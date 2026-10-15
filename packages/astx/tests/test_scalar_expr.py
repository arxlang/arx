"""
title: Backend-neutral scalar descriptors and expression operand validation.
"""

import pytest

from typeguard import TypeCheckError

import astx


def test_scalar_nodes_preserve_parameters() -> None:
    """
    title: Preserve logical parameters and ordered constructor children.
    """
    logical = astx.LogicalType(astx.LogicalKind.STRING)
    literal = astx.ScalarLiteral(
        astx.ScalarType(logical), (astx.LiteralString("λ"),)
    )
    query = astx.ScalarQuery(astx.ScalarOperation.BYTES, (literal,))
    assert literal.type_.element_type is logical
    assert "ScalarLiteral" in str(literal.get_struct())
    assert "scalar_bytes" in str(query.get_struct())
    assert literal.values[0].value == "λ"


def test_scalar_nodes_check_collection_items() -> None:
    """
    title: Runtime checking rejects invalid types inside expression tuples.
    """
    with pytest.raises(TypeCheckError):
        astx.ScalarLiteral(
            astx.ScalarType(astx.LogicalType(astx.LogicalKind.STRING)),
            ("x",),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeCheckError):
        astx.ScalarQuery(astx.ScalarOperation.TEXT, (1,))  # type: ignore[arg-type]
