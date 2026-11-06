"""
title: Explicit nominal AST handlers compose without shared dispatch mutation.
"""

from __future__ import annotations

import gc
import weakref

import astx
import pytest

from astx.base import ReprStruct
from irx.extensions import ConfigurationError
from irx.extensions.nodes import (
    NodeHandler,
    ScopedNodeDispatch,
    contribute_node,
)
from irx.typecheck import typechecked
from plum import dispatch
from public import private
from typeguard import TypeCheckError


@private
class Left(astx.AST):
    """
    title: One explicitly modeled feature input.
    """

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Supply the modeled AST representation contract.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return {"Left": {}}


@private
class Right(astx.AST):
    """
    title: An independent feature input.
    """

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Supply the modeled AST representation contract.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return {"Right": {}}


@private
class Combined(Left, Right):
    """
    title: A later nominal overlap diagnosed by Plum at invocation.
    """


@private
class LiteralSubtype(astx.LiteralInt32):
    """
    title: A nominal subtype selected through an existing handler.
    """


@private
class Provider:
    """
    title: A feature-local visitor that retains only its invocation state.
    attributes:
      seen:
        type: list[str]
    """

    seen: list[str]

    def __init__(self) -> None:
        """
        title: Start one isolated feature instance.
        """
        self.seen = []

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject unsupported inputs even within the feature family.
        parameters:
          node:
            type: astx.AST
        """
        reject(node)

    @dispatch
    def visit(self, node: astx.LiteralInt32) -> None:
        """
        title: Record one supported integer literal.
        parameters:
          node:
            type: astx.LiteralInt32
        """
        self.seen.append(f"integer:{node.value}")

    @dispatch
    def visit(self, node: astx.LiteralString) -> None:
        """
        title: Record a second explicitly exported input.
        parameters:
          node:
            type: astx.LiteralString
        """
        self.seen.append(f"text:{node.value}")


@typechecked
def reject(node: astx.AST) -> None:
    """
    title: Keep unsupported-node policy owned by the composing phase.
    parameters:
      node:
        type: astx.AST
    """
    raise NotImplementedError(f"unsupported {type(node).__name__}")


def bindings(provider: Provider) -> tuple[NodeHandler, ...]:
    """
    title: Export supported signatures without scanning dispatch internals.
    parameters:
      provider:
        type: Provider
    returns:
      type: tuple[NodeHandler, Ellipsis]
    """
    return (
        contribute_node(
            "literal.integer",
            "test.literals",
            "analysis",
            astx.LiteralInt32,
            provider.visit,
            source=f"{__name__}.Provider.visit",
        ),
        contribute_node(
            "literal.text",
            "test.literals",
            "analysis",
            astx.LiteralString,
            provider.visit,
            source=f"{__name__}.Provider.visit",
        ),
    )


def test_local_dispatch_preserves_specificity_and_instance_isolation() -> None:
    """
    title: >-
      Every compiler binds fresh state while retaining nominal specificity.
    """
    first, second = Provider(), Provider()
    first_bindings = bindings(first)
    dispatcher = ScopedNodeDispatch("analysis", first_bindings, reject)
    other = ScopedNodeDispatch("analysis", bindings(second), reject)
    assert dispatcher.selector is other.selector
    assert dispatcher.cache is not other.cache
    dispatcher.visit(LiteralSubtype(7))
    assert LiteralSubtype not in other.cache
    other.visit(astx.LiteralString("second"))
    assert first.seen == ["integer:7"]
    assert second.seen == ["text:second"]
    assert dispatcher.explain(LiteralSubtype) is first_bindings[0]
    assert dispatcher.explain(Left) is None
    assert first.seen == ["integer:7"]
    with pytest.raises(NotImplementedError, match="unsupported Left"):
        dispatcher.visit(Left())
    prior_provider = weakref.ref(first)
    prior_dispatcher = weakref.ref(dispatcher)
    del first, dispatcher, first_bindings
    gc.collect()
    assert prior_provider() is None
    assert prior_dispatcher() is None
    other.visit(astx.LiteralInt32(9))
    assert second.seen == ["text:second", "integer:9"]


def test_invalid_node_contributions_fail_before_use() -> None:
    """
    title: Exact conflicts, invalid phases, and malformed members fail early.
    """
    handlers = bindings(Provider())
    with pytest.raises(ConfigurationError, match="duplicate"):
        ScopedNodeDispatch("analysis", (*handlers, handlers[0]), reject)
    with pytest.raises(ConfigurationError, match="wrong phase"):
        ScopedNodeDispatch("lowering", handlers, reject)
    with pytest.raises(TypeCheckError):
        ScopedNodeDispatch("analysis", (*handlers, object()), reject)
    with pytest.raises(TypeError, match="invalid node"):
        handlers[0].implementation(astx.LiteralString("wrong"))
    with pytest.raises(ConfigurationError, match="promised Left"):
        contribute_node(
            "missing",
            "test",
            "analysis",
            Left,
            Provider().visit,
            source=__name__,
        )


@typechecked
def left(node: Left) -> None:
    """
    title: Supply one incomparable nominal handler.
    parameters:
      node:
        type: Left
    """
    del node


@typechecked
def right(node: Right) -> None:
    """
    title: Supply another incomparable nominal handler.
    parameters:
      node:
        type: Right
    """
    del node


def test_future_multiple_inheritance_ambiguity_is_explicit() -> None:
    """
    title: Invocation and explanation report the same future nominal ambiguity.
    """
    dispatcher = ScopedNodeDispatch(
        "analysis",
        (
            contribute_node(
                "left", "test", "analysis", Left, left, source=__name__
            ),
            contribute_node(
                "right", "test", "analysis", Right, right, source=__name__
            ),
        ),
        reject,
    )
    with pytest.raises(ConfigurationError, match="ambiguous"):
        dispatcher.visit(Combined())
    with pytest.raises(ConfigurationError, match="ambiguous"):
        dispatcher.explain(Combined)
