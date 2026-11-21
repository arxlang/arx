"""
title: ASTx iterable AST nodes.
summary: Provide small facade nodes for iterable constructs that
  are not yet present in upstream ASTx but are needed by semantic
  analysis and lowering.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import astx

from astx.base import NO_SOURCE_LOCATION, ReprStruct, SourceLocation
from astx.tools.typing import typechecked


@typechecked
class ForInLoopStmt(astx.StatementType):
    """
    title: Internal for-in statement node.
    summary: 'Model source forms equivalent to ``for target in iterable:
      body`` while preserving ASTx-compatible target, iterable, and body
      child nodes.'
    attributes:
      target: Destination of the operation.
      iterable: Iterable.
      body: Statements forming the body.
    """

    target: astx.AST
    iterable: astx.AST
    body: astx.Block

    def __init__(
        self,
        target: astx.AST,
        iterable: astx.AST,
        body: astx.Block,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: astx.ASTNodes | None = None,
    ) -> None:
        """
        title: Initialize one for-in statement.
        parameters:
          target: Destination of the operation.
          iterable: Iterable.
          body: Statements forming the body.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.target = target
        self.iterable = iterable
        self.body = body

    def __str__(self) -> str:
        """
        title: Return a compact display string.
        returns: String representation of this instance.
        """
        return "ForInLoopStmt"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the structured representation.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = (
            f"FOR-IN-LOOP-STMT[{id(self)}]"
            if simplified
            else "FOR-IN-LOOP-STMT"
        )
        value = cast(
            ReprStruct,
            {
                "target": self.target.get_struct(simplified),
                "iterable": self.iterable.get_struct(simplified),
                "body": self.body.get_struct(simplified),
            },
        )
        return self._prepare_struct(key, value, simplified)


@typechecked
class DictComprehension(astx.Comprehension):
    """
    title: Internal dictionary comprehension node.
    summary: 'Represent ``{key: value for ...}`` until upstream ASTx exposes
      a canonical dictionary-comprehension expression node.'
    attributes:
      key: Key selecting the entry.
      value: Stored value.
    """

    key: astx.Expr
    value: astx.Expr

    def __init__(
        self,
        key: astx.Expr,
        value: astx.Expr,
        generators: (
            astx.ASTNodes[astx.ComprehensionClause]
            | Iterable[astx.ComprehensionClause]
        ) = (),
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: astx.ASTNodes | None = None,
    ) -> None:
        """
        title: Initialize one dictionary comprehension.
        parameters:
          key: Key selecting the entry.
          value: Value to process.
          generators: Generators.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(generators=generators, loc=loc, parent=parent)
        self.key = key
        self.value = value

    def __str__(self) -> str:
        """
        title: Return a compact display string.
        returns: String representation of this instance.
        """
        return "DictComprehension"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the structured representation.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"{self}#{id(self)}" if simplified else str(self)
        generators = (
            {"generators": self.generators.get_struct(simplified)}
            if self.generators.nodes
            else {}
        )
        value = cast(
            ReprStruct,
            {
                "key": self.key.get_struct(simplified),
                "value": self.value.get_struct(simplified),
                **generators,
            },
        )
        return self._prepare_struct(key, value, simplified)


__all__ = ["DictComprehension", "ForInLoopStmt"]
