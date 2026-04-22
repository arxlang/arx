"""
title: Ndarray surface helpers for Arx.
summary: >-
  Adapt Arx surface ndarray syntax to the IRx buffer-view substrate while
  keeping user-facing shape and indexing rules local to Arx.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod
from typing import cast

from irx import astx
from irx.analysis.resolved_nodes import SemanticInfo
from irx.buffer import (
    BUFFER_DTYPE_TOKENS,
    BUFFER_VIEW_ELEMENT_TYPE_EXTRA,
    BUFFER_VIEW_METADATA_EXTRA,
    BufferHandle,
    BufferMutability,
    BufferOwnership,
    BufferViewMetadata,
    buffer_view_flags,
)

NDARRAY_SHAPE_ATTR = "_arx_ndarray_shape"
NDARRAY_VALUES_ATTR = "_arx_ndarray_values"


@dataclass(frozen=True)
class NdarrayBinding:
    """
    title: Static ndarray binding metadata.
    attributes:
      element_type:
        type: astx.DataType
      metadata:
        type: BufferViewMetadata
    """

    element_type: astx.DataType
    metadata: BufferViewMetadata


def _shape_of(data_type: astx.DataType) -> tuple[int, ...] | None:
    """
    title: Return the Arx ndarray shape stored on one IRx buffer view type.
    parameters:
      data_type:
        type: astx.DataType
    returns:
      type: tuple[int, Ellipsis] | None
    """
    shape = getattr(data_type, NDARRAY_SHAPE_ATTR, None)
    if isinstance(shape, tuple) and all(isinstance(dim, int) for dim in shape):
        return cast(tuple[int, ...], shape)
    return None


def is_ndarray_type(data_type: astx.DataType | None) -> bool:
    """
    title: Return whether one type is an Arx ndarray surface type.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: bool
    """
    if not isinstance(data_type, astx.BufferViewType):
        return False
    return _shape_of(data_type) is not None


def ndarray_shape(data_type: astx.DataType | None) -> tuple[int, ...] | None:
    """
    title: Return the declared ndarray shape when available.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: tuple[int, Ellipsis] | None
    """
    if data_type is None:
        return None
    return _shape_of(data_type)


def ndarray_type(
    element_type: astx.DataType,
    shape: tuple[int, ...],
) -> astx.BufferViewType:
    """
    title: Build one Arx ndarray surface type.
    parameters:
      element_type:
        type: astx.DataType
      shape:
        type: tuple[int, Ellipsis]
    returns:
      type: astx.BufferViewType
    """
    if not shape:
        raise ValueError("ndarray shape must include at least one dimension")
    if any(dim < 0 for dim in shape):
        raise ValueError("ndarray dimensions must be non-negative")
    _element_size_bytes(element_type)
    result = astx.BufferViewType(element_type)
    setattr(result, NDARRAY_SHAPE_ATTR, shape)
    return result


def binding_from_type(
    data_type: astx.DataType | None,
) -> NdarrayBinding | None:
    """
    title: Build one static ndarray binding from a declared surface type.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: NdarrayBinding | None
    """
    if not isinstance(data_type, astx.BufferViewType):
        return None

    shape = ndarray_shape(data_type)
    element_type = data_type.element_type
    if shape is None or element_type is None:
        return None

    item_size = _element_size_bytes(element_type)
    extent = prod(shape)
    data_handle = BufferHandle(1) if extent > 0 else BufferHandle()
    metadata = BufferViewMetadata(
        data=data_handle,
        owner=BufferHandle(),
        dtype=BufferHandle(_dtype_token(element_type)),
        ndim=len(shape),
        shape=shape,
        strides=_c_contiguous_strides(shape, item_size),
        offset_bytes=0,
        flags=buffer_view_flags(
            BufferOwnership.BORROWED,
            BufferMutability.READONLY,
            c_contiguous=True,
        ),
    )
    return NdarrayBinding(element_type=element_type, metadata=metadata)


def attach_binding(node: astx.AST, binding: NdarrayBinding) -> None:
    """
    title: Attach static ndarray metadata to one AST node.
    parameters:
      node:
        type: astx.AST
      binding:
        type: NdarrayBinding
    """
    info = cast(SemanticInfo | None, getattr(node, "semantic", None))
    if info is None or not isinstance(info, SemanticInfo):
        info = SemanticInfo()
        setattr(node, "semantic", info)
    info.extras[BUFFER_VIEW_METADATA_EXTRA] = binding.metadata
    info.extras[BUFFER_VIEW_ELEMENT_TYPE_EXTRA] = binding.element_type


def coerce_expression(
    expr: astx.Expr,
    target_type: astx.DataType,
    *,
    context: str,
) -> astx.Expr:
    """
    title: Coerce one parsed expression into the declared ndarray surface.
    parameters:
      expr:
        type: astx.Expr
      target_type:
        type: astx.DataType
      context:
        type: str
    returns:
      type: astx.Expr
    """
    if not is_ndarray_type(target_type):
        return expr
    if isinstance(expr, astx.BufferViewDescriptor):
        return expr
    if not isinstance(expr, astx.Literal):
        return expr
    return build_descriptor_from_literal(expr, target_type, context=context)


def default_value(target_type: astx.DataType) -> astx.BufferViewDescriptor:
    """
    title: Build one default ndarray literal for one declared type.
    parameters:
      target_type:
        type: astx.DataType
    returns:
      type: astx.BufferViewDescriptor
    """
    binding = binding_from_type(target_type)
    if binding is None:
        raise ValueError("default ndarray value requires an ndarray type")

    count = prod(binding.metadata.shape)
    scalar = _zero_literal(binding.element_type)
    values = tuple(_clone_scalar_literal(scalar) for _ in range(count))
    return _descriptor_from_values(binding, values)


def build_descriptor_from_literal(
    expr: astx.Literal,
    target_type: astx.DataType,
    *,
    context: str,
) -> astx.BufferViewDescriptor:
    """
    title: Build one ndarray descriptor from one nested literal list.
    parameters:
      expr:
        type: astx.Literal
      target_type:
        type: astx.DataType
      context:
        type: str
    returns:
      type: astx.BufferViewDescriptor
    """
    binding = binding_from_type(target_type)
    if binding is None:
        raise ValueError("ndarray literal target must be an ndarray type")

    shape, values = _flatten_literal(expr)
    if shape != binding.metadata.shape:
        raise ValueError(
            f"{context} has shape {_format_shape(shape)} but the declared "
            f"ndarray shape is {_format_shape(binding.metadata.shape)}"
        )

    for value in values:
        _validate_scalar_literal(value, binding.element_type, context=context)

    return _descriptor_from_values(binding, values)


def infer_descriptor(expr: astx.Literal) -> astx.BufferViewDescriptor:
    """
    title: Infer one ndarray descriptor directly from one literal list.
    parameters:
      expr:
        type: astx.Literal
    returns:
      type: astx.BufferViewDescriptor
    """
    shape, values = _flatten_literal(expr)
    if not values:
        raise ValueError(
            "cannot infer an ndarray element type from an empty literal"
        )

    element_type = _infer_element_type(values[0])
    for value in values:
        _validate_scalar_literal(
            value,
            element_type,
            context="ndarray literal",
        )

    binding = cast(
        NdarrayBinding,
        binding_from_type(ndarray_type(element_type, shape)),
    )
    return _descriptor_from_values(binding, values)


def literal_values(
    node: astx.BufferViewDescriptor,
) -> tuple[astx.Literal, ...] | None:
    """
    title: Return one flattened scalar payload attached to a descriptor.
    parameters:
      node:
        type: astx.BufferViewDescriptor
    returns:
      type: tuple[astx.Literal, Ellipsis] | None
    """
    values = getattr(node, NDARRAY_VALUES_ATTR, None)
    if isinstance(values, tuple) and all(
        isinstance(value, astx.Literal) for value in values
    ):
        return values
    return None


def _descriptor_from_values(
    binding: NdarrayBinding,
    values: tuple[astx.Literal, ...],
) -> astx.BufferViewDescriptor:
    """
    title: Build one descriptor and attach its flattened scalar payload.
    parameters:
      binding:
        type: NdarrayBinding
      values:
        type: tuple[astx.Literal, Ellipsis]
    returns:
      type: astx.BufferViewDescriptor
    """
    descriptor = astx.BufferViewDescriptor(
        binding.metadata,
        binding.element_type,
    )
    setattr(descriptor, NDARRAY_VALUES_ATTR, values)
    attach_binding(descriptor, binding)
    return descriptor


def _c_contiguous_strides(
    shape: tuple[int, ...],
    item_size: int,
) -> tuple[int, ...]:
    """
    title: Build byte strides for one C-contiguous ndarray shape.
    parameters:
      shape:
        type: tuple[int, Ellipsis]
      item_size:
        type: int
    returns:
      type: tuple[int, Ellipsis]
    """
    strides: list[int] = []
    stride = item_size
    for dim in reversed(shape):
        strides.append(stride)
        stride *= max(dim, 1)
    return tuple(reversed(strides))


def _element_size_bytes(element_type: astx.DataType) -> int:
    """
    title: Return the byte width of one supported ndarray scalar type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: int
    """
    if isinstance(element_type, (astx.Boolean, astx.Int8)):
        return 1
    if isinstance(element_type, astx.Int16):
        return 2
    if isinstance(element_type, (astx.Int32, astx.Float32)):
        return 4
    if isinstance(element_type, (astx.Int64, astx.Float64)):
        return 8
    raise ValueError(
        "ndarray element types currently support only bool, i8, i16, "
        "i32, i64, f32, and f64"
    )


def _dtype_token(element_type: astx.DataType) -> int:
    """
    title: Return one IRx dtype token for one ndarray scalar type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: int
    """
    if isinstance(element_type, astx.Boolean):
        return BUFFER_DTYPE_TOKENS["bool"]
    if isinstance(element_type, astx.Int8):
        return BUFFER_DTYPE_TOKENS["int8"]
    if isinstance(element_type, astx.Int16):
        return BUFFER_DTYPE_TOKENS["int16"]
    if isinstance(element_type, astx.Int32):
        return BUFFER_DTYPE_TOKENS["int32"]
    if isinstance(element_type, astx.Int64):
        return BUFFER_DTYPE_TOKENS["int64"]
    if isinstance(element_type, astx.Float32):
        return BUFFER_DTYPE_TOKENS["float32"]
    if isinstance(element_type, astx.Float64):
        return BUFFER_DTYPE_TOKENS["float64"]
    raise ValueError("unsupported ndarray element type")


def _flatten_literal(
    expr: astx.Literal,
) -> tuple[tuple[int, ...], tuple[astx.Literal, ...]]:
    """
    title: Flatten one nested ndarray literal.
    parameters:
      expr:
        type: astx.Literal
    returns:
      type: tuple[tuple[int, Ellipsis], tuple[astx.Literal, Ellipsis]]
    """
    if not isinstance(expr, (astx.LiteralList, astx.LiteralTuple)):
        return (), (expr,)

    if not expr.elements:
        return (0,), ()

    child_shapes: list[tuple[int, ...]] = []
    child_values: list[astx.Literal] = []
    for element in expr.elements:
        if not isinstance(element, astx.Literal):
            raise ValueError("ndarray literals support only literal elements")
        child_shape, flat_values = _flatten_literal(element)
        child_shapes.append(child_shape)
        child_values.extend(flat_values)

    first_shape = child_shapes[0]
    if any(shape != first_shape for shape in child_shapes[1:]):
        raise ValueError(
            "ndarray literals must use a regular rectangular shape"
        )

    return (len(expr.elements), *first_shape), tuple(child_values)


def _infer_element_type(value: astx.Literal) -> astx.DataType:
    """
    title: Infer one ndarray scalar type from one literal.
    parameters:
      value:
        type: astx.Literal
    returns:
      type: astx.DataType
    """
    if isinstance(value, astx.LiteralBoolean):
        return astx.Boolean()
    if isinstance(value, (astx.LiteralInt8, astx.LiteralUTF8Char)):
        return astx.Int8()
    if isinstance(value, astx.LiteralInt16):
        return astx.Int16()
    if isinstance(value, astx.LiteralInt32):
        return astx.Int32()
    if isinstance(value, astx.LiteralInt64):
        return astx.Int64()
    if isinstance(value, astx.LiteralFloat32):
        return astx.Float32()
    if isinstance(value, astx.LiteralFloat64):
        return astx.Float64()
    raise ValueError(
        "ndarray literals currently support only bool, char, integer, "
        "and floating-point scalars"
    )


def _validate_scalar_literal(
    value: astx.Literal,
    element_type: astx.DataType,
    *,
    context: str,
) -> None:
    """
    title: Validate one scalar literal against one ndarray element type.
    parameters:
      value:
        type: astx.Literal
      element_type:
        type: astx.DataType
      context:
        type: str
    """
    if isinstance(element_type, astx.Boolean):
        if isinstance(value, astx.LiteralBoolean):
            return
        raise ValueError(f"{context} expects bool elements")

    if isinstance(
        element_type,
        (astx.Int8, astx.Int16, astx.Int32, astx.Int64),
    ):
        if isinstance(
            value,
            (
                astx.LiteralUTF8Char,
                astx.LiteralInt8,
                astx.LiteralInt16,
                astx.LiteralInt32,
                astx.LiteralInt64,
            ),
        ):
            return
        raise ValueError(
            f"{context} expects integer elements compatible with "
            f"{type(element_type).__name__}"
        )

    if isinstance(element_type, (astx.Float32, astx.Float64)):
        if isinstance(
            value,
            (
                astx.LiteralInt8,
                astx.LiteralInt16,
                astx.LiteralInt32,
                astx.LiteralInt64,
                astx.LiteralFloat32,
                astx.LiteralFloat64,
            ),
        ):
            return
        raise ValueError(
            f"{context} expects numeric elements compatible with "
            f"{type(element_type).__name__}"
        )

    raise ValueError("unsupported ndarray element type")


def _zero_literal(element_type: astx.DataType) -> astx.Literal:
    """
    title: Return one zero-value scalar literal for one ndarray element type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: astx.Literal
    """
    if isinstance(element_type, astx.Boolean):
        return astx.LiteralBoolean(False)
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
    raise ValueError("unsupported ndarray element type")


def _clone_scalar_literal(value: astx.Literal) -> astx.Literal:
    """
    title: Clone one scalar literal so default values do not reuse one node.
    parameters:
      value:
        type: astx.Literal
    returns:
      type: astx.Literal
    """
    if isinstance(value, astx.LiteralBoolean):
        return astx.LiteralBoolean(value.value)
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
    raise ValueError("unsupported ndarray element type")


def _format_shape(shape: tuple[int, ...]) -> str:
    """
    title: Render one ndarray shape for user-facing diagnostics.
    parameters:
      shape:
        type: tuple[int, Ellipsis]
    returns:
      type: str
    """
    if not shape:
        return "()"
    return "(" + ", ".join(str(dim) for dim in shape) + ")"


__all__ = [
    "NdarrayBinding",
    "attach_binding",
    "binding_from_type",
    "build_descriptor_from_literal",
    "coerce_expression",
    "default_value",
    "infer_descriptor",
    "is_ndarray_type",
    "literal_values",
    "ndarray_shape",
    "ndarray_type",
]
