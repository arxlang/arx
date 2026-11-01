"""
title: Resolve trusted tabular I/O without arbitrary FFI access.
"""

from dataclasses import dataclass

import astx

from public import private

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.class_lifecycle import class_ownership
from irx.analysis.extensions.calls import AnalysisCall, CallAnalysisServices
from irx.analysis.extensions.records import CALL_PLAN, CallOperation, CallPlan
from irx.analysis.resolved_nodes import OwnershipKind, SemanticInfo
from irx.analysis.types import (
    is_boolean_type,
    is_float_type,
    is_signed_integer_type,
    is_string_type,
    same_type,
)
from irx.builtins.collections.dataframe import (
    DATAFRAME_SCHEMA_EXTRA,
    schema_from_type,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions import HandlerContribution, contribute
from irx.native import TableIOOperation
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True)
class TableOperation(CallOperation):
    """
    title: Trusted host operation identity independent of local source names.
    attributes:
      name:
        type: TableIOOperation
    """

    name: TableIOOperation

    def __post_init__(self) -> None:
        """
        title: Validate the closed trusted capability identifier.
        """
        validate_operation(self.name)


@private
@typechecked
def validate_operation(name: TableIOOperation) -> None:
    """
    title: Validate generated operation constructor arguments.
    parameters:
      name:
        type: TableIOOperation
    """


@private
@typechecked
class ReadTableOperation(TableOperation):
    """
    title: Nominal read operation dispatch key.
    attributes:
      name:
        type: TableIOOperation
    """


@private
@typechecked
class WriteTableOperation(TableOperation):
    """
    title: Nominal write operation dispatch key.
    attributes:
      name:
        type: TableIOOperation
    """


@private
@typechecked
class AuxiliaryTableOperation(TableOperation):
    """
    title: Existing predicate and streaming operations.
    attributes:
      name:
        type: TableIOOperation
    """


@private
@typechecked
def table_operation(name: TableIOOperation) -> TableOperation:
    """
    title: Construct meaning only from a validated host capability.
    parameters:
      name:
        type: TableIOOperation
    returns:
      type: TableOperation
    """
    if name.startswith("read_"):
        return ReadTableOperation(name)
    if name.startswith("write_"):
        return WriteTableOperation(name)
    return AuxiliaryTableOperation(name)


# These are trusted operation schemas, not names recognized in user code.
CSV_READ = {
    "path": "text",
    "schema": "schema",
    "columns": "texts",
    "names": "texts",
    "delimiter": "text",
    "header": "bool",
    "quotechar": "text",
    "doublequote": "bool",
    "escapechar": "text",
    "skiprows": "int",
    "skip_blank_lines": "bool",
    "null_values": "texts",
    "block_size": "int",
}
CSV_WRITE = {
    "frame": "frame",
    "path": "text",
    "delimiter": "text",
    "header": "bool",
    "lineterminator": "text",
    "na_rep": "text",
    "quoting": "text",
}
PARQUET_READ = {
    "path": "text",
    "schema": "schema",
    "columns": "texts",
    "filters": "filters",
    "row_groups": "ints",
    "options": "options",
    "batch_size": "int",
}
PARQUET_WRITE = {
    "frame": "frame",
    "path": "text",
    "compression": "text",
    "row_group_size": "int",
    "atomic": "bool",
    "durable": "bool",
    "append": "bool",
    "partition_columns": "texts",
    "options": "options",
}


@private
@typechecked
@dataclass(frozen=True)
class TableIOArgument:
    """
    title: One source-order operand with a validated lowering contract.
    attributes:
      name:
        type: str
      expression:
        type: astx.AST
      kind:
        type: str
      handle_index:
        type: int | None
      literals:
        type: tuple[str | int, Ellipsis]
    """

    name: str
    expression: astx.AST
    kind: str
    handle_index: int | None = None
    literals: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        """
        title: Validate the operand record before publishing a semantic plan.
        """
        validate_table_argument(
            self.name,
            self.expression,
            self.kind,
            self.handle_index,
            self.literals,
        )


@private
@typechecked
@dataclass(frozen=True)
class TableIOCall(CallPlan):
    """
    title: Complete I/O plan with omission and native identities.
    attributes:
      operation:
        type: TableIOOperation
      arguments:
        type: tuple[TableIOArgument, Ellipsis]
      construction:
        type: astx.ClassConstruct | None
      result_handle_index:
        type: int | None
    """

    operation: TableIOOperation
    arguments: tuple[TableIOArgument, ...]
    construction: astx.ClassConstruct | None = None
    result_handle_index: int | None = None

    def __post_init__(self) -> None:
        """
        title: >-
          Validate generated record constructors including collection items.
        """
        self.validate()

    def validate(self) -> None:
        """
        title: Check the complete table plan and each operand record.
        """
        validate_table_plan(
            self.operation,
            self.arguments,
            self.construction,
            self.result_handle_index,
        )

    def dependencies(self) -> tuple[astx.AST, ...]:
        """
        title: >-
          Expose operands and generated construction to declaration
          reachability.
        returns:
          type: tuple[astx.AST, Ellipsis]
        """
        expressions = tuple(argument.expression for argument in self.arguments)
        if self.construction is None:
            return expressions
        return (*expressions, self.construction)

    def invalidate(self, node: astx.AST) -> None:
        """
        title: Clear table-owned companion facts before a new analysis attempt.
        parameters:
          node:
            type: astx.AST
        """
        info = getattr(node, "semantic", None)
        if isinstance(info, SemanticInfo):
            info.resource_ownership = None
            info.resolved_class = None
            info.extras.pop(DATAFRAME_SCHEMA_EXTRA, None)


@private
@typechecked
def validate_table_plan(
    operation: TableIOOperation,
    arguments: tuple[TableIOArgument, ...],
    construction: astx.ClassConstruct | None,
    result_handle_index: int | None,
) -> None:
    """
    title: Validate nested table plan records at attachment boundaries.
    parameters:
      operation:
        type: TableIOOperation
      arguments:
        type: tuple[TableIOArgument, Ellipsis]
      construction:
        type: astx.ClassConstruct | None
      result_handle_index:
        type: int | None
    """
    for argument in arguments:
        validate_table_argument(
            argument.name,
            argument.expression,
            argument.kind,
            argument.handle_index,
            argument.literals,
        )
    if result_handle_index is not None and result_handle_index < 0:
        raise ValueError("result handle index must be non-negative")


@private
@typechecked
def validate_table_argument(
    name: str,
    expression: astx.AST,
    kind: str,
    handle_index: int | None,
    literals: tuple[str | int, ...],
) -> None:
    """
    title: Check every collection member in a resolved operand.
    parameters:
      name:
        type: str
      expression:
        type: astx.AST
      kind:
        type: str
      handle_index:
        type: int | None
      literals:
        type: tuple[str | int, Ellipsis]
    """
    if kind not in {
        "text",
        "int",
        "bool",
        "float",
        "frame",
        "opaque",
        "texts",
        "ints",
        "schema",
        "options",
        "filters",
    }:
        raise ValueError(f"invalid table operand kind: {kind}")
    if handle_index is not None and handle_index < 0:
        raise ValueError("handle index must be non-negative")
    if kind == "texts" and any(not isinstance(v, str) for v in literals):
        raise TypeError("text operands require string literals")
    if kind == "ints" and any(type(v) is not int for v in literals):
        raise TypeError("integer operands require integer literals")
    if kind not in {"texts", "ints"} and literals:
        raise ValueError("only literal-list operands carry literal values")


@private
@typechecked
def arrow_handle_index(
    services: CallAnalysisServices,
    type_: astx.DataType | None,
    role: str,
    node: astx.AST,
) -> int | None:
    """
    title: Require a canonical host-registered Arrow owner, never a lookalike.
    parameters:
      services:
        type: CallAnalysisServices
      type_:
        type: astx.DataType | None
      role:
        type: str
      node:
        type: astx.AST
    returns:
      type: int | None
    """
    if not isinstance(type_, astx.ClassType):
        return None
    class_ = services.resolve_class(type_, node)
    if class_ is None or class_.layout is None:
        return None
    if not any(
        declared is class_.declaration and declared.name == role
        for declared in services.registered_classes
    ):
        return None
    fields = class_.layout.instance_fields
    handle = "IrxRbApiSchema" if role == "Schema" else "IrxRbApiOptions"
    if (
        class_.bases
        or len(fields) != 1
        or not isinstance(fields[0].member.type_, astx.OpaqueHandleType)
        or fields[0].member.type_.handle_name != handle
        or fields[0].member.visibility is not astx.VisibilityKind.private
    ):
        return None
    return fields[0].storage_index


@private
@typechecked
def resolve_table_io(
    operation_key: TableOperation, call: AnalysisCall
) -> None:
    """
    title: Bind a resolved operation through explicit narrow analysis services.
    parameters:
      operation_key:
        type: TableOperation
      call:
        type: AnalysisCall
    """
    operation = operation_key.name
    node, function, info = call.node, call.function, call.info
    services = call.services
    if not services.allowed:
        call.diagnostics.add(
            "table I/O requires a non-generator function",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    specs = {
        "read_csv": CSV_READ,
        "write_csv": CSV_WRITE,
        "read_parquet": PARQUET_READ,
        "write_parquet": PARQUET_WRITE,
        "where": {"column": "text", "operation": "text", "value": "scalar"},
        "csv_frame": {"box": "opaque"},
        "parquet_frame": {"box": "opaque"},
        "csv_write_frame": {"box": "opaque", "frame": "frame"},
        "parquet_write_frame": {"box": "opaque", "frame": "frame"},
    }[operation]
    required = tuple(arg.name for arg in function.prototype.args.nodes)
    names = tuple(specs)
    arguments: list[tuple[str, astx.AST]] = []
    valid = True

    def error(message: str, location: astx.AST = node) -> None:
        """
        title: Diagnose invalid I/O inputs at their trustworthy source node.
        parameters:
          message:
            type: str
          location:
            type: astx.AST
        """
        nonlocal valid
        valid = False
        call.diagnostics.add(
            message, node=location, code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH
        )

    if len(tuple(node.args)) > len(names):
        error(f"too many arguments to {function.name}")
    for name, value in zip(names, node.args):
        arguments.append((name, value))
    seen = {name for name, _ in arguments}
    for keyword in node.keywords:
        if keyword.name not in specs:
            error(
                f"unknown argument '{keyword.name}' to {function.name}",
                keyword,
            )
        elif keyword.name in seen:
            error(
                f"duplicate argument '{keyword.name}' to {function.name}",
                keyword,
            )
        else:
            arguments.append((keyword.name, keyword.value))
            seen.add(keyword.name)
    for name in required:
        if name not in seen:
            error(f"missing required argument '{name}' to {function.name}")
    resolved: list[TableIOArgument] = []
    for name, expression in arguments:
        kind = specs[name]
        literals: tuple[str | int, ...] = ()
        index = None
        if kind in {"texts", "ints"}:
            if not isinstance(expression, (astx.LiteralList, astx.ListExpr)):
                error(f"{name} requires a literal list", expression)
                continue
            items = expression.elements
            if not items and name != "null_values":
                error(f"{name} must not be empty", expression)
            values: list[str | int] = []
            for item in items:
                if kind == "texts" and isinstance(item, astx.LiteralString):
                    if "\0" in item.value:
                        error(f"{name} must not contain NUL", item)
                    values.append(item.value)
                elif kind == "ints" and isinstance(
                    item,
                    (
                        astx.LiteralInt8,
                        astx.LiteralInt16,
                        astx.LiteralInt32,
                        astx.LiteralInteger,
                        astx.LiteralInt64,
                    ),
                ):
                    values.append(item.value)
                else:
                    label = "string" if kind == "texts" else "integer"
                    error(
                        f"{name} requires {label} literals",
                        item,
                    )
            if len(values) != len(set(values)):
                error(f"{name} must not contain duplicates", expression)
            literals = tuple(values)
        else:
            type_ = services.evaluate(expression)
            if kind in {"schema", "options", "filters"}:
                role = {
                    "schema": "Schema",
                    "options": "ParquetOptions",
                    "filters": "ParquetFilter",
                }[kind]
                index = arrow_handle_index(services, type_, role, expression)
                if index is None:
                    error(
                        f"{name} requires the registered {role} class",
                        expression,
                    )
            elif kind == "scalar":
                if is_boolean_type(type_):
                    kind = "bool"
                elif is_signed_integer_type(type_):
                    kind = "int"
                elif is_float_type(type_):
                    kind = "float"
                elif is_string_type(type_):
                    kind = "text"
                else:
                    error(
                        "filter value must be string, signed integer, "
                        "float or bool",
                        expression,
                    )
                    continue
            else:
                accepted = {
                    "text": is_string_type(type_),
                    "int": is_signed_integer_type(type_),
                    "bool": is_boolean_type(type_),
                    "frame": isinstance(type_, astx.DataFrameType),
                    "opaque": isinstance(type_, astx.OpaqueHandleType)
                    and same_type(
                        type_, function.signature.parameters[0].type_
                    ),
                }.get(kind, False)
                if not accepted:
                    error(f"{name} requires {kind}", expression)
            if (
                isinstance(expression, astx.LiteralString)
                and "\0" in expression.value
            ):
                error(f"{name} must not contain NUL", expression)
        resolved.append(
            TableIOArgument(name, expression, kind, index, literals)
        )
    construction = None
    result_index = None
    result_type = function.signature.return_type
    if operation == "where":
        result_index = arrow_handle_index(
            services, result_type, "ParquetFilter", node
        )
        if result_index is None or not isinstance(result_type, astx.ClassType):
            error("where requires a registered ParquetFilter result")
        else:
            class_ = services.resolve_class(result_type, node)
            assert class_ is not None
            construction = astx.ClassConstruct(class_.name)
            services.construct(construction, class_)
            if valid:
                info.resolved_class = class_
                info.resource_ownership = class_ownership(OwnershipKind.OWNED)
    elif valid and isinstance(result_type, astx.DataFrameType):
        info.resource_ownership = arrow_ownership(
            result_type, OwnershipKind.OWNED
        )
        info.extras[DATAFRAME_SCHEMA_EXTRA] = schema_from_type(result_type)
    if valid:
        info.facts = info.facts.with_fact(
            CALL_PLAN,
            TableIOCall(
                operation, tuple(resolved), construction, result_index
            ),
        )


@private
@typechecked
def analyze_read(operation: ReadTableOperation, call: AnalysisCall) -> None:
    """
    title: Resolve CSV and Parquet reads through the common table contract.
    parameters:
      operation:
        type: ReadTableOperation
      call:
        type: AnalysisCall
    """
    resolve_table_io(operation, call)


@private
@typechecked
def analyze_write(operation: WriteTableOperation, call: AnalysisCall) -> None:
    """
    title: >-
      Resolve CSV and Parquet writes without changing generic call analysis.
    parameters:
      operation:
        type: WriteTableOperation
      call:
        type: AnalysisCall
    """
    resolve_table_io(operation, call)


@private
@typechecked
def analyze_auxiliary(
    operation: AuxiliaryTableOperation, call: AnalysisCall
) -> None:
    """
    title: Resolve existing predicate and streaming operations.
    parameters:
      operation:
        type: AuxiliaryTableOperation
      call:
        type: AnalysisCall
    """
    resolve_table_io(operation, call)


@private
@typechecked
def analysis_contributions() -> tuple[HandlerContribution, ...]:
    """
    title: >-
      Export the finite table provider explicitly, without global dispatch.
    returns:
      type: tuple[HandlerContribution, Ellipsis]
    """
    return (
        contribute(
            "table.read",
            "irx.table_io",
            "analysis",
            ReadTableOperation,
            AnalysisCall,
            analyze_read,
        ),
        contribute(
            "table.write",
            "irx.table_io",
            "analysis",
            WriteTableOperation,
            AnalysisCall,
            analyze_write,
        ),
        contribute(
            "table.auxiliary",
            "irx.table_io",
            "analysis",
            AuxiliaryTableOperation,
            AnalysisCall,
            analyze_auxiliary,
        ),
    )
