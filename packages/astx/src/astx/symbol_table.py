"""
title: Symbol Table module for ASTx.
summary: >2-

  The `SymbolTable` class offered here allows the definition

  of scopes, so the variable or function would be available in

  specifics scopes.
"""

from __future__ import annotations

from typing import Optional

from public import public

from astx.mixes import NamedExpr
from astx.tools.typing import typechecked


@public
@typechecked
class ScopeNodeBase:
    """
    title: ScopeNodeBase is the base used for the nodes (levels) in the scope.
    attributes:
      name: Name identifying this declaration.
      parent: Parent node in the syntax tree.
      default_parent: Default parent.
      named_expr: Named expr.
    """

    name: str
    parent: Optional[ScopeNodeBase]
    default_parent: Optional[ScopeNodeBase] = None
    named_expr: dict[str, NamedExpr]

    def __init__(
        self, name: str, parent: Optional[ScopeNodeBase] = None
    ) -> None:
        """
        title: Initialize ScopeNodeBase.
        parameters:
          name: Name identifying the declaration or operation.
          parent: Parent node or enclosing scope.
        """
        self.parent: Optional[ScopeNodeBase] = (
            parent or ScopeNodeBase.default_parent
        )
        self.name: str = name
        self.named_expr: dict[str, NamedExpr] = {}


@public
@typechecked
class ScopeNode(ScopeNodeBase):
    """
    title: Scope node organize the scope in different levels in the stack.
    attributes:
      name: Name identifying this declaration.
      parent: Parent node in the syntax tree.
      default_parent: Default parent.
      named_expr: Named expr.
    """

    ...


@public
@typechecked
class Scope:
    """
    title: Organize the ASTx objects according to the scope.
    attributes:
      nodes: Contained syntax nodes in order.
      current: Current.
      previous: Previous.
      scope_node_class: Scope node class.
    """

    nodes: dict[int, ScopeNodeBase]
    current: Optional[ScopeNodeBase]
    previous: Optional[ScopeNodeBase]
    scope_node_class: type[ScopeNodeBase]

    def __init__(
        self,
        scope_node_class: type[ScopeNodeBase] = ScopeNode,
    ) -> None:
        """
        title: Initialize the scope.
        parameters:
          scope_node_class: Scope node class.
        """
        self.nodes: dict[int, ScopeNodeBase] = {}
        self.current = None
        self.previous = None
        self.scope_node_class = scope_node_class

        self.add("root")

        self.scope_node_class.default_parent = self.current

    def add(
        self,
        name: str,
        parent: Optional[ScopeNodeBase] = None,
        change_current: bool = True,
    ) -> ScopeNodeBase:
        """
        title: Add a new node in the scope.
        parameters:
          name: Name identifying the declaration or operation.
          parent: Parent node or enclosing scope.
          change_current: Whether to use change current.
        returns: 'Result of this operation: add a new node in the scope.'
        """
        node = self.scope_node_class(name, parent)

        # The use of id(node) as keys in the nodes dictionary is generally
        # fine, but be aware that this approach may lead to potential issues
        # if the id() of a node is reused after its destruction. It's #
        # unlikely to happen in the current code, but it's something to be
        # aware of.
        self.nodes[id(node)] = node

        if len(self.nodes) == 1 or change_current:
            self.previous = self.current
            self.current = self.nodes[id(node)]

        return node

    def get_first(self) -> ScopeNodeBase:
        """
        title: Get the first node in the scope.
        returns: The first node in the scope.
        """
        node_id = next(iter(self.nodes.keys()))
        return self.nodes[node_id]

    def get_last(self) -> ScopeNodeBase:
        """
        title: Get the latest node in the scope.
        returns: The latest node in the scope.
        """
        node_id = list(self.nodes.keys())[-1]
        return self.nodes[node_id]

    def destroy(self, node: ScopeNodeBase) -> None:
        """
        title: Destroy the current scope.
        parameters:
          node: Syntax node to process.
        """
        del self.nodes[id(node)]
        self.current = self.previous
        self.previous = None

    def set_default_parent(self, node: ScopeNodeBase) -> None:
        """
        title: Set default parent for the current scope.
        parameters:
          node: Syntax node to process.
        """
        self.scope_node_class.default_parent = node


@public
@typechecked
class SymbolTable:
    """
    title: Symbol Table for ASTx.
    attributes:
      scopes: Scopes.
    """

    scopes: Scope

    def __init__(self) -> None:
        """
        title: Initialize the symbol table.
        """
        self.scopes = Scope()

    def define(self, expr: NamedExpr) -> None:
        """
        title: Define a new named expression inside the scoped stack.
        parameters:
          expr: Expression to process.
        """
        if not self.scopes.current:
            raise Exception("SymbolTable: No scope active.")
        self.scopes.current.named_expr[expr.name] = expr

    def update(self, expr: NamedExpr) -> None:
        """
        title: Update the expression on the SymbolTable.
        summary: >2-

          It is useful mainly for updating the comment of the expression.
        parameters:
          expr: Expression to process.
        """
        if not self.scopes.current:
            raise Exception("SymbolTable: No scope active.")
        if expr.name not in self.scopes.current.named_expr:
            raise Exception("This name doesn't exist in the SymbolTable.")
        self.scopes.current.named_expr[expr.name] = expr

    def lookup(self, name: str) -> NamedExpr:
        """
        title: Get a named expression from the scope stack.
        parameters:
          name: Name identifying the declaration or operation.
        returns: A named expression from the scope stack.
        """
        scope = self.scopes.current
        while scope is not None:
            if name in scope.named_expr:
                return scope.named_expr[name]
            scope = scope.parent
        raise NameError(f"Name '{name}' is not defined")
