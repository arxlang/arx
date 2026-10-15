"""
title: Shared primitive array storage metadata.
summary: >-
  Define stable primitive type metadata shared by the builtin Arrow C++ backed
  array runtime and higher-level Tensor helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx

from astx.schema import LogicalKind, LogicalType
from public import public

from irx.buffer import (
    BUFFER_DTYPE_BOOL,
    BUFFER_DTYPE_FLOAT32,
    BUFFER_DTYPE_FLOAT64,
    BUFFER_DTYPE_INT8,
    BUFFER_DTYPE_INT16,
    BUFFER_DTYPE_INT32,
    BUFFER_DTYPE_INT64,
    BUFFER_DTYPE_UINT8,
    BUFFER_DTYPE_UINT16,
    BUFFER_DTYPE_UINT32,
    BUFFER_DTYPE_UINT64,
)
from irx.typecheck import typechecked

IRX_ARROW_TYPE_UNKNOWN = 0
IRX_ARROW_TYPE_INT32 = 1
IRX_ARROW_TYPE_INT8 = 2
IRX_ARROW_TYPE_INT16 = 3
IRX_ARROW_TYPE_INT64 = 4
IRX_ARROW_TYPE_UINT8 = 5
IRX_ARROW_TYPE_UINT16 = 6
IRX_ARROW_TYPE_UINT32 = 7
IRX_ARROW_TYPE_UINT64 = 8
IRX_ARROW_TYPE_FLOAT32 = 9
IRX_ARROW_TYPE_FLOAT64 = 10
IRX_ARROW_TYPE_BOOL = 11
IRX_ARROW_TYPE_FLOAT16 = 12


@typechecked
@dataclass(frozen=True)
class ArrayPrimitiveTypeSpec:
    """
    title: Supported builtin array primitive storage type metadata.
    attributes:
      name:
        type: str
      type_id:
        type: int
      dtype_token:
        type: int
      element_size_bytes:
        type: int | None
      buffer_view_compatible:
        type: bool
    """

    name: str
    type_id: int
    dtype_token: int
    element_size_bytes: int | None
    buffer_view_compatible: bool


ARRAY_PRIMITIVE_TYPE_SPECS = {
    spec.name: spec
    for spec in (
        ArrayPrimitiveTypeSpec("float16", IRX_ARROW_TYPE_FLOAT16, 0, 2, False),
        ArrayPrimitiveTypeSpec(
            "int8",
            IRX_ARROW_TYPE_INT8,
            BUFFER_DTYPE_INT8,
            1,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "int16",
            IRX_ARROW_TYPE_INT16,
            BUFFER_DTYPE_INT16,
            2,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "int32",
            IRX_ARROW_TYPE_INT32,
            BUFFER_DTYPE_INT32,
            4,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "int64",
            IRX_ARROW_TYPE_INT64,
            BUFFER_DTYPE_INT64,
            8,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "uint8",
            IRX_ARROW_TYPE_UINT8,
            BUFFER_DTYPE_UINT8,
            1,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "uint16",
            IRX_ARROW_TYPE_UINT16,
            BUFFER_DTYPE_UINT16,
            2,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "uint32",
            IRX_ARROW_TYPE_UINT32,
            BUFFER_DTYPE_UINT32,
            4,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "uint64",
            IRX_ARROW_TYPE_UINT64,
            BUFFER_DTYPE_UINT64,
            8,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "float32",
            IRX_ARROW_TYPE_FLOAT32,
            BUFFER_DTYPE_FLOAT32,
            4,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "float64",
            IRX_ARROW_TYPE_FLOAT64,
            BUFFER_DTYPE_FLOAT64,
            8,
            True,
        ),
        ArrayPrimitiveTypeSpec(
            "bool",
            IRX_ARROW_TYPE_BOOL,
            BUFFER_DTYPE_BOOL,
            None,
            False,
        ),
    )
}


AST_LOGICAL_KINDS: dict[type[astx.DataType], LogicalKind] = {
    astx.NoneType: LogicalKind.NULL,
    astx.Boolean: LogicalKind.BOOL,
    astx.Int8: LogicalKind.INT8,
    astx.Int16: LogicalKind.INT16,
    astx.Int32: LogicalKind.INT32,
    astx.Int64: LogicalKind.INT64,
    astx.UInt8: LogicalKind.UINT8,
    astx.UInt16: LogicalKind.UINT16,
    astx.UInt32: LogicalKind.UINT32,
    astx.UInt64: LogicalKind.UINT64,
    astx.Float16: LogicalKind.FLOAT16,
    astx.Float32: LogicalKind.FLOAT32,
    astx.Float64: LogicalKind.FLOAT64,
    astx.String: LogicalKind.STRING,
    astx.UTF8String: LogicalKind.STRING,
}


@public
@typechecked
def logical_type_for_scalar(type_: astx.DataType) -> LogicalType | None:
    """
    title: Map an existing scalar without guessing temporal parameters.
    parameters:
      type_:
        type: astx.DataType
    returns:
      type: LogicalType | None
    """
    for scalar_class in type(type_).__mro__:
        kind = AST_LOGICAL_KINDS.get(scalar_class)
        if kind is not None:
            return LogicalType(kind)
    return None


__all__ = [
    "ARRAY_PRIMITIVE_TYPE_SPECS",
    "IRX_ARROW_TYPE_BOOL",
    "IRX_ARROW_TYPE_FLOAT16",
    "IRX_ARROW_TYPE_FLOAT32",
    "IRX_ARROW_TYPE_FLOAT64",
    "IRX_ARROW_TYPE_INT8",
    "IRX_ARROW_TYPE_INT16",
    "IRX_ARROW_TYPE_INT32",
    "IRX_ARROW_TYPE_INT64",
    "IRX_ARROW_TYPE_UINT8",
    "IRX_ARROW_TYPE_UINT16",
    "IRX_ARROW_TYPE_UINT32",
    "IRX_ARROW_TYPE_UINT64",
    "IRX_ARROW_TYPE_UNKNOWN",
    "ArrayPrimitiveTypeSpec",
    "logical_type_for_scalar",
]
