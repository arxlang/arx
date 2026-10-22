"""
title: Nullable AST structure and runtime argument validation.
"""

import pytest

from typeguard import TypeCheckError

import astx


def test_nullable_structure() -> None:
    """
    title: Render stable storage parameters and expression children.
    """
    type_ = astx.NullableType(astx.Int32())
    assert str(type_) == "nullable[Int32]"
    decimal = astx.ColumnType("decimal128", (12, 3))
    assert str(decimal) == "decimal128[12, 3]"
    assert "12" in str(decimal.get_struct())
    value = astx.NullFill(
        astx.NullCheck(astx.LiteralInt32(7)), astx.LiteralBoolean(False)
    )
    assert "NullFill" in str(value.get_struct())
    assert "NullCheck" in str(value.get_struct())
    assert "7" in str(value.get_struct())


def test_nullable_runtime_validation() -> None:
    """
    title: Validate type arguments and every parameter collection member.
    """
    with pytest.raises(TypeCheckError):
        astx.NullableType("i32")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.ColumnType("decimal128", (12, object()))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.NullFill(astx.LiteralInt32(1), 1)  # type: ignore[arg-type]
