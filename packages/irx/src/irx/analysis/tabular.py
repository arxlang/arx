"""
title: Resolved tabular schemas and closed structural query signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import astx

from public import private, public

from irx.analysis.dataframe_values import legacy_adapter
from irx.analysis.interchange_values import interchange_signature
from irx.analysis.schema import canonical_schema
from irx.analysis.types import is_assignable, is_signed_integer_type, same_type
from irx.typecheck import typechecked

TABULAR_TYPES = (astx.TableType, astx.RecordBatchType)


@public
@typechecked
@dataclass(frozen=True)
class ResolvedTabular:
    """
    title: Resolved native symbol and ordered ABI expressions for a container.
    attributes:
      symbol:
        type: str
      result_type:
        type: astx.DataType
      arguments:
        type: tuple[astx.Expr, Ellipsis]
      indices:
        type: tuple[int, Ellipsis] | None
      feature:
        type: str
      required_version:
        type: int
      required_features:
        type: tuple[str, Ellipsis]
    """

    symbol: str
    result_type: astx.DataType
    arguments: tuple[astx.Expr, ...]
    indices: tuple[int, ...] | None = None
    feature: str = "dataframe"
    required_version: int = 0x00010200
    required_features: tuple[str, ...] = (
        "core",
        "array",
        "dataframe",
        "record_batch",
    )


@public
@typechecked
def tabular_column_type(
    owner: astx.TableType | astx.RecordBatchType, field: astx.SchemaField
) -> astx.ArrayType | astx.ChunkedArrayType:
    """
    title: Resolve a batch array or table chunk sequence from one field.
    parameters:
      owner:
        type: astx.TableType | astx.RecordBatchType
      field:
        type: astx.SchemaField
    returns:
      type: astx.ArrayType | astx.ChunkedArrayType
    """
    constructor = (
        astx.ArrayType
        if isinstance(owner, astx.RecordBatchType)
        else astx.ChunkedArrayType
    )
    return constructor(field.type_, nullable=field.nullable)


@private
@typechecked
def column_name(expr: astx.Expr) -> str:
    """
    title: Require literal column names for static schema transformations.
    parameters:
      expr:
        type: astx.Expr
    returns:
      type: str
    """
    if not isinstance(expr, astx.LiteralString):
        raise ValueError("static projection requires literal column names")
    return expr.value


@private
@typechecked
def column_index(schema: astx.Schema, expr: astx.Expr) -> int:
    """
    title: Resolve a unique static field without a backend name lookup.
    parameters:
      schema:
        type: astx.Schema
      expr:
        type: astx.Expr
    returns:
      type: int
    """
    name = column_name(expr)
    for index, field in enumerate(schema.fields):
        if field.name == name:
            return index
    raise ValueError(f"unknown column '{name}'")


@private
@typechecked
def static_query(
    node: astx.TabularQuery,
    owner: astx.TableType | astx.RecordBatchType,
    types: tuple[astx.DataType, ...],
) -> tuple[str, astx.DataType, tuple[astx.Expr, ...], tuple[int, ...] | None]:
    """
    title: Resolve schema-changing operations and checked static projections.
    parameters:
      node:
        type: astx.TabularQuery
      owner:
        type: astx.TableType | astx.RecordBatchType
      types:
        type: tuple[astx.DataType, Ellipsis]
    returns:
      type: >-
        tuple[str, astx.DataType, tuple[astx.Expr, Ellipsis], tuple[int,
        Ellipsis] | None]
    """
    schema = owner.schema
    if schema is None:
        raise ValueError("operation requires a static schema; use column_as")
    op, args = node.operation, node.arguments
    fields = schema.fields
    indices = None
    result: astx.DataType
    arguments: tuple[astx.Expr, ...]
    if op is astx.TabularOperation.COLUMN:
        index = column_index(schema, args[1])
        field = fields[index]
        return (
            "column_checked",
            tabular_column_type(owner, field),
            (args[0], astx.LiteralInt64(index), astx.FieldLiteral(field)),
            None,
        )
    if op is astx.TabularOperation.SELECT:
        indices = tuple(column_index(schema, arg) for arg in args[1:])
        fields = tuple(fields[index] for index in indices)
        symbol, arguments = "select", (args[0],)
    elif op is astx.TabularOperation.RENAME:
        if len(args) - 1 != len(fields):
            raise ValueError("rename_columns requires one name per column")
        fields = tuple(
            replace(field, name=column_name(arg))
            for field, arg in zip(fields, args[1:], strict=True)
        )
        symbol, arguments = "with_schema", (args[0],)
    elif op is astx.TabularOperation.REMOVE:
        index = column_index(schema, args[1])
        fields = fields[:index] + fields[index + 1 :]
        symbol, arguments = "remove", (args[0], astx.LiteralInt64(index))
    elif op in {astx.TabularOperation.ADD, astx.TabularOperation.REPLACE}:
        if not isinstance(args[1], astx.FieldLiteral):
            raise ValueError("column mutation requires a literal field")
        field = args[1].value
        if not is_assignable(tabular_column_type(owner, field), types[2]):
            raise ValueError("column value does not match its declared field")
        index = len(fields)
        if op is astx.TabularOperation.REPLACE:
            index = column_index(schema, astx.LiteralString(field.name))
            fields = (*fields[:index], field, *fields[index + 1 :])
        else:
            fields = (*fields, field)
        symbol, arguments = (
            "set_column",
            (
                args[0],
                astx.LiteralInt64(index),
                args[1],
                args[2],
            ),
        )
    else:
        raise ValueError("unsupported static tabular operation")
    changed = canonical_schema(astx.Schema(fields, metadata=schema.metadata))
    result = type(owner)(changed)
    if op is astx.TabularOperation.RENAME:
        arguments = (*arguments, astx.SchemaLiteral(changed))
    return symbol, result, arguments, indices


@public
@typechecked
def resolve_tabular_query(
    node: astx.TabularQuery, types: tuple[astx.DataType, ...]
) -> ResolvedTabular:
    """
    title: Close the operation signature before lowering or native execution.
    parameters:
      node:
        type: astx.TabularQuery
      types:
        type: tuple[astx.DataType, Ellipsis]
    returns:
      type: ResolvedTabular
    """
    op, args = node.operation, node.arguments
    arity = {
        astx.TabularOperation.COLUMN: 2,
        astx.TabularOperation.COLUMN_AS: 3,
        astx.TabularOperation.SLICE: 3,
        astx.TabularOperation.ADD: 3,
        astx.TabularOperation.REPLACE: 3,
        astx.TabularOperation.REMOVE: 2,
        astx.TabularOperation.TAKE: 2,
        astx.TabularOperation.IMPORT_C_DATA: 2,
        astx.TabularOperation.WITH_VALIDITY: 3,
        astx.TabularOperation.FROM_BUFFERS: 5,
    }.get(op, 1)
    variadic = op in {
        astx.TabularOperation.SELECT,
        astx.TabularOperation.RENAME,
    }
    if (
        not args
        or len(types) != len(args)
        or (not variadic and len(args) != arity)
    ):
        raise ValueError(f"{op.value} has invalid argument count")
    owner = types[0]
    interchange = interchange_signature(node, types)
    if interchange is not None:
        symbol, result_type = interchange
        return ResolvedTabular(
            symbol,
            result_type,
            args,
            feature="array",
            required_version=0x00010600,
            required_features=("core", "array"),
        )
    adapter = legacy_adapter(op, owner)
    if adapter is not None:
        symbol, result_type, feature = adapter
        return ResolvedTabular(
            symbol,
            result_type,
            args,
            feature=feature,
            required_version=0x00010000,
        )
    if not isinstance(owner, TABULAR_TYPES):
        raise ValueError(f"{op.value} requires a table or record_batch")
    prefix = "batch" if isinstance(owner, astx.RecordBatchType) else "table"
    result: astx.DataType
    suffix, result, arguments, indices = "", owner, args, None
    if op in {astx.TabularOperation.ROWS, astx.TabularOperation.COLUMNS}:
        suffix = "rows" if op is astx.TabularOperation.ROWS else "columns"
        result = astx.Int64()
    elif op is astx.TabularOperation.SCHEMA:
        suffix, result = "schema", astx.SchemaType()
    elif op is astx.TabularOperation.SLICE:
        if not all(is_signed_integer_type(type_) for type_ in types[1:]):
            raise ValueError("slice_rows requires signed integer bounds")
        suffix = "slice"
    elif op is astx.TabularOperation.TAKE:
        expected = astx.ArrayType(astx.LogicalType(astx.LogicalKind.INT64))
        if not same_type(types[1], expected):
            raise ValueError("take_rows requires a nonnullable array[i64]")
        suffix = "take"
    elif op is astx.TabularOperation.COLUMN_AS:
        if not is_signed_integer_type(types[1]) or not isinstance(
            args[2], astx.FieldLiteral
        ):
            raise ValueError("column_as requires an index and literal field")
        suffix = "column_checked"
        result = tabular_column_type(owner, args[2].value)
    elif op is astx.TabularOperation.DYNAMIC:
        return ResolvedTabular(
            "irx_arrow_"
            + ("record_batch" if prefix == "batch" else prefix)
            + "_retain",
            type(owner)(),
            args,
            feature="record_batch" if prefix == "batch" else "dataframe",
            required_version=0x00010000,
        )
    elif op in {
        astx.TabularOperation.TO_TABLE,
        astx.TabularOperation.TO_BATCH,
    }:
        to_table = op is astx.TabularOperation.TO_TABLE
        if to_table == isinstance(owner, astx.TableType):
            raise ValueError("conversion requires the other container kind")
        suffix = "to_table" if to_table else "to_batch"
        result = (
            astx.TableType(owner.schema)
            if to_table
            else astx.RecordBatchType(owner.schema)
        )
    elif op is astx.TabularOperation.COMBINE:
        if not isinstance(owner, astx.TableType):
            raise ValueError("table_combine_chunks requires a table")
        suffix = "combine"
    else:
        suffix, result, arguments, indices = static_query(node, owner, types)
    return ResolvedTabular(
        f"irx_arrow_{prefix}_{suffix}", result, arguments, indices
    )
