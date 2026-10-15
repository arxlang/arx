"""
title: Central logical-to-physical columnar type resolution.
summary: >-
  Resolve portable C Data formats and fixed-width storage. A known format is
  not a claim that container construction or kernels exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import astx

from astx.schema import LogicalKind, LogicalType, ParameterKind, TimeUnit
from public import private, public

from irx.analysis.array_values import array_storage
from irx.analysis.dataframe_values import dataframe_element, dataframe_schema
from irx.analysis.nullability import (
    aggregate_nullable,
    managed_nullable,
    normalize_nullable,
    nullable_diagnostic,
)
from irx.analysis.schema import (
    DECIMAL_PRECISIONS,
    MAX_SCHEMA_DEPTH,
    UNION_KINDS,
    SchemaError,
    canonical_logical_type,
    canonical_schema,
    parameter_value,
)
from irx.typecheck import typechecked

SIMPLE_FORMATS = {
    LogicalKind.NULL: "n",
    LogicalKind.BOOL: "b",
    LogicalKind.INT8: "c",
    LogicalKind.INT16: "s",
    LogicalKind.INT32: "i",
    LogicalKind.INT64: "l",
    LogicalKind.UINT8: "C",
    LogicalKind.UINT16: "S",
    LogicalKind.UINT32: "I",
    LogicalKind.UINT64: "L",
    LogicalKind.FLOAT16: "e",
    LogicalKind.FLOAT32: "f",
    LogicalKind.FLOAT64: "g",
    LogicalKind.STRING: "u",
    LogicalKind.LARGE_STRING: "U",
    LogicalKind.BINARY: "z",
    LogicalKind.LARGE_BINARY: "Z",
    LogicalKind.STRING_VIEW: "vu",
    LogicalKind.BINARY_VIEW: "vz",
    LogicalKind.DATE32: "tdD",
    LogicalKind.DATE64: "tdm",
    LogicalKind.MONTH_INTERVAL: "tiM",
    LogicalKind.DAY_TIME_INTERVAL: "tiD",
    LogicalKind.MONTH_DAY_NANO_INTERVAL: "tin",
    LogicalKind.LIST: "+l",
    LogicalKind.LARGE_LIST: "+L",
    LogicalKind.LIST_VIEW: "+vl",
    LogicalKind.LARGE_LIST_VIEW: "+vL",
    LogicalKind.STRUCT: "+s",
    LogicalKind.MAP: "+m",
    LogicalKind.RUN_END_ENCODED: "+r",
}
TIME_FORMAT_UNITS = {
    TimeUnit.SECOND: "s",
    TimeUnit.MILLISECOND: "m",
    TimeUnit.MICROSECOND: "u",
    TimeUnit.NANOSECOND: "n",
}
BIT_WIDTHS = {
    LogicalKind.BOOL: 1,
    **{
        kind: int(kind.value.removeprefix("u").removeprefix("int"))
        for kind in LogicalKind
        if kind.value.startswith(("int", "uint"))
    },
    **{
        kind: int(kind.value.removeprefix("float"))
        for kind in LogicalKind
        if kind.value.startswith("float")
    },
    **{
        kind: int(kind.value.removeprefix("decimal"))
        for kind in DECIMAL_PRECISIONS
    },
    LogicalKind.DATE32: 32,
    LogicalKind.DATE64: 64,
    LogicalKind.TIME32: 32,
    LogicalKind.TIME64: 64,
    LogicalKind.TIMESTAMP: 64,
    LogicalKind.DURATION: 64,
    LogicalKind.MONTH_INTERVAL: 32,
    LogicalKind.DAY_TIME_INTERVAL: 64,
    LogicalKind.MONTH_DAY_NANO_INTERVAL: 128,
}


@public
@typechecked
@dataclass(frozen=True)
class ResolvedLogicalType:
    """
    title: Canonical physical facts for schema interoperability.
    attributes:
      logical_type:
        type: LogicalType
      c_format:
        type: str
      bit_width:
        type: int | None
      required_features:
        type: tuple[str, Ellipsis]
      required_feature_versions:
        type: tuple[tuple[str, int], Ellipsis]
    """

    logical_type: LogicalType
    c_format: str
    bit_width: int | None
    required_features: tuple[str, ...] = ("core", "array")
    required_feature_versions: tuple[tuple[str, int], ...] = (
        ("core", 0x00010000),
        ("array", 0x00010100),
    )


@public
@typechecked
def logical_c_format(type_: LogicalType) -> str:
    """
    title: Return the C Data format for a validated logical descriptor.
    parameters:
      type_:
        type: LogicalType
    returns:
      type: str
    """
    kind = type_.kind
    if kind in SIMPLE_FORMATS:
        return SIMPLE_FORMATS[kind]
    if kind in {LogicalKind.EXTENSION, LogicalKind.DICTIONARY}:
        return logical_c_format(type_.fields[0].type_)
    if kind in DECIMAL_PRECISIONS:
        precision = cast(int, parameter_value(type_, ParameterKind.PRECISION))
        scale = cast(int, parameter_value(type_, ParameterKind.SCALE))
        return f"d:{precision},{scale},{BIT_WIDTHS[kind]}"
    if kind in {LogicalKind.FIXED_LIST, LogicalKind.FIXED_BINARY}:
        key = (
            ParameterKind.LIST_SIZE
            if kind is LogicalKind.FIXED_LIST
            else ParameterKind.BYTE_WIDTH
        )
        prefix = "+w" if kind is LogicalKind.FIXED_LIST else "w"
        return f"{prefix}:{cast(int, parameter_value(type_, key))}"
    if kind in UNION_KINDS:
        codes = parameter_value(type_, ParameterKind.TYPE_CODES)
        if not isinstance(codes, tuple):
            raise SchemaError("unresolved union codes")
        prefix = "+ud" if kind is LogicalKind.DENSE_UNION else "+us"
        return f"{prefix}:{','.join(str(code) for code in codes)}"
    unit = parameter_value(type_, ParameterKind.TIME_UNIT)
    if not isinstance(unit, TimeUnit):
        raise SchemaError("unresolved temporal unit")
    code = TIME_FORMAT_UNITS[unit]
    if kind is LogicalKind.TIMESTAMP:
        timezone = cast(str, parameter_value(type_, ParameterKind.TIMEZONE))
        return f"ts{code}:{timezone}"
    prefix = "tD" if kind is LogicalKind.DURATION else "tt"
    return f"{prefix}{code}"


@public
@typechecked
def resolve_logical_type(type_: LogicalType) -> ResolvedLogicalType:
    """
    title: Validate once and resolve a type without embedding C++ layouts.
    parameters:
      type_:
        type: LogicalType
    returns:
      type: ResolvedLogicalType
    """
    canonical = canonical_logical_type(type_)
    storage = canonical
    while storage.kind in {LogicalKind.EXTENSION, LogicalKind.DICTIONARY}:
        storage = storage.fields[0].type_
    width = BIT_WIDTHS.get(storage.kind)
    if storage.kind is LogicalKind.FIXED_BINARY:
        size = parameter_value(storage, ParameterKind.BYTE_WIDTH)
        if isinstance(size, int):
            width = size * 8
    return ResolvedLogicalType(canonical, logical_c_format(canonical), width)


@public
@typechecked
def same_columnar_type(lhs: astx.DataType, rhs: astx.DataType) -> bool:
    """
    title: >-
      Compare modeled columnar types structurally rather than by class alone.
    parameters:
      lhs:
        type: astx.DataType
      rhs:
        type: astx.DataType
    returns:
      type: bool
    """
    if type(lhs) is not type(rhs):
        return False
    try:
        if isinstance(lhs, astx.LogicalValueType) and isinstance(
            rhs, astx.LogicalValueType
        ):
            return lhs.nullable == rhs.nullable and canonical_logical_type(
                lhs.element_type
            ) == canonical_logical_type(rhs.element_type)
        if isinstance(lhs, astx.SchemaValueType) and isinstance(
            rhs, astx.SchemaValueType
        ):
            if lhs.schema is None or rhs.schema is None:
                return lhs.schema is rhs.schema
            return canonical_schema(lhs.schema) == canonical_schema(rhs.schema)
    except SchemaError:
        return False
    return False


@private
@typechecked
def columnar_type_children(type_: astx.DataType) -> tuple[astx.DataType, ...]:
    """
    title: Traverse declared type wrappers without looking up semantic symbols.
    parameters:
      type_:
        type: astx.DataType
    returns:
      type: tuple[astx.DataType, Ellipsis]
    """
    if isinstance(type_, astx.UnionType):
        return type_.members
    if isinstance(type_, astx.GeneratorType):
        return (type_.yield_type,)
    if isinstance(type_, astx.TemplateTypeVar):
        return (type_.bound,)
    if isinstance(type_, (astx.ListType, astx.TupleType)):
        return tuple(
            child
            for child in type_.element_types
            if isinstance(child, astx.DataType)
        )
    if isinstance(type_, astx.SetType):
        return (cast(astx.DataType, type_.element_type),)
    if isinstance(type_, astx.DictType):
        return (
            cast(astx.DataType, type_.key_type),
            cast(astx.DataType, type_.value_type),
        )
    if isinstance(type_, (astx.TensorType, astx.SeriesType)):
        return () if type_.element_type is None else (type_.element_type,)
    if isinstance(type_, astx.DataFrameType):
        return tuple(column.type_ for column in type_.columns or ())
    if isinstance(type_, astx.PointerType):
        return () if type_.pointee_type is None else (type_.pointee_type,)
    return ()


@public
@typechecked
def columnar_type_diagnostic(
    type_: astx.DataType, depth: int = 0
) -> str | None:
    """
    title: Reject modeled-only value types before unsupported LLVM lowering.
    parameters:
      type_:
        type: astx.DataType
      depth:
        type: int
    returns:
      type: str | None
    """
    if depth > MAX_SCHEMA_DEPTH:
        return "declared type exceeds maximum nesting depth"
    normalized = normalize_nullable(type_)
    if isinstance(normalized, astx.NullableType):
        if depth:
            return "nullable container elements are not implemented yet"
        if isinstance(normalized.payload_type, astx.ListType) and any(
            isinstance(child, astx.ListType)
            for child in normalized.payload_type.element_types
        ):
            return "nested list owners require recursive element destruction"
        if managed_nullable(normalized) or aggregate_nullable(normalized):
            return columnar_type_diagnostic(normalized.payload_type, depth)
        return nullable_diagnostic(normalized)
    if isinstance(type_, astx.UnionType) and any(
        isinstance(member, astx.NoneType) for member in type_.members
    ):
        return "nullable unions require one distinct non-none payload type"
    try:
        if isinstance(type_, (astx.DataFrameType, astx.SeriesType)):
            if depth:
                return "legacy columnar owners cannot be nested in containers"
            if isinstance(type_, astx.DataFrameType):
                dataframe_schema(type_)
            elif type_.element_type is not None:
                dataframe_element(type_.element_type, type_.nullable)
            return None
        if isinstance(type_, astx.LogicalValueType):
            canonical_logical_type(type_.element_type)
            if isinstance(type_, astx.ScalarType) and type_.nullable:
                return "use scalar[T] | none for optional scalar owners"
            if (
                isinstance(
                    type_,
                    (
                        astx.ScalarType,
                        astx.ArrayType,
                        astx.ArrayBuilderType,
                        astx.ChunkedArrayType,
                    ),
                )
                and array_storage(type_) is not None
            ):
                if depth:
                    return (
                        "array owners cannot be nested in other value "
                        "containers yet"
                    )
                return None
        elif isinstance(type_, astx.SchemaValueType):
            if type_.schema is not None:
                canonical_schema(type_.schema)
            if isinstance(type_, (astx.TableType, astx.RecordBatchType)):
                if depth:
                    return (
                        "tabular owners cannot be nested in value containers"
                    )
                for field in (
                    () if type_.schema is None else type_.schema.fields
                ):
                    if array_storage(astx.ArrayType(field.type_)) is None:
                        return "tabular values require primitive columns"
                return None
        elif isinstance(
            type_,
            (
                astx.SchemaType,
                astx.FieldType,
                astx.TypeDescriptorType,
                astx.CDataType,
            ),
        ):
            if depth:
                return (
                    "descriptor values cannot be nested in value containers; "
                    "element ownership and destruction are not implemented"
                )
            return None
        else:
            for child in columnar_type_children(type_):
                error = columnar_type_diagnostic(child, depth + 1)
                if error is not None:
                    return error
            return None
    except (SchemaError, ValueError) as error:
        return f"invalid columnar descriptor: {error}"
    return (
        f"{type(type_).__name__} is modeled for schema interoperability; "
        "native value construction and lowering are not implemented yet"
    )
