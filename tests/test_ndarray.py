"""
title: Tests for Arx ndarray helpers and ndarray-specific codegen paths.
"""

from __future__ import annotations

import pytest

from arx import ndarray as ndarray_module
from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.ndarray import (
    NdarrayBinding,
    attach_binding,
    binding_from_type,
    build_descriptor_from_literal,
    coerce_expression,
    default_value,
    infer_descriptor,
    is_ndarray_type,
    literal_values,
    ndarray_shape,
    ndarray_type,
)
from arx.parser import Parser
from irx import astx
from irx.analysis.resolved_nodes import SemanticInfo
from irx.buffer import (
    BUFFER_DTYPE_TOKENS,
    BUFFER_VIEW_ELEMENT_TYPE_EXTRA,
    BUFFER_VIEW_METADATA_EXTRA,
)
from llvmlite import ir


def _binding_for(data_type: astx.DataType) -> NdarrayBinding:
    """
    title: Return a non-null ndarray binding for one declared ndarray type.
    parameters:
      data_type:
        type: astx.DataType
    returns:
      type: NdarrayBinding
    """
    binding = binding_from_type(data_type)
    assert binding is not None
    return binding


def _matrix_literal() -> astx.Literal:
    """
    title: Parse one 2x2 integer ndarray literal expression.
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
        (astx.Boolean(), 1, "bool", astx.LiteralBoolean(False)),
        (astx.Int8(), 1, "int8", astx.LiteralInt8(0)),
        (astx.Int16(), 2, "int16", astx.LiteralInt16(0)),
        (astx.Int32(), 4, "int32", astx.LiteralInt32(0)),
        (astx.Int64(), 8, "int64", astx.LiteralInt64(0)),
        (astx.Float32(), 4, "float32", astx.LiteralFloat32(0.0)),
        (astx.Float64(), 8, "float64", astx.LiteralFloat64(0.0)),
    ],
)
def test_ndarray_scalar_helpers_cover_supported_types(
    element_type: astx.DataType,
    expected_size: int,
    dtype_name: str,
    expected_literal: astx.Literal,
) -> None:
    """
    title: Scalar helper tables cover each supported ndarray element type.
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
    assert ndarray_module._element_size_bytes(element_type) == expected_size
    assert (
        ndarray_module._dtype_token(element_type)
        == BUFFER_DTYPE_TOKENS[dtype_name]
    )

    zero = ndarray_module._zero_literal(element_type)
    assert isinstance(zero, type(expected_literal))
    assert zero.value == expected_literal.value

    clone = ndarray_module._clone_scalar_literal(zero)
    assert isinstance(clone, type(expected_literal))
    assert clone.value == expected_literal.value
    assert clone is not zero


def test_ndarray_scalar_helpers_reject_unsupported_types() -> None:
    """
    title: >-
      Scalar helper utilities reject unsupported element and literal kinds.
    """
    with pytest.raises(ValueError, match="support only"):
        ndarray_module._element_size_bytes(astx.String())

    with pytest.raises(ValueError, match="unsupported ndarray element type"):
        ndarray_module._dtype_token(astx.String())

    with pytest.raises(ValueError, match="unsupported ndarray element type"):
        ndarray_module._zero_literal(astx.String())

    with pytest.raises(ValueError, match="unsupported ndarray element type"):
        ndarray_module._clone_scalar_literal(astx.LiteralString("bad"))

    with pytest.raises(ValueError, match="support only"):
        ndarray_module._infer_element_type(astx.LiteralString("bad"))

    with pytest.raises(ValueError, match="unsupported ndarray element type"):
        ndarray_module._validate_scalar_literal(
            astx.LiteralInt32(1),
            astx.String(),
            context="ndarray literal",
        )


@pytest.mark.parametrize(
    ("literal", "expected_type"),
    [
        (astx.LiteralBoolean(True), astx.Boolean),
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
    title: >-
      Element-type inference recognizes each supported scalar literal kind.
    parameters:
      literal:
        type: astx.Literal
      expected_type:
        type: type[astx.DataType]
    """
    inferred = ndarray_module._infer_element_type(literal)
    assert isinstance(inferred, expected_type)


def test_validate_scalar_literal_covers_success_and_error_paths() -> None:
    """
    title: Scalar validation accepts compatible kinds and rejects mismatches.
    """
    ndarray_module._validate_scalar_literal(
        astx.LiteralBoolean(True),
        astx.Boolean(),
        context="matrix",
    )
    ndarray_module._validate_scalar_literal(
        astx.LiteralUTF8Char("A"),
        astx.Int8(),
        context="matrix",
    )
    ndarray_module._validate_scalar_literal(
        astx.LiteralInt32(1),
        astx.Float64(),
        context="matrix",
    )

    with pytest.raises(ValueError, match="expects bool elements"):
        ndarray_module._validate_scalar_literal(
            astx.LiteralInt32(1),
            astx.Boolean(),
            context="matrix",
        )

    with pytest.raises(ValueError, match="expects integer elements"):
        ndarray_module._validate_scalar_literal(
            astx.LiteralFloat32(1.0),
            astx.Int32(),
            context="matrix",
        )

    with pytest.raises(ValueError, match="expects numeric elements"):
        ndarray_module._validate_scalar_literal(
            astx.LiteralUTF8Char("A"),
            astx.Float32(),
            context="matrix",
        )


def test_ndarray_surface_type_and_binding_round_trip() -> None:
    """
    title: Ndarray surface types round-trip through shape and binding metadata.
    """
    target_type = ndarray_type(astx.Int16(), (2, 3))
    binding = _binding_for(target_type)

    assert is_ndarray_type(target_type) is True
    assert ndarray_shape(target_type) == (2, 3)
    assert ndarray_shape(None) is None
    assert is_ndarray_type(astx.ListType([astx.Int16()])) is False
    assert binding_from_type(astx.ListType([astx.Int16()])) is None
    assert binding_from_type(astx.BufferViewType(astx.Int16())) is None

    assert binding.metadata.data.address == 1
    assert binding.metadata.owner.address is None
    assert binding.metadata.dtype.address == BUFFER_DTYPE_TOKENS["int16"]
    assert binding.metadata.ndim == 2
    assert binding.metadata.shape == (2, 3)
    assert binding.metadata.strides == (6, 2)


def test_ndarray_type_rejects_invalid_shapes() -> None:
    """
    title: Ndarray types reject empty and negative declared shapes.
    """
    with pytest.raises(ValueError, match="at least one dimension"):
        ndarray_type(astx.Int32(), ())

    with pytest.raises(ValueError, match="non-negative"):
        ndarray_type(astx.Int32(), (2, -1))


def test_zero_extent_binding_and_default_value_paths() -> None:
    """
    title: Zero-extent bindings and default descriptors preserve ndarray shape.
    """
    empty_binding = _binding_for(ndarray_type(astx.Int32(), (0, 2)))
    assert empty_binding.metadata.data.address is None
    assert empty_binding.metadata.strides == (8, 4)

    descriptor = default_value(ndarray_type(astx.Float32(), (2, 2)))
    values = literal_values(descriptor)
    assert values is not None
    assert len(values) == 4
    assert all(isinstance(value, astx.LiteralFloat32) for value in values)
    assert all(value.value == 0.0 for value in values)
    assert values[0] is not values[1]


def test_attach_binding_and_coerce_expression_cover_branch_paths() -> None:
    """
    title: >-
      Binding attachment and coercion cover semantic and passthrough paths.
    """
    target_type = ndarray_type(astx.Int32(), (2, 2))
    binding = _binding_for(target_type)

    node = astx.Identifier("grid")
    attach_binding(node, binding)
    attach_binding(node, binding)

    semantic = getattr(node, "semantic", None)
    assert isinstance(semantic, SemanticInfo)
    assert semantic.extras[BUFFER_VIEW_METADATA_EXTRA] == binding.metadata
    assert (
        semantic.extras[BUFFER_VIEW_ELEMENT_TYPE_EXTRA] == binding.element_type
    )

    plain_identifier = astx.Identifier("plain")
    assert (
        coerce_expression(plain_identifier, astx.Int32(), context="value")
        is plain_identifier
    )

    descriptor = default_value(target_type)
    assert (
        coerce_expression(descriptor, target_type, context="value")
        is descriptor
    )

    ndarray_identifier = astx.Identifier("ndarray_value")
    assert (
        coerce_expression(ndarray_identifier, target_type, context="value")
        is ndarray_identifier
    )

    coerced = coerce_expression(
        _matrix_literal(),
        target_type,
        context="value",
    )
    assert isinstance(coerced, astx.BufferViewDescriptor)


def test_build_descriptor_and_infer_descriptor_round_trip() -> None:
    """
    title: Descriptor builders preserve flattened ndarray literal payloads.
    """
    target_type = ndarray_type(astx.Int32(), (2, 2))
    descriptor = build_descriptor_from_literal(
        _matrix_literal(),
        target_type,
        context="initializer",
    )
    values = literal_values(descriptor)
    assert values is not None
    assert [value.value for value in values] == [1, 2, 3, 4]
    assert descriptor.metadata.shape == (2, 2)

    inferred = infer_descriptor(_tuple_matrix_literal())
    inferred_values = literal_values(inferred)
    assert inferred_values is not None
    assert inferred.metadata.shape == (2, 2)
    assert isinstance(inferred.type_, astx.BufferViewType)
    assert isinstance(inferred.type_.element_type, astx.Float64)
    assert [value.value for value in inferred_values] == [1.5, 2.5, 3.5, 4.5]


def test_literal_values_rejects_missing_or_invalid_payloads() -> None:
    """
    title: >-
      Literal payload lookup rejects missing and malformed descriptor data.
    """
    binding = _binding_for(ndarray_type(astx.Int32(), (1,)))
    descriptor = astx.BufferViewDescriptor(
        binding.metadata,
        binding.element_type,
    )
    assert literal_values(descriptor) is None

    setattr(
        descriptor,
        ndarray_module.NDARRAY_VALUES_ATTR,
        [astx.LiteralInt32(1)],
    )
    assert literal_values(descriptor) is None

    setattr(
        descriptor,
        ndarray_module.NDARRAY_VALUES_ATTR,
        (astx.Identifier("bad"),),
    )
    assert literal_values(descriptor) is None


def test_ndarray_literal_error_paths_cover_shape_and_type_validation() -> None:
    """
    title: >-
      Literal descriptors reject ragged, empty, mismatched, and bad values.
    """
    ArxIO.string_to_buffer("[[1, 2], [3]]")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    ragged = parser.parse_expression()
    assert isinstance(ragged, astx.Literal)
    with pytest.raises(ValueError, match="regular rectangular shape"):
        infer_descriptor(ragged)

    with pytest.raises(ValueError, match="declared ndarray shape"):
        build_descriptor_from_literal(
            _matrix_literal(),
            ndarray_type(astx.Int32(), (1, 4)),
            context="initializer",
        )

    with pytest.raises(ValueError, match="expects integer elements"):
        build_descriptor_from_literal(
            astx.LiteralList(
                [astx.LiteralFloat32(1.0), astx.LiteralFloat32(2.0)]
            ),
            ndarray_type(astx.Int32(), (2,)),
            context="initializer",
        )

    with pytest.raises(
        ValueError,
        match="cannot infer an ndarray element type from an empty literal",
    ):
        infer_descriptor(astx.LiteralList([]))

    malformed = astx.LiteralList([astx.LiteralInt32(1)])
    setattr(malformed, "elements", [astx.Identifier("bad")])
    with pytest.raises(ValueError, match="literal elements"):
        ndarray_module._flatten_literal(malformed)


def test_ndarray_shape_formatting_helper() -> None:
    """
    title: Shape formatting renders empty and populated ndarray shapes.
    """
    assert ndarray_module._format_shape(()) == "()"
    assert ndarray_module._format_shape((2, 3)) == "(2, 3)"


@pytest.mark.parametrize(
    ("literal", "llvm_type", "expected"),
    [
        (astx.LiteralBoolean(True), ir.IntType(1), 1),
        (astx.LiteralUTF8Char("A"), ir.IntType(8), ord("A")),
        (astx.LiteralInt32(7), ir.IntType(32), 7),
        (astx.LiteralInt32(7), ir.DoubleType(), 7.0),
        (astx.LiteralFloat32(2.5), ir.DoubleType(), 2.5),
    ],
)
def test_ndarray_scalar_constant_branches(
    literal: astx.Literal,
    llvm_type: ir.Type,
    expected: int | float,
) -> None:
    """
    title: Ndarray scalar lowering covers bool, char, int, and float branches.
    parameters:
      literal:
        type: astx.Literal
      llvm_type:
        type: ir.Type
      expected:
        type: int | float
    """
    visitor = ArxBuilder().translator
    constant = visitor._ndarray_scalar_constant(literal, llvm_type)
    assert isinstance(constant, ir.Constant)
    assert constant.constant == expected


def test_ndarray_scalar_constant_rejects_unsupported_literals() -> None:
    """
    title: Ndarray scalar lowering rejects unsupported scalar literal kinds.
    """
    visitor = ArxBuilder().translator
    with pytest.raises(TypeError, match="unsupported ndarray scalar literal"):
        visitor._ndarray_scalar_constant(
            astx.LiteralString("bad"),
            ir.IntType(8),
        )


def test_ndarray_data_pointer_empty_values_returns_null_pointer() -> None:
    """
    title: Empty ndarray payloads lower to a null opaque data pointer.
    """
    visitor = ArxBuilder().translator
    pointer = visitor._ndarray_data_pointer((), astx.Int32())
    assert isinstance(pointer, ir.Constant)
    assert pointer.constant is None
    assert str(pointer) == "i8* null"
