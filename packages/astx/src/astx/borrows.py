"""
title: Local borrow declarations and retargeting statements.
"""

from enum import Enum

from public import public

from astx.base import (
    NO_SOURCE_LOCATION,
    ASTKind,
    DataType,
    Expr,
    ReprStruct,
    SourceLocation,
    StatementType,
)
from astx.data import Identifier, VariableDeclaration
from astx.modifiers import MutabilityKind
from astx.tools.typing import typechecked


@public
class BorrowAccess(Enum):
    """
    title: Access granted by a borrow.
    """

    read_only = "read_only"
    exclusive = "exclusive"


@public
@typechecked
class BorrowDeclaration(VariableDeclaration):
    """
    title: Declare a local borrow of a place.
    attributes:
      kind: Kind of syntax node.
      access: Access granted through the binding.
    """

    kind: ASTKind
    access: BorrowAccess

    def __init__(
        self,
        name: str,
        type_: DataType,
        source: Expr,
        access: BorrowAccess,
        *,
        mutability: MutabilityKind = MutabilityKind.mutable,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize a local borrow declaration.
        parameters:
          name: Binding name.
          type_: Declared type or an inference request.
          source: Place whose storage is borrowed.
          access: Access granted through the binding.
          mutability: Whether the binding may be retargeted.
          loc: Source coordinates.
        """
        super().__init__(name, type_, mutability, value=source, loc=loc)
        self.kind = ASTKind.BorrowDeclarationKind
        self.access = access

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Represent a borrow initializer with its access mode.
        parameters:
          simplified: Whether to emit the compact representation.
        returns: Structured representation.
        """
        return self._prepare_struct(
            f"BorrowDeclaration[{self.name}, {self.access.value}]",
            self.value.get_struct(simplified),
            simplified,
        )


@public
@typechecked
class BorrowRetarget(StatementType):
    """
    title: Retarget a live borrow binding.
    attributes:
      kind: Kind of syntax node.
      target: Existing borrow binding.
      source: Replacement place.
      access: Access requested for the replacement.
    """

    kind: ASTKind
    target: Identifier
    source: Expr
    access: BorrowAccess

    def __init__(
        self,
        target: Identifier,
        source: Expr,
        access: BorrowAccess,
        *,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize a borrow retargeting statement.
        parameters:
          target: Existing borrow binding.
          source: Replacement place.
          access: Access requested for the replacement.
          loc: Source coordinates.
        """
        super().__init__(loc=loc)
        self.kind = ASTKind.BorrowRetargetKind
        self.target = target
        self.source = source
        self.access = access

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Represent retargeting with its destination and access.
        parameters:
          simplified: Whether to emit the compact representation.
        returns: Structured representation.
        """
        return self._prepare_struct(
            f"BorrowRetarget[{self.target.name}, {self.access.value}]",
            self.source.get_struct(simplified),
            simplified,
        )
