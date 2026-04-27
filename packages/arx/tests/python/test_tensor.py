"""
title: Tests for Arx tensor helpers and tensor-specific parser paths.
"""

from __future__ import annotations

import astx
import pytest

from arx import tensor as tensor_module
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from arx.tensor import (
    TensorBinding,
    attach_binding,
    binding_from_type,
    build_literal_from_literal,
    coerce_expression,
    default_value,
    infer_literal,
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


def _matrix_literal() -> astx.Literal:
    """
    title: Parse one 2x2 integer tensor literal expression.
    returns:
      type: astx.Literal
    """
    ArxIO.string_to_buffer("[[1, 2], [3, 4]]")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    expr = parser.parse_expression()
    assert isinstance(expr, astx.Literal)
    return expr


def _tuple_matrix_literal() -> astx.LiteralTuple:
    """
    title: Build one 2x2 floating-point tuple matrix literal.
    returns:
      type: astx.LiteralTuple
    """
    return astx.LiteralTuple(
        (
            astx.LiteralTuple(
                (astx.LiteralFloat64(1.5), astx.LiteralFloat64(2.5))
            ),
            astx.LiteralTuple(
                (astx.LiteralFloat64(3.5), astx.LiteralFloat64(4.5))
            ),
        )
    )


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


@pytest.mark.parametrize("literal", [astx.LiteralString("bad")])
def test_tensor_literal_helpers_reject_unsupported_literals(
    literal: astx.Literal,
) -> None:
    """
    title: Literal helpers reject unsupported scalar literal kinds.
    parameters:
      literal:
        type: astx.Literal
    """
    with pytest.raises(ValueError, match="support only"):
        tensor_module._infer_element_type(literal)

    with pytest.raises(ValueError, match="unsupported tensor element type"):
        tensor_module._clone_scalar_literal(literal)

    with pytest.raises(ValueError, match="unsupported tensor element type"):
        tensor_module._validate_scalar_literal(
            astx.LiteralInt32(1),
            astx.String(),
            context="tensor literal",
        )


@pytest.mark.parametrize(
    ("literal", "expected_type"),
    [
        (astx.LiteralUTF8Char("A"), astx.Int8),
        (astx.LiteralInt16(2), astx.Int16),
        (astx.LiteralInt32(3), astx.Int32),
        (astx.LiteralInt64(4), astx.Int64),
        (astx.LiteralFloat32(5.0), astx.Float32),
        (astx.LiteralFloat64(6.0), astx.Float64),
    ],
)
def test_infer_element_type_covers_supported_scalar_literals(
    literal: astx.Literal,
    expected_type: type[astx.DataType],
) -> None:
    """
    title: Element-type inference recognizes supported scalar literal kinds.
    parameters:
      literal:
        type: astx.Literal
      expected_type:
        type: type[astx.DataType]
    """
    inferred = tensor_module._infer_element_type(literal)
    assert isinstance(inferred, expected_type)


@pytest.mark.parametrize("literal", [astx.LiteralBoolean(True)])
def test_infer_element_type_rejects_bool_literals(
    literal: astx.Literal,
) -> None:
    """
    title: Tensor literal inference rejects bool scalars.
    parameters:
      literal:
        type: astx.Literal
    """
    with pytest.raises(ValueError, match="support only"):
        tensor_module._infer_element_type(literal)


def test_validate_scalar_literal_covers_success_and_error_paths() -> None:
    """
    title: Scalar validation accepts compatible kinds and rejects mismatches.
    """
    tensor_module._validate_scalar_literal(
        astx.LiteralUTF8Char("A"),
        astx.Int8(),
        context="matrix",
    )
    tensor_module._validate_scalar_literal(
        astx.LiteralInt32(1),
        astx.Float64(),
        context="matrix",
    )

    with pytest.raises(ValueError, match="expects integer elements"):
        tensor_module._validate_scalar_literal(
            astx.LiteralFloat32(1.0),
            astx.Int32(),
            context="matrix",
        )

    with pytest.raises(ValueError, match="expects numeric elements"):
        tensor_module._validate_scalar_literal(
            astx.LiteralUTF8Char("A"),
            astx.Float32(),
            context="matrix",
        )


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


def test_attach_binding_and_coerce_expression_cover_branch_paths() -> None:
    """
    title: >-
      Binding attachment and coercion cover semantic and passthrough paths.
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

    plain_identifier = astx.Identifier("plain")
    assert (
        coerce_expression(plain_identifier, astx.Int32(), context="value")
        is plain_identifier
    )

    literal = default_value(target_type)
    assert coerce_expression(literal, target_type, context="value") is literal

    tensor_identifier = astx.Identifier("tensor_value")
    assert (
        coerce_expression(tensor_identifier, target_type, context="value")
        is tensor_identifier
    )

    coerced = coerce_expression(
        _matrix_literal(),
        target_type,
        context="value",
    )
    assert isinstance(coerced, astx.TensorLiteral)


def test_build_literal_and_infer_literal_round_trip() -> None:
    """
    title: Literal builders preserve flattened tensor literal payloads.
    """
    target_type = tensor_type(astx.Int32(), (2, 2))
    literal = build_literal_from_literal(
        _matrix_literal(),
        target_type,
        context="initializer",
    )
    values = literal_values(literal)
    assert [value.value for value in values] == [1, 2, 3, 4]
    assert literal.shape == (2, 2)
    assert isinstance(literal.type_, astx.TensorType)
    assert tensor_shape(literal.type_) == (2, 2)

    with pytest.raises(ValueError, match="static tensor shape"):
        build_literal_from_literal(
            astx.LiteralList([astx.LiteralInt32(8), astx.LiteralInt32(9)]),
            runtime_tensor_type(astx.Int32()),
            context="initializer",
        )

    with pytest.raises(ValueError, match="tensor literal target"):
        build_literal_from_literal(
            astx.LiteralList([astx.LiteralInt32(1)]),
            astx.ListType([astx.Int32()]),
            context="initializer",
        )

    inferred = infer_literal(_tuple_matrix_literal())
    inferred_values = literal_values(inferred)
    assert inferred.shape == (2, 2)
    assert isinstance(inferred.type_, astx.TensorType)
    assert isinstance(inferred.type_.element_type, astx.Float64)
    assert [value.value for value in inferred_values] == [
        1.5,
        2.5,
        3.5,
        4.5,
    ]


def test_tensor_literal_error_paths_cover_shape_and_type_validation() -> None:
    """
    title: Literal builders reject ragged, empty, mismatched, and bad values.
    """
    ArxIO.string_to_buffer("[[1, 2], [3]]")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    ragged = parser.parse_expression()
    assert isinstance(ragged, astx.Literal)
    with pytest.raises(ValueError, match="regular rectangular shape"):
        infer_literal(ragged)

    with pytest.raises(ValueError, match="declared tensor shape"):
        build_literal_from_literal(
            _matrix_literal(),
            tensor_type(astx.Int32(), (1, 4)),
            context="initializer",
        )

    with pytest.raises(ValueError, match="expects integer elements"):
        build_literal_from_literal(
            astx.LiteralList(
                [astx.LiteralFloat32(1.0), astx.LiteralFloat32(2.0)]
            ),
            tensor_type(astx.Int32(), (2,)),
            context="initializer",
        )

    with pytest.raises(
        ValueError,
        match="cannot infer a tensor element type from an empty literal",
    ):
        infer_literal(astx.LiteralList([]))

    malformed = astx.LiteralList([astx.LiteralInt32(1)])
    setattr(malformed, "elements", [astx.Identifier("bad")])
    with pytest.raises(ValueError, match="literal elements"):
        tensor_module._flatten_literal(malformed)


def test_tensor_shape_formatting_helper() -> None:
    """
    title: Shape formatting renders empty and populated tensor shapes.
    """
    assert tensor_module._format_shape(()) == "()"
    assert tensor_module._format_shape((2, 3)) == "(2, 3)"
