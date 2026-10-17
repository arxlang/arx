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


def test_namespace_constructor_keyword_model() -> None:
    """
    title: >-
      Method syntax preserves constructor keywords without granting meaning.
    """
    keyword = astx.KeywordArgument("file", astx.LiteralString("x"))
    call = astx.MethodCall(
        astx.Identifier("io"), "File", [], keywords=(keyword,)
    )
    assert call.keywords == (keyword,)
    assert "keywords" in str(call.get_struct())
    assert call.get_struct(simplified=True)
    with pytest.raises(TypeCheckError):
        astx.MethodCall(
            astx.Identifier("io"),
            "File",
            [],
            keywords=(keyword, "bad"),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("kind", ["static", "base"])
def test_static_and_base_keywords(kind: str) -> None:
    """
    title: >-
      Named values survive static/base model rendering and type validation.
    parameters:
      kind:
        type: str
    """
    keywords = (astx.KeywordArgument("value", astx.LiteralInt32(1)),)
    if kind == "static":
        call = astx.StaticMethodCall("C", "method", [], keywords=keywords)
        with pytest.raises(TypeCheckError):
            astx.StaticMethodCall("C", "method", [], keywords=(*keywords, 1))  # type: ignore[arg-type]
    else:
        call = astx.BaseMethodCall(
            astx.Identifier("self"), "C", "method", [], keywords=keywords
        )
        with pytest.raises(TypeCheckError):
            astx.BaseMethodCall(
                astx.Identifier("self"),
                "C",
                "method",
                [],
                keywords=(*keywords, 1),
            )  # type: ignore[arg-type]
    assert call.keywords == keywords
    assert "keywords" in str(call.get_struct())


def test_function_call_materializes_iterable_once() -> None:
    """
    title: Repeated analysis does not consume or lose generator operands.
    """
    value = astx.LiteralInt32(1)
    call = astx.FunctionCall("f", (item for item in (value,)))
    assert tuple(call.args) == (value,)
    assert tuple(call.args) == (value,)
    with pytest.raises(TypeCheckError):
        astx.FunctionCall("f", (item for item in (value, 1)))  # type: ignore[arg-type]
