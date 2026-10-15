"""
title: Checked constructor and query contracts for owned Arrow scalars.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx

from public import public

from irx.analysis.schema import LIST_KINDS, canonical_logical_type
from irx.analysis.types import is_assignable, is_signed_integer_type, same_type
from irx.typecheck import typechecked

UNION_CONSTRUCTOR_ARITY = 2
BINARY_KINDS = frozenset(
    {
        astx.LogicalKind.STRING,
        astx.LogicalKind.LARGE_STRING,
        astx.LogicalKind.STRING_VIEW,
        astx.LogicalKind.BINARY,
        astx.LogicalKind.LARGE_BINARY,
        astx.LogicalKind.BINARY_VIEW,
        astx.LogicalKind.FIXED_BINARY,
    }
)


@public
@typechecked
@dataclass(frozen=True)
class ResolvedScalar:
    """
    title: Native symbol and normalized operands selected by semantic analysis.
    attributes:
      symbol:
        type: str
      result_type:
        type: astx.DataType
      arguments:
        type: tuple[astx.Expr, Ellipsis]
      argument_types:
        type: tuple[astx.DataType, Ellipsis]
      vector:
        type: astx.DataType | None
      required_feature_version:
        type: int
    """

    symbol: str
    result_type: astx.DataType
    arguments: tuple[astx.Expr, ...]
    argument_types: tuple[astx.DataType, ...]
    vector: astx.DataType | None = None
    required_feature_version: int = 0x00010600


@public
@typechecked
def scalar_constructor(
    type_: astx.ScalarType,
    arguments: tuple[astx.Expr, ...],
    types: tuple[astx.DataType, ...],
) -> ResolvedScalar:
    """
    title: Validate scalar payloads without allowing backend type inference.
    parameters:
      type_:
        type: astx.ScalarType
      arguments:
        type: tuple[astx.Expr, Ellipsis]
      types:
        type: tuple[astx.DataType, Ellipsis]
    returns:
      type: ResolvedScalar
    """
    if len(arguments) != len(types):
        raise ValueError("invalid scalar argument count")
    logical = canonical_logical_type(type_.element_type)
    if any(
        isinstance(value, astx.LiteralString) and "\0" in value.value
        for value in arguments
    ):
        raise ValueError("embedded NUL scalar input requires an array[u8]")
    if type_.nullable:
        raise ValueError("use scalar[T] | none for optional scalar owners")
    kind = logical.kind
    fields = logical.fields
    symbol = "irx_arrow_scalar_parse"
    expected: tuple[astx.DataType, ...] = (astx.String(),)
    vector: astx.DataType | None = None
    if (
        kind in BINARY_KINDS
        and len(types) == 1
        and isinstance(types[0], astx.ArrayType)
    ):
        expected = (astx.ArrayType(astx.LogicalType(astx.LogicalKind.UINT8)),)
        symbol = "irx_arrow_scalar_from_bytes"
    elif kind in LIST_KINDS or kind is astx.LogicalKind.MAP:
        field = fields[0]
        expected = (astx.ArrayType(field.type_, nullable=field.nullable),)
        symbol = "irx_arrow_scalar_from_array"
    elif kind is astx.LogicalKind.STRUCT:
        expected = tuple(
            astx.NullableType(astx.ScalarType(field.type_))
            if field.nullable
            else astx.ScalarType(field.type_)
            for field in fields
        )
        symbol = "irx_arrow_scalar_from_fields"
        vector = astx.OpaqueHandleType("irx_arrow_scalar_handle")
    elif kind is astx.LogicalKind.DICTIONARY:
        expected = (
            astx.ScalarType(fields[0].type_),
            astx.ArrayType(fields[1].type_, nullable=fields[1].nullable),
        )
        symbol = "irx_arrow_scalar_dictionary"
    elif kind in {
        astx.LogicalKind.RUN_END_ENCODED,
        astx.LogicalKind.EXTENSION,
    }:
        field = fields[-1]
        expected = (astx.ScalarType(field.type_),)
        symbol = "irx_arrow_scalar_wrap"
    elif kind in {astx.LogicalKind.DENSE_UNION, astx.LogicalKind.SPARSE_UNION}:
        if len(arguments) != UNION_CONSTRUCTOR_ARITY or not isinstance(
            arguments[0], astx.LiteralString
        ):
            raise ValueError(
                "union scalar requires a literal field name and scalar"
            )
        names = [field.name for field in fields]
        if arguments[0].value not in names:
            raise ValueError("unknown union scalar field")
        index = names.index(arguments[0].value)
        expected = (astx.String(), astx.ScalarType(fields[index].type_))
        symbol = "irx_arrow_scalar_union"
    elif kind in {
        astx.LogicalKind.MONTH_INTERVAL,
        astx.LogicalKind.DAY_TIME_INTERVAL,
        astx.LogicalKind.MONTH_DAY_NANO_INTERVAL,
    }:
        count = {
            astx.LogicalKind.MONTH_INTERVAL: 1,
            astx.LogicalKind.DAY_TIME_INTERVAL: 2,
            astx.LogicalKind.MONTH_DAY_NANO_INTERVAL: 3,
        }[kind]
        if len(types) != count or not all(
            is_signed_integer_type(t) for t in types
        ):
            raise ValueError(
                "interval scalar requires signed integer components"
            )
        symbol = "irx_arrow_scalar_interval"
        expected = (astx.Int64(),) * count
        vector = astx.Int64()
    elif kind is astx.LogicalKind.NULL:
        raise ValueError("null values use none, not a present scalar[null]")
    if len(types) != len(expected) or not all(
        is_assignable(target, actual)
        for target, actual in zip(expected, types, strict=False)
    ):
        raise ValueError("scalar payload does not match its logical type")
    return ResolvedScalar(symbol, type_, arguments, expected, vector)


@public
@typechecked
def scalar_query(
    operation: astx.ScalarOperation,
    arguments: tuple[astx.Expr, ...],
    types: tuple[astx.DataType, ...],
) -> ResolvedScalar:
    """
    title: Resolve scalar inspection and independent child owner results.
    parameters:
      operation:
        type: astx.ScalarOperation
      arguments:
        type: tuple[astx.Expr, Ellipsis]
      types:
        type: tuple[astx.DataType, Ellipsis]
    returns:
      type: ResolvedScalar
    """
    arity = (
        2
        if operation
        in {astx.ScalarOperation.EQUAL, astx.ScalarOperation.FIELD}
        else 1
    )
    if len(types) != arity or not isinstance(types[0], astx.ScalarType):
        raise ValueError("scalar query requires a present typed scalar")
    if len(arguments) != len(types):
        raise ValueError("invalid scalar argument count")
    base = types[0]
    logical = canonical_logical_type(base.element_type)
    result: astx.DataType
    symbol = f"irx_arrow_{operation.value}"
    if operation is astx.ScalarOperation.EQUAL:
        if not same_type(base, types[1]):
            raise ValueError(
                "scalar equality requires identical logical types"
            )
        result = astx.Boolean()
    elif operation is astx.ScalarOperation.TEXT:
        result = astx.String()
    elif operation is astx.ScalarOperation.BYTES:
        if logical.kind not in BINARY_KINDS:
            raise ValueError("scalar_bytes requires a binary or string scalar")
        result = astx.ArrayType(astx.LogicalType(astx.LogicalKind.UINT8))
    elif operation is astx.ScalarOperation.STORAGE:
        if logical.kind not in {
            astx.LogicalKind.EXTENSION,
            astx.LogicalKind.RUN_END_ENCODED,
        }:
            raise ValueError(
                "scalar_storage requires an extension or run-end scalar"
            )
        result = astx.ScalarType(logical.fields[-1].type_)
    elif operation is astx.ScalarOperation.VALUES:
        if logical.kind not in LIST_KINDS | {astx.LogicalKind.MAP}:
            raise ValueError("scalar_values requires a list or map scalar")
        field = logical.fields[0]
        result = astx.ArrayType(field.type_, nullable=field.nullable)
    else:
        if logical.kind is not astx.LogicalKind.STRUCT or not isinstance(
            arguments[1], astx.LiteralString
        ):
            raise ValueError(
                "scalar_field requires a struct and literal field name"
            )
        fields = {field.name: field for field in logical.fields}
        selected = fields.get(arguments[1].value)
        if selected is None:
            raise ValueError("unknown scalar field")
        result = astx.NullableType(astx.ScalarType(selected.type_))
    return ResolvedScalar(symbol, result, arguments, types)
