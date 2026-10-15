"""
title: Nullable normalization and supported scalar or opaque owner payloads.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx

from public import public

from irx.analysis.array_values import array_storage
from irx.typecheck import typechecked

PRIMITIVE_PAYLOADS = (
    astx.Boolean,
    astx.Int8,
    astx.Int16,
    astx.Int32,
    astx.Int64,
    astx.UInt8,
    astx.UInt16,
    astx.UInt32,
    astx.UInt64,
    astx.Float16,
    astx.Float32,
    astx.Float64,
)


@public
@typechecked
@dataclass(frozen=True)
class ResolvedNullableOperator:
    """
    title: Payload conversion and validity policy resolved before lowering.
    attributes:
      op_code:
        type: str
      lhs_type:
        type: astx.DataType
      rhs_type:
        type: astx.DataType | None
      operand_type:
        type: astx.DataType
      payload_type:
        type: astx.DataType
      kleene:
        type: bool
    """

    op_code: str
    lhs_type: astx.DataType
    rhs_type: astx.DataType | None
    operand_type: astx.DataType
    payload_type: astx.DataType
    kleene: bool = False


@public
@typechecked
@dataclass(frozen=True)
class ResolvedNullableQuery:
    """
    title: Validated validity operation and its supported payload type.
    attributes:
      operation:
        type: astx.NullableOperation
      payload_type:
        type: astx.DataType
    """

    operation: astx.NullableOperation
    payload_type: astx.DataType


@public
@typechecked
def normalize_nullable(type_: astx.DataType | None) -> astx.DataType | None:
    """
    title: Normalize an exact nullable union without changing general unions.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: astx.DataType | None
    """
    if not isinstance(type_, astx.UnionType):
        return type_
    members: list[astx.DataType] = []
    pending = [
        (member, frozenset({id(type_)})) for member in reversed(type_.members)
    ]
    has_null = False
    while pending:
        member, ancestors = pending.pop()
        if isinstance(member, astx.UnionType):
            # Do not turn an invalid cyclic type into a valid nullable type.
            if id(member) in ancestors:
                return type_
            lineage = ancestors | {id(member)}
            pending.extend(
                (child, lineage) for child in reversed(member.members)
            )
        elif isinstance(member, astx.NoneType):
            has_null = True
        elif not any(
            member is other
            or (
                type(member) in PRIMITIVE_PAYLOADS
                and type(member) is type(other)
            )
            for other in members
        ):
            members.append(member)
    if has_null and len(members) == 1:
        return astx.NullableType(members[0], alias_name=type_.alias_name)
    return type_


@public
@typechecked
def nullable_diagnostic(type_: astx.NullableType) -> str | None:
    """
    title: Reject payloads without an implemented value and lifetime contract.
    parameters:
      type_:
        type: astx.NullableType
    returns:
      type: str | None
    """
    if managed_nullable(type_) or aggregate_nullable(type_):
        return None
    if type(type_.payload_type) not in PRIMITIVE_PAYLOADS:
        return (
            "nullable values require primitive numeric or Boolean payloads "
            "or implemented managed owners; this payload has no native "
            "lifetime contract"
        )
    return None


@public
@typechecked
def aggregate_nullable(type_: astx.DataType | None) -> bool:
    """
    title: Identify optional by-value owners requiring separate validity.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: bool
    """
    return isinstance(type_, astx.NullableType) and isinstance(
        type_.payload_type,
        (astx.ListType, astx.TensorType, astx.BufferViewType),
    )


@public
@typechecked
def managed_nullable(type_: astx.DataType | None) -> bool:
    """
    title: Identify nullable opaque owners with a reserved null-pointer niche.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: bool
    """
    if not isinstance(type_, astx.NullableType):
        return False
    payload = type_.payload_type
    if isinstance(
        payload, (astx.ArrayType, astx.ArrayBuilderType, astx.ChunkedArrayType)
    ):
        return array_storage(payload) is not None
    return isinstance(
        payload,
        (
            astx.String,
            astx.ClassType,
            astx.CDataType,
            astx.DataFrameType,
            astx.SeriesType,
            astx.ScalarType,
            astx.TableType,
            astx.RecordBatchType,
            astx.SchemaType,
            astx.FieldType,
            astx.TypeDescriptorType,
        ),
    )
