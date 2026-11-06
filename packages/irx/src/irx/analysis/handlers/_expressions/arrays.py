# mypy: disable-error-code=no-redef

"""
title: Expression array visitors.
summary: >-
  Handle array-specific semantic helpers that are separate from tensor
  expression semantics.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.dependencies.expression_array import (
    ExpressionArrayAnalysisServices,
)
from irx.analysis.types import is_integer_type
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ExpressionArrayAnalysis:
    """
    title: Expression array visitors.
    attributes:
      services:
        type: ExpressionArrayAnalysisServices
    """

    services: ExpressionArrayAnalysisServices

    def __init__(self, services: ExpressionArrayAnalysisServices) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExpressionArrayAnalysisServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject an input outside this feature's explicit support.
        parameters:
          node:
            type: astx.AST
        """
        raise configuration_error(
            f"unsupported {type(node).__name__} in ExpressionArrayAnalysis"
        )

    @dispatch
    def visit(self, node: astx.ArrayInt32ArrayLength) -> None:
        """
        title: Visit ArrayInt32ArrayLength nodes.
        parameters:
          node:
            type: astx.ArrayInt32ArrayLength
        """
        for item in node.values:
            self.services.visit(item)
            if not is_integer_type(self.services.expr_type(item)):
                self.services.context.diagnostics.add(
                    "Array helper supports only integer expressions",
                    node=item,
                )
        self.services.set_type(node, astx.Int32())

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.expression_array." + node_type.__name__,
                "irx.analysis.expression_array",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExpressionArrayAnalysis.visit",
            )
            for node_type in (astx.ArrayInt32ArrayLength,)
        )
