"""
title: Resolve trusted tabular I/O without arbitrary FFI access.
"""

from dataclasses import dataclass
from typing import cast

import astx

from public import private

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.class_lifecycle import class_ownership
from irx.analysis.handlers.base import (
    SemanticAnalyzerCore,
    SemanticVisitorMixinBase,
)
from irx.analysis.resolved_nodes import OwnershipKind, SemanticFunction
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
from irx.native import TableIOOperation
from irx.typecheck import typechecked

TABLE_IO = "table_io"

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


@private
@typechecked
@dataclass(frozen=True)
class TableIOCall:
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


@private
@typechecked
def arrow_handle_index(
    analyzer: SemanticAnalyzerCore,
    type_: astx.DataType | None,
    role: str,
    node: astx.AST,
) -> int | None:
    """
    title: Require a canonical host-registered Arrow owner, never a lookalike.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      type_:
        type: astx.DataType | None
      role:
        type: str
      node:
        type: astx.AST
    returns:
      type: int | None
    """
    if not isinstance(type_, astx.ClassType) or analyzer.session is None:
        return None
    class_ = analyzer._resolve_class_from_type(
        type_, node=node, unknown_message="unknown Arrow class {name}"
    )
    if class_ is None or class_.layout is None:
        return None
    if not any(
        declared is class_.declaration and declared.name == role
        for module in analyzer.session.modules.values()
        for declared in module.native_arrow_classes
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
    analyzer: SemanticAnalyzerCore,
    node: astx.FunctionCall | astx.MethodCall,
    function: SemanticFunction,
) -> bool:
    """
    title: Bind and type-check a declared I/O capability before ordinary FFI.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.FunctionCall | astx.MethodCall
      function:
        type: SemanticFunction
    returns:
      type: bool
    """
    operation = analyzer.context.native_table_io.get(id(function.prototype))
    if operation is None:
        return False
    current = analyzer.context.current_function
    if (
        current is None
        or current.signature.metadata.get("generator") is not None
    ):
        analyzer.context.diagnostics.add(
            "table I/O requires a non-generator function",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return True
    info = analyzer._semantic(node)
    info.extras.pop(TABLE_IO, None)
    analyzer._set_function(node, function)
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
        analyzer.context.diagnostics.add(
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
            if not isinstance(expression, astx.LiteralList):
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
                        astx.SourceInteger,
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
            analyzer.visit(expression)
            type_ = analyzer._expr_type(expression)
            if kind in {"schema", "options", "filters"}:
                role = {
                    "schema": "Schema",
                    "options": "ParquetOptions",
                    "filters": "ParquetFilter",
                }[kind]
                index = arrow_handle_index(analyzer, type_, role, expression)
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
            analyzer, result_type, "ParquetFilter", node
        )
        if result_index is None or not isinstance(result_type, astx.ClassType):
            error("where requires a registered ParquetFilter result")
        else:
            class_ = analyzer._resolve_class_from_type(
                result_type,
                node=node,
                unknown_message="unknown filter class {name}",
            )
            assert class_ is not None
            construction = astx.ClassConstruct(class_.name)
            cast(
                SemanticVisitorMixinBase, analyzer
            ).resolve_class_construction(construction, class_)
            analyzer._set_class(node, class_)
            analyzer._set_resource_ownership(
                node, class_ownership(OwnershipKind.OWNED)
            )
    elif isinstance(result_type, astx.DataFrameType):
        analyzer._set_resource_ownership(
            node, arrow_ownership(result_type, OwnershipKind.OWNED)
        )
        info.extras[DATAFRAME_SCHEMA_EXTRA] = schema_from_type(result_type)
    analyzer._set_type(node, result_type)
    if valid:
        info.extras[TABLE_IO] = TableIOCall(
            operation, tuple(resolved), construction, result_index
        )
    return True
