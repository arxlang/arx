"""
title: Exact source literals and explicit arithmetic intent.
"""

import pytest

from typeguard import TypeCheckError

import astx


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


def test_source_literals_preserve_untyped_values() -> None:
    """
    title: >-
      Source literals are not prematurely narrowed to concrete typed nodes.
    """
    large = astx.SourceInteger(2**100)
    assert large.value == 2**100
    assert type(large.type_) is astx.DataType
    text = "1.2345678901234567890123456789"
    number = astx.SourceFloat(text)
    assert number.text == text
    assert type(number.type_) is astx.DataType
    assert not isinstance(large, astx.LiteralInt32)


def test_numeric_intent_runtime_validation() -> None:
    """
    title: >-
      Invalid source values and untyped intent strings fail at the AST
      boundary.
    """
    with pytest.raises(TypeCheckError):
        astx.SourceInteger("1")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.SourceFloat(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.Cast(astx.LiteralInt32(1), astx.Int8(), mode="wrap")  # type: ignore[arg-type]
