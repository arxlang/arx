"""
title: Structural and runtime-typing contracts for exception nodes.
"""

from collections.abc import Iterable
from typing import cast

import pytest

from typeguard import TypeCheckError

import astx


@pytest.mark.parametrize("simplified", [False, True])
def test_raise_cause_is_distinct_from_absence(simplified: bool) -> None:
    """
    title: An explicit null cause survives representation and traversal.
    parameters:
      simplified:
        type: bool
    """
    exception = astx.Identifier("problem")
    implicit = astx.ThrowStmt(exception)
    suppressed = astx.ThrowStmt(exception, cause=astx.LiteralNone())
    assert implicit.cause is None
    assert isinstance(suppressed.cause, astx.LiteralNone)
    assert "cause" not in str(implicit.get_struct(simplified))
    assert "cause" in str(suppressed.get_struct(simplified))
    assert astx.ThrowStmt().get_struct(simplified)


def test_handler_preserves_empty_type_list() -> None:
    """
    title: Invalid empty type lists must not turn into catch-all handlers.
    """
    bare = astx.CatchHandlerStmt(astx.Block())
    empty = astx.CatchHandlerStmt(astx.Block(), types=[])
    assert bare.types is None
    assert empty.types is not None
    assert not empty.types.nodes
    assert "types" in str(empty.get_struct())


@pytest.mark.parametrize("simplified", [False, True])
def test_try_preserves_all_clauses(simplified: bool) -> None:
    """
    title: Qualified handlers, else, and finalization remain separate children.
    parameters:
      simplified:
        type: bool
    """
    reference = astx.FieldAccess(astx.Identifier("package"), "Problem")
    handler = astx.CatchHandlerStmt(astx.Block(), types=[reference])
    otherwise = astx.Block()
    finalizer = astx.FinallyHandlerStmt(astx.Block())
    node = astx.ExceptionHandlerStmt(
        astx.Block(), [handler], finalizer, else_body=otherwise
    )
    assert node.else_body is otherwise
    assert node.finally_handler is finalizer
    assert node.handlers.nodes == [handler]
    assert handler.types is not None
    assert handler.types.nodes == [reference]
    result = str(node.get_struct(simplified))
    assert "else_body" in result
    assert "finally_handler" in result


def test_raise_rejects_invalid_cause_type() -> None:
    """
    title: Runtime argument checking rejects non-expression cause values.
    """
    with pytest.raises(TypeCheckError):
        astx.ThrowStmt(cause=cast(astx.Expr, "invalid"))


def test_handler_checks_every_list_item() -> None:
    """
    title: Collection typing checks non-first handler types too.
    """
    with pytest.raises(TypeError, match="handler types"):
        astx.CatchHandlerStmt(
            astx.Block(),
            types=cast(
                Iterable[astx.Expr], [astx.Identifier("Problem"), "invalid"]
            ),
        )


def test_try_checks_every_handler() -> None:
    """
    title: An invalid non-first handler is rejected before storing the tree.
    """
    with pytest.raises(TypeError, match="handlers must"):
        astx.ExceptionHandlerStmt(
            astx.Block(),
            cast(
                Iterable[astx.CatchHandlerStmt],
                [astx.CatchHandlerStmt(astx.Block()), "invalid"],
            ),
        )


def test_try_rejects_invalid_else_body() -> None:
    """
    title: The else suite must be a block rather than an arbitrary expression.
    """
    with pytest.raises(TypeCheckError):
        astx.ExceptionHandlerStmt(
            astx.Block(), [], else_body=cast(astx.Block, "invalid")
        )


@pytest.mark.parametrize("container", [False, True])
def test_lazy_and_astnodes_handler_types_are_checked(container: bool) -> None:
    """
    title: Validate collection items beyond Typeguard's builtin containers.
    parameters:
      container:
        type: bool
    """
    values = [astx.Identifier("Problem"), astx.ThrowStmt()]
    types: Iterable[astx.Expr]
    if container:
        nodes = astx.ASTNodes[astx.Expr]()
        nodes.nodes = cast(list[astx.Expr], values)
        types = nodes
    else:
        types = cast(Iterable[astx.Expr], iter(values))
    with pytest.raises(TypeError, match="handler types"):
        astx.CatchHandlerStmt(astx.Block(), types=types)


@pytest.mark.parametrize("container", [False, True])
def test_lazy_and_astnodes_handlers_are_checked(container: bool) -> None:
    """
    title: Invalid nested handler lists cannot reach structure generation.
    parameters:
      container:
        type: bool
    """
    values = [astx.CatchHandlerStmt(astx.Block()), astx.ThrowStmt()]
    handlers: Iterable[astx.CatchHandlerStmt]
    if container:
        nodes = astx.ASTNodes[astx.CatchHandlerStmt]()
        nodes.nodes = cast(list[astx.CatchHandlerStmt], values)
        handlers = nodes
    else:
        handlers = cast(Iterable[astx.CatchHandlerStmt], iter(values))
    with pytest.raises(TypeError, match="handlers must"):
        astx.ExceptionHandlerStmt(astx.Block(), handlers)
