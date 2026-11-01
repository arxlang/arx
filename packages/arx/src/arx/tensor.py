"""
title: Tensor surface helpers for Arx.
summary: >-
  Adapt Arx surface tensor syntax to IRx Tensor nodes while keeping user-facing
  shape and indexing rules local to Arx.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod
from typing import cast

import astx

from irx.analysis.resolved_nodes import SemanticInfo
from irx.buffer import BufferMutability, BufferOwnership, buffer_view_flags
from irx.builtins.collections.tensor import (
    TENSOR_ELEMENT_TYPE_EXTRA,
    TENSOR_FLAGS_EXTRA,
    TENSOR_LAYOUT_EXTRA,
    TensorLayout,
    tensor_buffer_dtype,
    tensor_default_strides,
    tensor_element_size_bytes,
    tensor_is_c_contiguous,
    tensor_is_f_contiguous,
)

TENSOR_SHAPE_ATTR = "_arx_tensor_shape"
TENSOR_SURFACE_ATTR = "_arx_tensor_surface"


@dataclass(frozen=True)
class TensorBinding:
    """
    title: Static tensor binding metadata.
    attributes:
      element_type:
        type: astx.DataType
      layout:
        type: TensorLayout
      flags:
        type: int
    """

    element_type: astx.DataType
    layout: TensorLayout
    flags: int


def _shape_of(data_type: astx.DataType) -> tuple[int, ...] | None:
    """
    title: Return the declared tensor shape stored on one type.
    parameters:
      data_type:
        type: astx.DataType
    returns:
      type: tuple[int, Ellipsis] | None
    """
    if isinstance(data_type, astx.TensorType) and data_type.shape is not None:
        return data_type.shape

    shape = getattr(data_type, TENSOR_SHAPE_ATTR, None)
    if isinstance(shape, tuple) and all(isinstance(dim, int) for dim in shape):
        return cast(tuple[int, ...], shape)
    return None


def _mark_tensor_type(
    data_type: astx.TensorType,
    shape: tuple[int, ...] | None,
) -> astx.TensorType:
    """
    title: Mark one IRx TensorType as originating from Arx syntax.
    parameters:
      data_type:
        type: astx.TensorType
      shape:
        type: tuple[int, Ellipsis] | None
    returns:
      type: astx.TensorType
    """
    setattr(data_type, TENSOR_SURFACE_ATTR, True)
    data_type.shape = shape
    if shape is not None:
        setattr(data_type, TENSOR_SHAPE_ATTR, shape)
    return data_type


def is_tensor_type(data_type: astx.DataType | None) -> bool:
    """
    title: Return whether one type is an Arx tensor surface type.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: bool
    """
    return (
        isinstance(data_type, astx.TensorType)
        and getattr(data_type, TENSOR_SURFACE_ATTR, False) is True
    )


def tensor_shape(data_type: astx.DataType | None) -> tuple[int, ...] | None:
    """
    title: Return the declared tensor shape when available.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: tuple[int, Ellipsis] | None
    """
    if data_type is None:
        return None
    return _shape_of(data_type)


def tensor_type(
    element_type: astx.DataType,
    shape: tuple[int, ...],
) -> astx.TensorType:
    """
    title: Build one static-shape tensor surface type.
    parameters:
      element_type:
        type: astx.DataType
      shape:
        type: tuple[int, Ellipsis]
    returns:
      type: astx.TensorType
    """
    _element_size_bytes(element_type)
    if not shape:
        raise ValueError("tensor shapes must include at least one dimension")
    if any(dim < 0 for dim in shape):
        raise ValueError("tensor dimensions must be non-negative")
    return _mark_tensor_type(
        astx.TensorType(element_type, shape=shape),
        shape,
    )


def runtime_tensor_type(element_type: astx.DataType) -> astx.TensorType:
    """
    title: Build one runtime-shaped tensor surface type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: astx.TensorType
    """
    _element_size_bytes(element_type)
    return _mark_tensor_type(astx.TensorType(element_type), None)


def binding_from_type(
    data_type: astx.DataType | None,
) -> TensorBinding | None:
    """
    title: Build one static tensor binding from one declared type.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: TensorBinding | None
    """
    if not is_tensor_type(data_type):
        return None

    shape = tensor_shape(data_type)
    element_type = cast(astx.TensorType, data_type).element_type
    if shape is None or element_type is None:
        return None

    item_size = _element_size_bytes(element_type)
    layout = TensorLayout(
        shape=shape,
        strides=tensor_default_strides(shape, item_size),
        offset_bytes=0,
    )
    flags = buffer_view_flags(
        BufferOwnership.EXTERNAL_OWNER,
        BufferMutability.READONLY,
        c_contiguous=tensor_is_c_contiguous(layout, item_size),
        f_contiguous=tensor_is_f_contiguous(layout, item_size),
    )
    return TensorBinding(
        element_type=element_type,
        layout=layout,
        flags=flags,
    )


def attach_binding(node: astx.AST, binding: TensorBinding) -> None:
    """
    title: Attach static tensor metadata to one AST node.
    parameters:
      node:
        type: astx.AST
      binding:
        type: TensorBinding
    """
    info = cast(SemanticInfo | None, getattr(node, "semantic", None))
    if info is None or not isinstance(info, SemanticInfo):
        info = SemanticInfo()
        setattr(node, "semantic", info)
    info.extras[TENSOR_LAYOUT_EXTRA] = binding.layout
    info.extras[TENSOR_ELEMENT_TYPE_EXTRA] = binding.element_type
    info.extras[TENSOR_FLAGS_EXTRA] = binding.flags


def default_value(target_type: astx.DataType) -> astx.TensorLiteral:
    """
    title: Build one default tensor literal for one declared type.
    parameters:
      target_type:
        type: astx.DataType
    returns:
      type: astx.TensorLiteral
    """
    binding = binding_from_type(target_type)
    if binding is None:
        raise ValueError("default tensor value requires a static tensor shape")

    count = prod(binding.layout.shape)
    scalar = _zero_literal(binding.element_type)
    values = tuple(_clone_scalar_literal(scalar) for _ in range(count))
    return _literal_from_values(binding, values)


def literal_values(
    node: astx.TensorLiteral,
) -> tuple[astx.AST, ...]:
    """
    title: Return one flattened scalar payload from a tensor literal.
    parameters:
      node:
        type: astx.TensorLiteral
    returns:
      type: tuple[astx.AST, Ellipsis]
    """
    return tuple(node.values)


def _literal_from_values(
    binding: TensorBinding,
    values: tuple[astx.Literal, ...],
) -> astx.TensorLiteral:
    """
    title: Build one TensorLiteral and attach static metadata.
    parameters:
      binding:
        type: TensorBinding
      values:
        type: tuple[astx.Literal, Ellipsis]
    returns:
      type: astx.TensorLiteral
    """
    literal = astx.TensorLiteral(
        values,
        element_type=binding.element_type,
        shape=binding.layout.shape,
        strides=binding.layout.strides,
        offset_bytes=binding.layout.offset_bytes,
    )
    _mark_tensor_type(literal.type_, binding.layout.shape)
    attach_binding(literal, binding)
    return literal


def _element_size_bytes(element_type: astx.DataType) -> int:
    """
    title: Return the byte width of one supported tensor scalar type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: int
    """
    if not isinstance(
        element_type,
        (
            astx.Int8,
            astx.Int16,
            astx.Int32,
            astx.Int64,
            astx.Float32,
            astx.Float64,
        ),
    ):
        raise ValueError(
            "tensor element types currently support only i8, i16, i32, "
            "i64, f32, and f64"
        )

    size = tensor_element_size_bytes(element_type)
    if size is None:
        raise ValueError("unsupported tensor element type")
    return size


def _dtype_handle(element_type: astx.DataType) -> int:
    """
    title: Return one IRx dtype token for one tensor scalar type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: int
    """
    _element_size_bytes(element_type)
    handle = tensor_buffer_dtype(element_type)
    if handle is None or handle.address is None:
        raise ValueError("unsupported tensor element type")
    return handle.address


def _zero_literal(element_type: astx.DataType) -> astx.Literal:
    """
    title: Return one zero-value scalar literal for one tensor type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: astx.Literal
    """
    if isinstance(element_type, astx.Int8):
        return astx.LiteralInt8(0)
    if isinstance(element_type, astx.Int16):
        return astx.LiteralInt16(0)
    if isinstance(element_type, astx.Int32):
        return astx.LiteralInt32(0)
    if isinstance(element_type, astx.Int64):
        return astx.LiteralInt64(0)
    if isinstance(element_type, astx.Float32):
        return astx.LiteralFloat32(0.0)
    if isinstance(element_type, astx.Float64):
        return astx.LiteralFloat64(0.0)
    raise ValueError("unsupported tensor element type")


def _clone_scalar_literal(value: astx.Literal) -> astx.Literal:
    """
    title: Clone one scalar literal so default values do not reuse one node.
    parameters:
      value:
        type: astx.Literal
    returns:
      type: astx.Literal
    """
    if isinstance(value, astx.LiteralInteger):
        return astx.LiteralInteger(value.value, loc=value.loc)
    if isinstance(value, astx.LiteralFloat):
        return astx.LiteralFloat(value.value, loc=value.loc)
    if isinstance(value, astx.LiteralInt8):
        return astx.LiteralInt8(value.value)
    if isinstance(value, astx.LiteralInt16):
        return astx.LiteralInt16(value.value)
    if isinstance(value, astx.LiteralInt32):
        return astx.LiteralInt32(value.value)
    if isinstance(value, astx.LiteralInt64):
        return astx.LiteralInt64(value.value)
    if isinstance(value, astx.LiteralFloat32):
        return astx.LiteralFloat32(value.value)
    if isinstance(value, astx.LiteralFloat64):
        return astx.LiteralFloat64(value.value)
    raise ValueError("unsupported tensor element type")


__all__ = [
    "TensorBinding",
    "attach_binding",
    "binding_from_type",
    "default_value",
    "is_tensor_type",
    "literal_values",
    "runtime_tensor_type",
    "tensor_shape",
    "tensor_type",
]
