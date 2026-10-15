"""
title: Backend-neutral immutable columnar array expression contracts.
"""

from __future__ import annotations

import pytest

from typeguard import TypeCheckError

import astx


def test_array_nodes_preserve_structure() -> None:
    """
    title: Keep nullability, ordered elements and operation identity in ASTx.
    """
    type_ = astx.ArrayType(
        astx.LogicalType(astx.LogicalKind.INT32), nullable=True
    )
    literal = astx.ArrayLiteral(
        type_, (astx.LiteralInt32(1), astx.LiteralNone())
    )
    query = astx.ArrayQuery(
        astx.ArrayOperation.AT, (literal, astx.LiteralInt32(1))
    )
    assert literal.type_.nullable
    assert "array_at" in str(query.get_struct())
    assert "nullable" in str(literal.get_struct())


def test_array_nodes_validate_collection_items() -> None:
    """
    title: Reject invalid values even inside annotated argument tuples.
    """
    with pytest.raises(TypeCheckError):
        astx.ArrayLiteral(
            astx.ArrayType(astx.LogicalType(astx.LogicalKind.INT32)), (1,)
        )  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.ArrayQuery(astx.ArrayOperation.LENGTH, ("invalid",))  # type: ignore[arg-type]
