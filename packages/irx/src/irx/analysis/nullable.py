"""
title: Resolve nullable scalar and Series kernel contracts before lowering.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx

from public import private

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.resolved_nodes import OwnershipKind
from irx.analysis.types import (
    common_numeric_type,
    is_assignable,
    is_integer_type,
    is_numeric_type,
    is_unsigned_type,
    same_type,
)
from irx.builtins.collections.column_types import (
    column_arrow_type,
    dataframe_schema_ipc,
)
from irx.builtins.collections.dataframe import dataframe_type_id
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked

KERNELS = {
    "+": "add_checked",
    "-": "subtract_checked",
    "*": "multiply_checked",
    "/": "divide_checked",
    "==": "equal",
    "!=": "not_equal",
    "<": "less",
    "<=": "less_equal",
    ">": "greater",
    ">=": "greater_equal",
    "&&": "and",
    "and": "and",
    "||": "or",
    "or": "or",
}
COMPARISONS = {"==", "!=", "<", "<=", ">", ">="}


@private
@typechecked
@dataclass(frozen=True)
class ColumnOperation:
    """
    title: Fully resolved kernel name, input storage and output type.
    attributes:
      kernel:
        type: str
      type_id:
        type: int
      result:
        type: astx.DataType
      input_type:
        type: astx.DataType | None
    """

    kernel: str
    type_id: int
    result: astx.DataType
    input_type: astx.DataType | None = None


@private
@typechecked
def scalar_type(type_: astx.DataType | None) -> astx.DataType | None:
    """
    title: Unwrap one column or nullable scalar type.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: astx.DataType | None
    """
    if isinstance(type_, astx.SeriesType):
        return type_.element_type
    if isinstance(type_, astx.NullableType):
        return type_.value_type
    return type_


@private
@typechecked
def nullable_error(
    analyzer: SemanticAnalyzerCore, node: astx.AST, message: str
) -> None:
    """
    title: Report unsupported nullable operations at the semantic boundary.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      message:
        type: str
    """
    analyzer.context.diagnostics.add(
        message, node=node, code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
    )


@private
@typechecked
def set_operation(
    analyzer: SemanticAnalyzerCore,
    node: astx.AST,
    kernel: str,
    input_type: astx.DataType | None,
    result: astx.DataType,
) -> None:
    """
    title: Record one checked operation and its owned Series result.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.AST
      kernel:
        type: str
      input_type:
        type: astx.DataType | None
      result:
        type: astx.DataType
    """
    type_id = dataframe_type_id(input_type)
    if type_id is None and kernel not in {"slice", "is_null", "count"}:
        nullable_error(
            analyzer,
            node,
            "Series scalar operations support numeric and bool "
            "types; retain other columns as Series/RecordBatch",
        )
        return
    analyzer._semantic(node).extras["column_operation"] = ColumnOperation(
        kernel, type_id or 0, result, input_type
    )
    analyzer._set_type(node, result)
    if isinstance(result, astx.SeriesType):
        analyzer._set_resource_ownership(
            node, arrow_ownership(result, OwnershipKind.OWNED)
        )
        function = analyzer.context.current_function
        if (
            function is None
            or function.signature.metadata.get("generator") is not None
        ):
            nullable_error(
                analyzer,
                node,
                "Series operations require a non-generator function",
            )


@private
@typechecked
def resolve_column_binary(
    analyzer: SemanticAnalyzerCore, node: astx.BinaryOp
) -> bool:
    """
    title: Resolve exact-type, null-propagating scalar and Series operations.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.BinaryOp
    returns:
      type: bool
    """
    left = analyzer._expr_type(node.lhs)
    right = analyzer._expr_type(node.rhs)
    managed = (astx.SeriesType, astx.NullableType)
    if node.op_code == "=" and isinstance(node.lhs, astx.SubscriptExpr):
        return resolve_series_store(analyzer, node)
    if node.op_code == "=" or not (
        isinstance(left, managed) or isinstance(right, managed)
    ):
        return False
    lhs, rhs = scalar_type(left), scalar_type(right)
    kernel = KERNELS.get(node.op_code)
    promoted = lhs if same_type(lhs, rhs) else common_numeric_type(lhs, rhs)
    if kernel is None or promoted is None:
        nullable_error(
            analyzer,
            node,
            "nullable/Series operators require compatible scalar "
            "types and a supported operator; cast operands explicitly",
        )
        return True
    if node.op_code in {"+", "-", "*", "/"} and not is_numeric_type(lhs):
        nullable_error(
            analyzer, node, "Series arithmetic requires numeric operands"
        )
        return True
    if node.op_code in {"&&", "and", "||", "or"} and not isinstance(
        lhs, astx.Boolean
    ):
        nullable_error(
            analyzer, node, "Series logical operators require bool operands"
        )
        return True
    assert promoted is not None
    output = astx.Boolean() if node.op_code in COMPARISONS else promoted
    nullable = any(
        isinstance(t, astx.NullableType)
        or (isinstance(t, astx.SeriesType) and t.nullable)
        for t in (left, right)
    )
    result: astx.DataType = astx.NullableType(output) if nullable else output
    if isinstance(left, astx.SeriesType) or isinstance(right, astx.SeriesType):
        result = astx.SeriesType(output, nullable=nullable)
    set_operation(analyzer, node, kernel, promoted, result)
    return True


@private
@typechecked
def resolve_column_index(
    analyzer: SemanticAnalyzerCore, node: astx.SubscriptExpr
) -> bool:
    """
    title: Resolve checked scalar access without borrowing Arrow storage.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.SubscriptExpr
    returns:
      type: bool
    """
    source = analyzer._expr_type(node.value)
    if not isinstance(source, astx.SeriesType):
        return False
    if isinstance(node.index, astx.LiteralNone):
        for bound in (node.lower, node.upper, node.step):
            if isinstance(bound, astx.LiteralNone):
                continue
            analyzer.visit(bound)
            if not is_integer_type(analyzer._expr_type(bound)) or isinstance(
                analyzer._expr_type(bound), (astx.UInt64, astx.UInt128)
            ):
                nullable_error(
                    analyzer,
                    node,
                    "Series slice bounds require integers "
                    "representable as i64",
                )
                return True
        set_operation(
            analyzer,
            node,
            "slice",
            source.element_type,
            astx.SeriesType(source.element_type, nullable=source.nullable),
        )
        return True
    index = analyzer._expr_type(node.index)
    if not is_integer_type(index) or isinstance(
        index, (astx.UInt64, astx.UInt128)
    ):
        nullable_error(
            analyzer,
            node,
            "Series indices require an integer representable as i64",
        )
        return True
    if any(
        not isinstance(value, astx.LiteralNone)
        for value in (node.lower, node.upper, node.step)
    ):
        nullable_error(analyzer, node, "Series slicing is unsupported")
        return True
    inner = source.element_type
    if inner is None:
        nullable_error(
            analyzer, node, "Series indexing requires a known element type"
        )
        return True
    result = astx.NullableType(inner) if source.nullable else inner
    set_operation(analyzer, node, "index", inner, result)
    return True


@private
@typechecked
def validate_column_declaration(
    analyzer: SemanticAnalyzerCore, type_: astx.DataType, node: astx.AST
) -> None:
    """
    title: Reject unsupported scalar storage and malformed rich declarations.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      type_:
        type: astx.DataType
      node:
        type: astx.AST
    """
    if isinstance(type_, astx.UnionType) and any(
        isinstance(member, astx.NullableType) for member in type_.members
    ):
        nullable_error(
            analyzer,
            node,
            "nullable scalar types inside unions are unsupported; "
            "use nullable[T]",
        )
        return
    if isinstance(type_, astx.ColumnType):
        nullable_error(
            analyzer,
            node,
            "parameterized column types require DataFrame/Series schemas",
        )
        return
    if isinstance(type_, astx.NullableType):
        if dataframe_type_id(type_.value_type) is None:
            nullable_error(
                analyzer,
                node,
                "nullable scalars support fixed-width numeric and bool types",
            )
        return
    try:
        if (
            isinstance(type_, astx.DataFrameType)
            and type_.columns is not None
            and any(
                isinstance(c.type_, astx.ColumnType) for c in type_.columns
            )
        ):
            dataframe_schema_ipc(type_)
        if isinstance(type_, astx.SeriesType) and isinstance(
            type_.element_type, astx.ColumnType
        ):
            column_arrow_type(type_.element_type)
    except (ValueError, TypeError) as error:
        nullable_error(analyzer, node, str(error))


@private
@typechecked
def resolve_column_unary(
    analyzer: SemanticAnalyzerCore, node: astx.UnaryOp
) -> bool:
    """
    title: Resolve checked, null-propagating unary column operations.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.UnaryOp
    returns:
      type: bool
    """
    source = analyzer._expr_type(node.operand)
    if not isinstance(source, (astx.NullableType, astx.SeriesType)):
        return False
    inner = scalar_type(source)
    kernels = {
        "+": "identity",
        "-": "negate_checked",
        "!": "invert",
        "not": "invert",
    }
    kernel = kernels.get(node.op_code)
    if (
        kernel is None
        or (kernel == "invert" and not isinstance(inner, astx.Boolean))
        or (kernel != "invert" and not is_numeric_type(inner))
    ):
        nullable_error(
            analyzer,
            node,
            "unsupported nullable/Series unary operator or operand type",
        )
        return True
    if kernel == "negate_checked" and is_unsigned_type(inner):
        nullable_error(
            analyzer,
            node,
            "negation requires a signed numeric type; "
            "cast unsigned values explicitly",
        )
        return True
    set_operation(analyzer, node, kernel, inner, source)
    return True


@private
@typechecked
def resolve_series_reduction(
    analyzer: SemanticAnalyzerCore, node: astx.SeriesReduction
) -> None:
    """
    title: Resolve null-skipping reductions with explicit accumulator types.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.SeriesReduction
    """
    analyzer.visit(node.value)
    source = analyzer._expr_type(node.value)
    if not isinstance(source, astx.SeriesType):
        nullable_error(analyzer, node, "Series reductions require a Series")
        return
    inner = source.element_type
    operation = node.operation
    if operation not in {"sum", "min", "max", "mean", "count", "any", "all"}:
        nullable_error(analyzer, node, "unknown Series reduction")
        return
    if operation in {"any", "all"}:
        if not isinstance(inner, astx.Boolean):
            nullable_error(
                analyzer, node, "Boolean reductions require bool columns"
            )
            return
        output: astx.DataType = astx.Boolean()
    elif operation == "count":
        output = astx.Int64()
    else:
        if not is_numeric_type(inner):
            nullable_error(
                analyzer, node, "numeric reductions require numeric columns"
            )
            return
        assert inner is not None
        output = inner
        if operation == "mean" or (
            operation == "sum" and not is_integer_type(inner)
        ):
            output = astx.Float64()
        elif operation == "sum":
            output = astx.UInt64() if is_unsigned_type(inner) else astx.Int64()
    result = output if operation == "count" else astx.NullableType(output)
    set_operation(analyzer, node, operation, inner, result)


@private
@typechecked
def resolve_nullable_global(
    analyzer: SemanticAnalyzerCore,
    node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
) -> None:
    """
    title: >-
      Resolve POD nullable globals to static validity and payload constants.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.VariableDeclaration | astx.InlineVariableDeclaration
    """
    if (
        not isinstance(node.type_, astx.NullableType)
        or analyzer.context.current_function is not None
        or analyzer.context.current_class is not None
    ):
        return
    value = node.value
    if isinstance(value, astx.Cast) and isinstance(
        value.value, astx.LiteralNone
    ):
        value = value.value
    if value is None or isinstance(value, (astx.Undefined, astx.LiteralNone)):
        payload: tuple[bool, int | float] = (False, 0)
    elif isinstance(value, astx.Literal) and isinstance(
        value.value, (int, float, bool)
    ):
        payload = (True, value.value)
    else:
        nullable_error(
            analyzer,
            node,
            "nullable globals require a numeric/Boolean "
            "literal or none initializer",
        )
        return
    analyzer._semantic(node).extras["nullable_global"] = payload


@private
@typechecked
def resolve_series_store(
    analyzer: SemanticAnalyzerCore, node: astx.BinaryOp
) -> bool:
    """
    title: Resolve checked element updates on a mutable Series binding.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.BinaryOp
    returns:
      type: bool
    """
    assert isinstance(node.lhs, astx.SubscriptExpr)
    source = analyzer._expr_type(node.lhs.value)
    if not isinstance(source, astx.SeriesType):
        return False
    if isinstance(node.lhs.index, astx.LiteralNone):
        nullable_error(
            analyzer, node, "Series assignment requires a single index"
        )
        return True
    element = analyzer._expr_type(node.lhs)
    if not is_assignable(element, analyzer._expr_type(node.rhs)):
        nullable_error(
            analyzer,
            node,
            "Series update requires an assignable scalar, "
            "preserving nullability",
        )
        return True
    set_operation(analyzer, node, "set", source.element_type, astx.NoneType())
    return True
