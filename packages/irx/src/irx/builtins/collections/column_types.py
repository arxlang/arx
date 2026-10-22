"""
title: Resolve exact parameterized column schemas during semantic analysis.
"""

from __future__ import annotations

from typing import Callable, cast

import astx
import pyarrow as pa

from public import private, public

from irx.typecheck import typechecked

PAIR_SIZE = 2


@private
@typechecked
def column_field(name: str, type_: astx.DataType) -> pa.Field:
    """
    title: Preserve explicit nested nullability in a column field.
    parameters:
      name:
        type: str
      type_:
        type: astx.DataType
    returns:
      type: pa.Field
    """
    nullable = isinstance(type_, astx.NullableType)
    inner = type_.value_type if isinstance(type_, astx.NullableType) else type_
    return pa.field(name, column_arrow_type(inner), nullable=nullable)


@private
@typechecked
def binary_column(type_: astx.ColumnType) -> pa.DataType:
    """
    title: Resolve variable or fixed binary and large UTF-8 storage.
    parameters:
      type_:
        type: astx.ColumnType
    returns:
      type: pa.DataType
    """
    name, args = type_.column_kind, type_.arguments
    if not args:
        return {
            "binary": pa.binary,
            "large_binary": pa.large_binary,
            "large_string": pa.large_string,
        }[name]()
    if (
        name == "binary"
        and len(args) == 1
        and type(args[0]) is int
        and args[0] > 0
    ):
        return pa.binary(args[0])
    raise ValueError(f"unsupported parameters for {name}")


@private
@typechecked
def decimal_column(type_: astx.ColumnType) -> pa.DataType:
    """
    title: Validate decimal precision and signed scale.
    parameters:
      type_:
        type: astx.ColumnType
    returns:
      type: pa.DataType
    """
    args = type_.arguments
    if len(args) != PAIR_SIZE or not all(type(a) is int for a in args):
        raise ValueError("decimal columns require integer precision and scale")
    precision, scale = args
    assert isinstance(precision, int) and isinstance(scale, int)
    factory = (
        pa.decimal128 if type_.column_kind == "decimal128" else pa.decimal256
    )
    return factory(precision, scale)


@private
@typechecked
def temporal_column(type_: astx.ColumnType) -> pa.DataType:
    """
    title: Validate physical time units and optional timestamp zones.
    parameters:
      type_:
        type: astx.ColumnType
    returns:
      type: pa.DataType
    """
    args = type_.arguments
    if not 1 <= len(args) <= PAIR_SIZE or not all(
        isinstance(a, str) for a in args
    ):
        raise ValueError(
            "temporal columns require a unit and optional timezone"
        )
    unit = args[0]
    assert isinstance(unit, str)
    if unit not in {"s", "ms", "us", "ns"}:
        raise ValueError("temporal units must be s, ms, us or ns")
    if type_.column_kind == "timestamp":
        zone = args[1] if len(args) == PAIR_SIZE else None
        assert zone is None or isinstance(zone, str)
        if zone is not None and (not zone or "\0" in zone):
            raise ValueError("timestamp timezone must be nonempty without NUL")
        return pa.timestamp(unit, tz=zone)
    if len(args) != 1:
        raise ValueError("only timestamps accept timezones")
    return pa.time32(unit) if unit in {"s", "ms"} else pa.time64(unit)


@private
@typechecked
def list_column(type_: astx.ColumnType) -> pa.DataType:
    """
    title: Resolve list offset widths, child nullability and fixed sizes.
    parameters:
      type_:
        type: astx.ColumnType
    returns:
      type: pa.DataType
    """
    args = type_.arguments
    if not args or not isinstance(args[0], astx.DataType):
        raise ValueError("list columns require an element type")
    field = column_field("item", args[0])
    if type_.column_kind == "fixed_list":
        if len(args) != PAIR_SIZE or type(args[1]) is not int or args[1] <= 0:
            raise ValueError(
                "fixed_list requires an element type and positive size"
            )
        return pa.list_(field, args[1])
    if len(args) != 1:
        raise ValueError("variable list columns require one element type")
    return (
        pa.large_list(field)
        if type_.column_kind == "large_list"
        else pa.list_(field)
    )


@private
@typechecked
def paired_column(type_: astx.ColumnType) -> pa.DataType:
    """
    title: Resolve dictionary index/value or map key/item types.
    parameters:
      type_:
        type: astx.ColumnType
    returns:
      type: pa.DataType
    """
    args = type_.arguments
    if len(args) != PAIR_SIZE or not all(
        isinstance(a, astx.DataType) for a in args
    ):
        raise ValueError(f"{type_.column_kind} requires two column types")
    key, value = args
    assert isinstance(key, astx.DataType) and isinstance(value, astx.DataType)
    if type_.column_kind == "dictionary":
        return pa.dictionary(column_arrow_type(key), column_arrow_type(value))
    return pa.map_(column_arrow_type(key), column_field("value", value))


@private
@typechecked
def struct_column(type_: astx.ColumnType) -> pa.DataType:
    """
    title: Validate ordered, unique named fields with explicit nullability.
    parameters:
      type_:
        type: astx.ColumnType
    returns:
      type: pa.DataType
    """
    args = type_.arguments
    if not args or len(args) % PAIR_SIZE:
        raise ValueError("struct columns require named typed fields")
    fields: list[pa.Field] = []
    for name, value in zip(args[::2], args[1::2]):
        if not isinstance(name, str) or not isinstance(value, astx.DataType):
            raise ValueError("struct columns require named typed fields")
        if not name or "\0" in name or any(f.name == name for f in fields):
            raise ValueError(
                "struct field names must be unique and nonempty without NUL"
            )
        fields.append(column_field(name, value))
    return pa.struct(fields)


@public
@typechecked
def column_arrow_type(type_: astx.DataType) -> pa.DataType:
    """
    title: Resolve exact column storage without lossy coercions.
    parameters:
      type_:
        type: astx.DataType
    returns:
      type: pa.DataType
    """
    primitive: dict[type[astx.DataType], pa.DataType] = {
        astx.Int8: pa.int8(),
        astx.Int16: pa.int16(),
        astx.Int32: pa.int32(),
        astx.Int64: pa.int64(),
        astx.UInt8: pa.uint8(),
        astx.UInt16: pa.uint16(),
        astx.UInt32: pa.uint32(),
        astx.UInt64: pa.uint64(),
        astx.Float32: pa.float32(),
        astx.Float64: pa.float64(),
        astx.Boolean: pa.bool_(),
        astx.String: pa.string(),
        astx.UTF8String: pa.string(),
        astx.Date: pa.date32(),
        astx.Time: pa.time64("us"),
        astx.Timestamp: pa.timestamp("us"),
        astx.DateTime: pa.timestamp("us"),
    }
    if type(type_) in primitive:
        return primitive[type(type_)]
    if not isinstance(type_, astx.ColumnType):
        raise ValueError(f"unsupported column type: {type(type_).__name__}")
    resolvers: dict[str, Callable[[astx.ColumnType], pa.DataType]] = {
        "binary": binary_column,
        "large_binary": binary_column,
        "large_string": binary_column,
        "decimal128": decimal_column,
        "decimal256": decimal_column,
        "timestamp": temporal_column,
        "time": temporal_column,
        "arrow_list": list_column,
        "large_list": list_column,
        "fixed_list": list_column,
        "dictionary": paired_column,
        "arrow_map": paired_column,
        "arrow_struct": struct_column,
    }
    resolver = resolvers.get(type_.column_kind)
    if resolver is None:
        raise ValueError(f"unsupported column type: {type_.column_kind}")
    try:
        return resolver(type_)
    except OverflowError as error:
        raise ValueError(
            f"{type_.column_kind} parameters exceed "
            "the supported integer range"
        ) from error


@public
@typechecked
def dataframe_schema_ipc(type_: astx.DataFrameType) -> bytes:
    """
    title: Serialize the exact declared schema, not input-dependent inference.
    parameters:
      type_:
        type: astx.DataFrameType
    returns:
      type: bytes
    """
    if not type_.columns:
        raise ValueError("a static DataFrame schema must contain columns")
    names = [c.name for c in type_.columns]
    if len(set(names)) != len(names) or any(not n or "\0" in n for n in names):
        raise ValueError("DataFrame requires unique nonempty column names")
    schema = pa.schema(
        [
            pa.field(c.name, column_arrow_type(c.type_), nullable=c.nullable)
            for c in type_.columns
        ]
    )
    return cast(bytes, schema.serialize().to_pybytes())
