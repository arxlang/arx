# mypy: disable-error-code=no-redef

"""
title: Small typed visitors for cross-module shared-dispatch tests.
"""

from typing import cast

import astx

from irx.typecheck import copy_type, typechecked
from plum import Function, dispatch
from public import private


@private
@typechecked
class MixinVisitorCore:
    """
    title: Own one test visit family and independent invocation state.
    attributes:
      calls:
        type: list[str]
    """

    calls: list[str]

    def __init__(self) -> None:
        """
        title: Initialize one visitor's call history.
        """
        self.calls = []

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject unsupported test nodes.
        parameters:
          node:
            type: astx.AST
        """
        raise NotImplementedError(type(node).__name__)


# Expose Plum's public registration API without changing callable annotations.
visit_overloads = cast(Function, MixinVisitorCore.visit)


@private
@typechecked
class LiteralProbeMixin(MixinVisitorCore):
    """
    title: Contribute broad literal and narrow integer overloads.
    attributes:
      calls:
        type: list[str]
    """

    # Register the narrow handler first: later broad handlers must not win.
    @copy_type(MixinVisitorCore.visit)
    @visit_overloads.dispatch
    def visit(self, node: astx.LiteralInt32) -> None:
        """
        title: Prefer the narrower integer overload.
        parameters:
          node:
            type: astx.LiteralInt32
        """
        del node
        self.calls.append("int32")

    @copy_type(MixinVisitorCore.visit)
    @visit_overloads.dispatch
    def visit(self, node: astx.Literal) -> None:
        """
        title: Record a literal without a more specific overload.
        parameters:
          node:
            type: astx.Literal
        """
        del node
        self.calls.append("literal")
