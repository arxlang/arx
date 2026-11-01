"""
title: Tests for Arx tensor helpers and tensor-specific parser paths.
"""

from __future__ import annotations

import astx
import pytest

from arx import tensor as tensor_module
from arx.tensor import (
    TensorBinding,
    attach_binding,
    binding_from_type,
    default_value,
    is_tensor_type,
    literal_values,
    runtime_tensor_type,
    tensor_shape,
    tensor_type,
)
from irx.analysis.resolved_nodes import SemanticInfo
from irx.buffer import BUFFER_DTYPE_TOKENS
from irx.builtins.collections.tensor import (
    TENSOR_ELEMENT_TYPE_EXTRA,
    TENSOR_FLAGS_EXTRA,
    TENSOR_LAYOUT_EXTRA,
)


def _binding_for(data_type: astx.DataType) -> TensorBinding:
    """
    title: Return a non-null binding for one declared tensor type.
    parameters:
      data_type:
        type: astx.DataType
    returns:
      type: TensorBinding
    """
    binding = binding_from_type(data_type)
    assert binding is not None
    return binding


@pytest.mark.parametrize(
    ("element_type", "expected_size", "dtype_name", "expected_literal"),
    [
        (astx.Int8(), 1, "int8", astx.LiteralInt8(0)),
        (astx.Int16(), 2, "int16", astx.LiteralInt16(0)),
        (astx.Int32(), 4, "int32", astx.LiteralInt32(0)),
        (astx.Int64(), 8, "int64", astx.LiteralInt64(0)),
        (astx.Float32(), 4, "float32", astx.LiteralFloat32(0.0)),
        (astx.Float64(), 8, "float64", astx.LiteralFloat64(0.0)),
    ],
)
def test_tensor_scalar_helpers_cover_supported_types(
    element_type: astx.DataType,
    expected_size: int,
    dtype_name: str,
    expected_literal: astx.Literal,
) -> None:
    """
    title: Scalar helper tables cover each supported tensor element type.
    parameters:
      element_type:
        type: astx.DataType
      expected_size:
        type: int
      dtype_name:
        type: str
      expected_literal:
        type: astx.Literal
    """
    assert tensor_module._element_size_bytes(element_type) == expected_size
    assert (
        tensor_module._dtype_handle(element_type)
        == BUFFER_DTYPE_TOKENS[dtype_name]
    )

    zero = tensor_module._zero_literal(element_type)
    assert isinstance(zero, type(expected_literal))
    assert zero.value == expected_literal.value

    clone = tensor_module._clone_scalar_literal(zero)
    assert isinstance(clone, type(expected_literal))
    assert clone.value == expected_literal.value
    assert clone is not zero


@pytest.mark.parametrize("element_type", [astx.Boolean(), astx.String()])
def test_tensor_scalar_helpers_reject_unsupported_types(
    element_type: astx.DataType,
) -> None:
    """
    title: Scalar helper utilities reject unsupported element kinds.
    parameters:
      element_type:
        type: astx.DataType
    """
    with pytest.raises(ValueError, match=r"support only|unsupported"):
        tensor_module._element_size_bytes(element_type)

    with pytest.raises(ValueError, match=r"support only|unsupported"):
        tensor_module._dtype_handle(element_type)

    with pytest.raises(ValueError, match="unsupported tensor element type"):
        tensor_module._zero_literal(element_type)


def test_tensor_surface_type_and_binding_round_trip() -> None:
    """
    title: Tensor surface types round-trip through shape and binding metadata.
    """
    target_type = tensor_type(astx.Int16(), (2, 3))
    runtime_type = runtime_tensor_type(astx.Int16())
    binding = _binding_for(target_type)

    assert is_tensor_type(target_type) is True
    assert is_tensor_type(runtime_type) is True
    assert is_tensor_type(astx.TensorType(astx.Int16())) is False
    assert tensor_shape(target_type) == (2, 3)
    assert tensor_shape(runtime_type) is None
    assert tensor_shape(None) is None
    assert is_tensor_type(astx.ListType([astx.Int16()])) is False
    assert binding_from_type(astx.ListType([astx.Int16()])) is None
    assert binding_from_type(runtime_type) is None

    assert binding.layout.ndim == 2
    assert binding.layout.shape == (2, 3)
    assert binding.layout.strides == (6, 2)
    assert (
        tensor_module._dtype_handle(binding.element_type)
        == (BUFFER_DTYPE_TOKENS["int16"])
    )


def test_tensor_type_rejects_invalid_shapes_and_elements() -> None:
    """
    title: >-
      Tensor types reject empty shapes, negative shapes, and bool elements.
    """
    with pytest.raises(ValueError, match="at least one dimension"):
        tensor_type(astx.Int32(), ())

    with pytest.raises(ValueError, match="non-negative"):
        tensor_type(astx.Int32(), (2, -1))

    with pytest.raises(ValueError, match="support only"):
        tensor_type(astx.Boolean(), (2,))


def test_zero_extent_binding_and_default_value_paths() -> None:
    """
    title: Zero-extent bindings and default literals preserve tensor shape.
    """
    empty_binding = _binding_for(tensor_type(astx.Int32(), (0, 2)))
    assert empty_binding.layout.strides == (8, 4)

    literal = default_value(tensor_type(astx.Float32(), (2, 2)))
    values = literal_values(literal)
    assert len(values) == 4
    assert all(isinstance(value, astx.LiteralFloat32) for value in values)
    assert all(value.value == 0.0 for value in values)
    assert values[0] is not values[1]
    assert literal.shape == (2, 2)

    with pytest.raises(ValueError, match="static tensor shape"):
        default_value(runtime_tensor_type(astx.Int32()))


def test_attach_binding_covers_semantic_paths() -> None:
    """
    title: Binding attachment preserves tensor layout metadata.
    """
    target_type = tensor_type(astx.Int32(), (2, 2))
    binding = _binding_for(target_type)

    node = astx.Identifier("grid")
    attach_binding(node, binding)
    attach_binding(node, binding)

    semantic = getattr(node, "semantic", None)
    assert isinstance(semantic, SemanticInfo)
    assert semantic.extras[TENSOR_LAYOUT_EXTRA] == binding.layout
    assert semantic.extras[TENSOR_ELEMENT_TYPE_EXTRA] == binding.element_type
    assert semantic.extras[TENSOR_FLAGS_EXTRA] == binding.flags
