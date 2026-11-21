"""
title: ASTx Data Types module.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from public import public

from astx.base import (
    NO_SOURCE_LOCATION,
    ExprType,
    ReprStruct,
    SourceLocation,
)
from astx.tools.typing import typechecked
from astx.types.base import NoneType
from astx.types.operators import DataTypeOps


@public
@typechecked
class Literal(DataTypeOps):
    """
    title: Literal Data type.
    attributes:
      ref: Identifier associated with this node.
      type_: Type associated with this expression.
      loc: Source coordinates attached to this node.
      value: Stored value.
    """

    ref: str

    type_: ExprType
    loc: SourceLocation
    value: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        title: Initialize the literal base node.
        parameters:
          args:
            variadic: positional
            description: Positional arguments.
          kwargs:
            variadic: keyword
            description: Keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.ref = uuid4().hex

    def __str__(self) -> str:
        """
        title: Return a string that represents the object.
        returns: String representation of this instance.
        """
        class_name = self.__class__.__name__
        return f"{class_name}({self.value})"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Return the AST representation for the object.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        key = f"Literal[{self.type_}]: {self.value}"
        value = self.value
        return self._prepare_struct(key, value, simplified)


@public
@typechecked
class LiteralNone(Literal):
    """
    title: LiteralNone data type.
    attributes:
      loc: Source coordinates attached to this node.
      ref: Identifier associated with this node.
      value: Stored value.
      type_: Type associated with this expression.
    """

    ref: str
    value: None

    type_: NoneType
    value = None

    def __init__(self, loc: SourceLocation = NO_SOURCE_LOCATION) -> None:
        """
        title: Initialize LiteralNone.
        parameters:
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc)
        self.value = None
        self.type_ = NoneType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Represent explicit null in the supported scalar vocabulary.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        return self._prepare_struct(
            f"Literal[{self.type_}]: None", "none", simplified
        )
