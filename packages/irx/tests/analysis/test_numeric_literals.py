"""
title: Exact contextual literals and single-rounding binary conversion.
"""

from __future__ import annotations

import math
import struct

from decimal import Decimal, localcontext
from typing import cast

import astx
import pytest

from irx.analysis import SemanticError, SemanticInfo, analyze
from irx.analysis.float_literals import rounded_float
from irx.analysis.numeric_literals import numeric_constant


@pytest.mark.parametrize(
    ("target", "precision", "minimum", "maximum"),
    [
        (astx.Float16(), 11, -14, 15),
        (astx.Float32(), 24, -126, 127),
        (astx.Float64(), 53, -1022, 1023),
    ],
)
def test_exact_rounding_boundaries(
    target: astx.DataType, precision: int, minimum: int, maximum: int
) -> None:
    """
    title: Exact midpoints, subnormals and overflow use nearest-even rounding.
    parameters:
      target:
        type: astx.DataType
      precision:
        type: int
      minimum:
        type: int
      maximum:
        type: int
    """
    # Enough decimal precision to construct every tested dyadic value exactly.
    with localcontext() as context:
        context.prec = 2000
        two = Decimal(2)
        half = two**-precision
        epsilon = two ** (-precision - 60)
        midpoint = Decimal(1) + half
        even_high_midpoint = Decimal(1) + 3 * half
        quantum = two ** (minimum - precision + 1)
        overflow = (two - half) * two**maximum
        maximum_finite = (two - 2 * half) * two**maximum
        cases = [
            (midpoint - epsilon, 1.0),
            (midpoint, 1.0),
            (midpoint + epsilon, float(Decimal(1) + 2 * half)),
            (even_high_midpoint, float(Decimal(1) + 4 * half)),
            (quantum / 2, 0.0),
            (quantum / 2 + quantum * epsilon, float(quantum)),
            (overflow - epsilon, float(maximum_finite)),
            (overflow, math.inf),
        ]
    # Conversion must not depend on the ambient Decimal precision or traps.
    with localcontext() as context:
        context.prec = 2
        for value, expected in cases:
            assert rounded_float(value, target) == expected
            negative = rounded_float(value.copy_negate(), target)
            assert negative == -expected
            assert math.copysign(1.0, negative) < 0


def test_every_finite_half_value_survives_exact_conversion() -> None:
    """
    title: Every finite f16 bit pattern round-trips, including negative zero.
    """
    target = astx.Float16()
    for bits in range(1 << 16):
        value = struct.unpack(">e", bits.to_bytes(2, "big"))[0]
        if not math.isfinite(value):
            continue
        rounded = rounded_float(Decimal.from_float(value), target)
        assert struct.pack(">e", rounded) == bits.to_bytes(2, "big")


@pytest.mark.parametrize(
    "target", [astx.Float16(), astx.Float32(), astx.Float64()]
)
def test_extreme_decimal_exponents_are_bounded(target: astx.DataType) -> None:
    """
    title: Compact huge exponents do not require enormous integer ratios.
    parameters:
      target:
        type: astx.DataType
    """
    assert rounded_float(Decimal("1e1000000000"), target) == math.inf
    tiny = rounded_float(Decimal("-1e-1000000000"), target)
    assert tiny == 0.0
    assert math.copysign(1.0, tiny) < 0


def test_literal_resolution_preserves_payload_and_reanalyzes_context() -> None:
    """
    title: Reusing an exact literal never inherits prior rounding or width.
    """
    exact = Decimal("1.000000059604644830901776231257827021181583404541015625")
    literal = astx.LiteralFloat(exact)
    declared = literal.type_
    original_structure = literal.to_json()
    original_hash = hash(literal)
    narrow = astx.VariableDeclaration("value", astx.Float32(), value=literal)
    analyze(narrow)
    expected = 1.00000011920928955078125
    assert numeric_constant(literal) == expected
    assert literal.value == exact
    assert literal.type_ is declared
    assert literal.to_json() == original_structure
    assert hash(literal) == original_hash

    wide = astx.VariableDeclaration("value", astx.Float64(), value=literal)
    analyze(wide)
    assert numeric_constant(literal) == float(exact)
    assert literal.value == exact
    assert literal.type_ is declared
    # No declaration context: default to f32 again, not the previous f64.
    analyze(literal)
    assert numeric_constant(literal) == expected
    semantic = cast(SemanticInfo, getattr(literal, "semantic"))
    assert isinstance(semantic.resolved_type, astx.Float32)
    assert semantic.literal_context is None
    assert literal.to_json() == original_structure
    assert hash(literal) == original_hash


def test_failed_context_does_not_damage_a_literal() -> None:
    """
    title: Reanalysis after overflow recovers the original exact decimal.
    """
    literal = astx.LiteralFloat("1e100")
    narrow = astx.VariableDeclaration("value", astx.Float32(), value=literal)
    with pytest.raises(SemanticError, match="not representable"):
        analyze(narrow)
    assert numeric_constant(literal) is None
    assert literal.value == Decimal("1e100")
    analyze(astx.VariableDeclaration("value", astx.Float64(), value=literal))
    assert numeric_constant(literal) == float(literal.value)


def test_integer_context_does_not_become_a_declared_type() -> None:
    """
    title: A successful u64 context does not change the default integer domain.
    """
    literal = astx.LiteralInteger(2**63)
    declared = literal.type_
    analyze(astx.VariableDeclaration("value", astx.UInt64(), value=literal))
    assert literal.type_ is declared
    assert literal.value == 2**63
    assert numeric_constant(literal) == 2**63
    with pytest.raises(SemanticError, match="not representable"):
        analyze(literal)


def test_explicitly_typed_payload_is_not_rewritten() -> None:
    """
    title: >-
      Typed literals keep declared values; semantic constants hold rounding.
    """
    original = 0.1
    literal = astx.LiteralFloat32(original)
    analyze(literal)
    assert literal.value == original
    assert (
        numeric_constant(literal)
        == struct.unpack("f", struct.pack("f", original))[0]
    )
    analyze(literal)
    assert literal.value == original


def test_integer_to_float_constant_rounding_does_not_double_round() -> None:
    """
    title: >-
      Constant conversion agrees with direct LLVM integer-to-float rounding.
    """
    value = (1 << 62) + (1 << 38) + 1
    assert rounded_float(value, astx.Float32()) == float((1 << 62) + (1 << 39))


def test_rounding_rejects_unsupported_inputs() -> None:
    """
    title: >-
      Exact rounding fails closed for nonfinite decimals and wrong targets.
    """
    with pytest.raises(TypeError, match="f16, f32, or f64"):
        rounded_float(Decimal(1), astx.Int32())
    with pytest.raises(ValueError, match="finite"):
        rounded_float(Decimal("NaN"), astx.Float32())
