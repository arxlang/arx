"""
title: Backend-neutral row-container schemas and closed operations.
"""

from __future__ import annotations

import pytest

from typeguard import TypeCheckError

import astx


def test_tabular_nodes_preserve_empty_and_dynamic_schemas() -> None:
    """
    title: Distinguish a known empty schema from a checked runtime schema.
    """
    empty = astx.TableType(astx.Schema(()))
    dynamic = astx.TableType()
    assert empty.get_struct() != dynamic.get_struct()
    literal = astx.TabularLiteral(empty, (astx.LiteralInt64(3),))
    query = astx.TabularQuery(astx.TabularOperation.ROWS, (literal,))
    assert "TabularLiteral" in str(literal.get_struct())
    assert "num_rows" in str(query.get_struct())
    assert len(literal.values) == 1


def test_tabular_nodes_check_collection_items() -> None:
    """
    title: Fail closed on invalid expression types inside argument tuples.
    """
    with pytest.raises(TypeCheckError):
        astx.TabularLiteral(astx.TableType(), (1,))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.TabularQuery(astx.TabularOperation.ROWS, ("x",))  # type: ignore[arg-type]
