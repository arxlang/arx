"""
title: Exact source literals and explicit arithmetic intent.
"""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from typeguard import TypeCheckError

import astx

from astx.literals import LiteralFloat, LiteralInteger


def test_numeric_intent_is_structural() -> None:
    """
    title: Wrapping arithmetic and casts retain distinct structural identity.
    """
    left, right = astx.LiteralInt8(1), astx.LiteralInt8(2)
    checked = astx.BinaryOp("+", left, right)
    wrapping = astx.BinaryOp("+", left, right, mode=astx.NumericMode.WRAPPING)
    assert checked.mode is astx.NumericMode.CHECKED
    assert checked.get_struct() != wrapping.get_struct()
    assert (
        astx.Cast(left, astx.Int8()).get_struct()
        != astx.Cast(
            left, astx.Int8(), mode=astx.NumericMode.WRAPPING
        ).get_struct()
    )


def test_contextual_literals_preserve_exact_values() -> None:
    """
    title: >-
      Source literals are not prematurely narrowed to concrete typed nodes.
    """
    large = astx.LiteralInteger(2**100)
    assert large.value == 2**100
    assert type(large.type_) is astx.DataType
    text = "1.2345678901234567890123456789"
    number = astx.LiteralFloat(text)
    assert number.value == Decimal(text)
    assert type(number.type_) is astx.DataType
    assert not isinstance(large, astx.LiteralInt32)


def test_numeric_intent_runtime_validation() -> None:
    """
    title: >-
      Invalid source values and untyped intent strings fail at the AST
      boundary.
    """
    with pytest.raises(TypeCheckError):
        astx.LiteralInteger("1")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.LiteralFloat(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.Cast(astx.LiteralInt32(1), astx.Int8(), mode="wrap")  # type: ignore[arg-type]


def test_decimal_payload_is_exact_and_serializable() -> None:
    """
    title: Decimal construction, copying and representation never round values.
    """
    text = "1.000000059604644830901776231257827021181583404541015625"
    with localcontext() as context:
        context.prec = 2
        number = LiteralFloat(text)
        assert number.value == Decimal(text)
        copied = deepcopy(number)
        assert copied.value == number.value
        assert copied.to_json() == number.to_json()
        assert text in number.to_json()
        assert LiteralFloat(Decimal(text)).value == number.value
    assert LiteralInteger is astx.LiteralInteger
    assert LiteralFloat is astx.LiteralFloat
    assert astx.LiteralFloat("-0").value.is_signed()


@pytest.mark.parametrize("text", ["invalid", "NaN", "Infinity", "-Infinity"])
def test_exact_floating_literal_requires_finite_decimal(text: str) -> None:
    """
    title: Invalid and nonfinite exact payloads fail at the modeling boundary.
    parameters:
      text:
        type: str
    """
    with pytest.raises(ValueError, match="decimal value"):
        astx.LiteralFloat(text)
    with pytest.raises(TypeError, match="Boolean"):
        astx.LiteralInteger(True)
