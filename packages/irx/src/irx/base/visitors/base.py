"""
title: Minimal fail-closed Plum visitor base.
summary: >-
  Concrete visitors explicitly register supported nodes and structural
  traversal. Modeling an ASTx node does not imply compiler support.
"""

import astx

from plum import dispatch

from irx.typecheck import typechecked


@typechecked
class BaseVisitor:
    """
    title: Typed rejection fallback extended by nominal visit overloads.
    """

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject unsupported nodes without implicit structural traversal.
        parameters:
          node:
            type: astx.AST
        raises:
          NotImplementedError: When the visitor does not implement the node.
        """
        raise NotImplementedError(
            f"{type(self).__name__}.visit({type(node).__name__}) "
            "is not implemented"
        )
