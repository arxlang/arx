"""
title: Module for Variables.
"""

from __future__ import annotations

from typing import Iterable, Optional

from public import public

from astx.base import (
    NO_SOURCE_LOCATION,
    ASTKind,
    ASTNodes,
    DataType,
    Expr,
    ReprStruct,
    SourceLocation,
    StatementType,
    Undefined,
)
from astx.modifiers import MutabilityKind, ScopeKind, VisibilityKind
from astx.tools.typing import typechecked
from astx.types import AnyType
from astx.types.operators import DataTypeOps

UNDEFINED = Undefined()


@public
@typechecked
class VariableDeclaration(StatementType):
    """
    title: AST class for variable declaration.
    attributes:
      kind: Kind of value or operation.
      mutability: Mutability.
      visibility: Visibility.
      scope: Scope used to resolve names.
      name: Name identifying this declaration.
      type_: Type associated with this expression.
      value: Stored value.
    """

    kind: ASTKind

    mutability: MutabilityKind
    visibility: VisibilityKind
    scope: ScopeKind
    name: str
    type_: DataType
    value: Expr

    def __init__(
        self,
        name: str,
        type_: DataType,
        mutability: MutabilityKind = MutabilityKind.constant,
        visibility: VisibilityKind = VisibilityKind.public,
        scope: ScopeKind = ScopeKind.local,
        value: Expr = UNDEFINED,
        parent: Optional[ASTNodes] = None,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize the VarExprAST instance.
        parameters:
          name: Name identifying the declaration or operation.
          type_: Type expression to process.
          mutability: Mutability.
          visibility: Visibility.
          scope: Scope used to resolve names.
          value: Value to process.
          parent: Parent node or enclosing scope.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc, parent=parent)
        self.mutability = mutability
        self.scope = scope
        self.visibility = visibility
        self.name = name
        self.type_ = type_
        self.value = value
        self.kind = ASTKind.VarDeclKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        type_ = self.type_.__class__.__name__
        return f"VariableDeclaration[{self.name}, {type_}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = str(self)
        value = self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class InlineVariableDeclaration(Expr):
    """
    title: AST class for inline variable declaration expression.
    summary: >2-

      Can be used in expressions like for loops.
    attributes:
      scope: Scope used to resolve names.
      visibility: Visibility.
      kind: Kind of value or operation.
      mutability: Mutability.
      name: Name identifying this declaration.
      type_: Type associated with this expression.
      value: Stored value.
    """

    scope: ScopeKind
    visibility: VisibilityKind
    kind: ASTKind

    mutability: MutabilityKind
    name: str
    type_: DataType
    value: Expr

    def __init__(
        self,
        name: str,
        type_: DataType,
        mutability: MutabilityKind = MutabilityKind.constant,
        visibility: VisibilityKind = VisibilityKind.public,
        scope: ScopeKind = ScopeKind.local,
        value: Expr = UNDEFINED,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the VarExprAST instance.
        parameters:
          name: Name identifying the declaration or operation.
          type_: Type expression to process.
          mutability: Mutability.
          visibility: Visibility.
          scope: Scope used to resolve names.
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.mutability = mutability
        self.scope = scope
        self.visibility = visibility
        self.name = name
        self.type_ = type_
        self.value = value
        self.kind = ASTKind.VarDeclKind

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        type_ = self.type_.__class__.__name__
        return f"InlineVariableDeclaration[{self.name}, {type_}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = str(self)
        value = self.value.get_struct(simplified)
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class Identifier(DataTypeOps):
    """
    title: AST class for identifiers.
    attributes:
      name: Name identifying this declaration.
      type_: Type associated with this expression.
    """

    name: str
    type_: DataType = AnyType()

    def __init__(
        self,
        name: str,
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the Identifier instance.
        parameters:
          name: Name identifying the declaration or operation.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.name = name
        # note: necessary for data operations
        self.type_ = AnyType()

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        return f"{self.__class__.__name__}[{self.name}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return a structure that represents the Identifier object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"{self.__class__.__name__.upper()}[{self.name}]"
        return self._prepare_struct(key, self.name, simplified)


@public
@typechecked
class Variable(Identifier):
    """
    title: AST class for the variable usage.
    attributes:
      name: Name identifying this declaration.
      type_: Type associated with this expression.
    """

    type_: DataType

    def __init__(
        self,
        name: str,
        type_: DataType = AnyType(),
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the Variable instance.
        parameters:
          name: Name identifying the declaration or operation.
          type_: Type expression to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(name=name, loc=loc, parent=parent)
        self.type_ = type_


class DeleteStmt(StatementType):
    """
    title: AST class for 'del' statements.
    attributes:
      kind: Kind of value or operation.
      value: Stored value.
    """

    kind: ASTKind

    value: Iterable[Identifier]

    def __init__(
        self,
        value: Iterable[Identifier],
        loc: SourceLocation = NO_SOURCE_LOCATION,
        parent: Optional[ASTNodes] = None,
    ) -> None:
        """
        title: Initialize the DeleteStmt instance.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
          parent: Parent node or enclosing scope.
        """
        super().__init__(loc=loc, parent=parent)
        self.value = value
        self.kind = ASTKind.DeleteStmtKind

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        value_str = ", ".join(str(value) for value in self.value)
        return f"DeleteStmt[{value_str}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = "DELETE"

        value: ReprStruct = {
            f"target_{i}": val.get_struct(simplified)
            for i, val in enumerate(self.value)
        }

        return self._prepare_struct(key, value, simplified)
