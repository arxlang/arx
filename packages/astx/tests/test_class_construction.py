"""
title: Typed constructor-call modeling independent of language semantics.
"""

import pytest

from typeguard import TypeCheckError

import astx


def test_constructor_arguments_and_location() -> None:
    """
    title: Constructors preserve supplied expressions and source location.
    """
    value = astx.LiteralInt32(7)
    keyword = astx.KeywordArgument("value", value)
    loc = astx.SourceLocation(line=8, col=3)
    call = astx.ClassConstruct(
        "Counter", (value,), keywords=(keyword,), loc=loc
    )
    assert call.args == (value,)
    assert call.keywords == (keyword,)
    assert call.loc == loc
    assert "args" in str(call.get_struct()).lower()
    assert call.get_struct(simplified=True)
    assert str(astx.ClassConstruct("Counter")) == "ClassConstruct[Counter]"


def test_constructor_checks_all_collection_items() -> None:
    """
    title: Invalid constructor arguments fail at the ASTx API boundary.
    """
    with pytest.raises(TypeCheckError):
        astx.ClassConstruct("Counter", (astx.LiteralInt32(1), "bad"))  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError):
        astx.ClassConstruct("Counter", keywords=("bad",))  # type: ignore[arg-type]
