"""
title: ASTx Data Types module.
"""

from __future__ import annotations

from public import public

from astx.base import (
    NO_SOURCE_LOCATION,
    ReprStruct,
    SourceLocation,
)
from astx.literals.base import Literal
from astx.tools.typing import typechecked
from astx.types.string import String, UTF8Char, UTF8String


@public
@typechecked
class LiteralString(Literal):
    """
    title: LiteralString data type class.
    attributes:
      type_: Type associated with this expression.
      loc: Source coordinates attached to this node.
      value: Stored value.
    """

    type_: String
    loc: SourceLocation

    value: str

    def __init__(
        self, value: str, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Initialize LiteralString.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc)
        self.value = value
        self.type_ = String()
        self.loc = loc

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"LiteralString({self.value})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST structure of the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"LiteralString: {self.value}"
        value = self.value
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class LiteralUTF8String(LiteralString):
    """
    title: Literal class for UTF-8 strings.
    attributes:
      loc: Source coordinates attached to this node.
      type_: Type associated with this expression.
      value: Stored value.
    """

    loc: SourceLocation
    type_: UTF8String

    value: str

    def __init__(
        self, value: str, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Initialize the UTF-8 string literal.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(value=value, loc=loc)
        self.type_ = UTF8String()

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"LiteralUTF8String({self.value})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the structure of the object in a simplified.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"LiteralUTF8String: {self.value}"
        value = self.value
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class LiteralUTF8Char(LiteralString):
    """
    title: Literal class for UTF-8 characters.
    attributes:
      loc: Source coordinates attached to this node.
      type_: Type associated with this expression.
      value: Stored value.
    """

    loc: SourceLocation
    type_: UTF8Char

    value: str

    def __init__(
        self, value: str, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Initialize the UTF-8 character literal.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(value=value, loc=loc)
        self.type_ = UTF8Char()

    def __str__(self) -> str:
        """
        title: Return a string representation of the object.
        returns: String representation of this instance.
        """
        return f"LiteralUTF8Char({self.value})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the structure of the object in a simplified.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"LiteralUTF8Char: {self.value}"
        value = self.value
        return self._prepare_struct(key, value, simplified)
