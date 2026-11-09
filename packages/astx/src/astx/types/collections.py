"""
title: ASTx Collection Data Types.
"""

from __future__ import annotations

from public import public

from astx.base import DataType, ExprType
from astx.tools.typing import typechecked
from astx.types.base import AnyType


@typechecked
def _format_type_name(type_: ExprType) -> str:
    """
    title: Return one stable collection element type name.
    parameters:
      type_:
        type: ExprType
    returns:
      type: str
    """
    pointee_type = getattr(type_, "pointee_type", None)
    if isinstance(pointee_type, ExprType):
        return f"{type_.__class__.__name__}[{_format_type_name(pointee_type)}]"

    value = str(type_)
    default_name = f"{type_.__class__.__name__}: {getattr(type_, 'name', '')}"
    if value == default_name:
        return type_.__class__.__name__
    return value


@public
@typechecked
class CollectionType(AnyType):
    """
    title: Base class for collection data types.
    """


@public
@typechecked
class RangeType(CollectionType):
    """
    title: Immutable, independently iterable integer progression value.
    summary: >-
      Elements and endpoints are signed i32; length and cursor arithmetic use
      i64. This value owns no allocation and is not contiguous list storage.
      Construction, access, and iteration validity belong to semantic hosts.
    """

    def __str__(self) -> str:
        """
        title: Render the fixed integer range domain.
        returns:
          type: str
        """
        return "RangeType"


@public
@typechecked
class SequenceType(CollectionType):
    """
    title: Read-only ordered, sized, indexable sequence parameter contract.
    summary: >-
      The element type preserves width and nullability. Frontends may express
      generic elements; the semantic host validates concrete adapters, borrow
      lifetimes and supported storage. This type does not own its elements.
    attributes:
      element_type:
        type: DataType
    """

    element_type: DataType

    def __init__(self, element_type: DataType) -> None:
        """
        title: Declare the exact element contract of a borrowed sequence.
        parameters:
          element_type:
            type: DataType
        """
        super().__init__()
        self.element_type = element_type

    def __str__(self) -> str:
        """
        title: Render the sequence element contract.
        returns:
          type: str
        """
        return f"SequenceType[{_format_type_name(self.element_type)}]"


@public
@typechecked
class ListType(CollectionType):
    """
    title: List data type expression.
    attributes:
      element_types:
        type: list[ExprType]
      size:
        type: int | None
    """

    element_types: list[ExprType]
    size: int | None

    def __init__(
        self,
        element_types: list[ExprType],
        *,
        size: int | None = None,
    ) -> None:
        """
        title: Initialize ListType with an element type.
        parameters:
          element_types:
            type: list[ExprType]
          size:
            type: int | None
        """
        if size is not None and size < 0:
            raise ValueError("list size must be non-negative")
        self.element_types = element_types
        self.size = size

    def __str__(self) -> str:
        """
        title: Return string representation of ListType.
        returns:
          type: str
        """
        parts = [_format_type_name(type_) for type_ in self.element_types]
        if self.size is not None:
            parts.append(str(self.size))
        types_str = ", ".join(parts)
        return f"ListType[{types_str}]"


@public
@typechecked
class SetType(CollectionType):
    """
    title: Set data type expression.
    attributes:
      element_type:
        type: ExprType
    """

    element_type: ExprType

    def __init__(self, element_type: ExprType) -> None:
        """
        title: Initialize SetType with an element type.
        parameters:
          element_type:
            type: ExprType
        """
        self.element_type = element_type

    def __str__(self) -> str:
        """
        title: Return string representation of SetType.
        returns:
          type: str
        """
        return f"SetType[{self.element_type}]"


@public
@typechecked
class DictType(CollectionType):
    """
    title: Dictionary data type expression.
    attributes:
      key_type:
        type: ExprType
      value_type:
        type: ExprType
    """

    key_type: ExprType
    value_type: ExprType

    def __init__(self, key_type: ExprType, value_type: ExprType) -> None:
        """
        title: Initialize DictType with key-value types.
        parameters:
          key_type:
            type: ExprType
          value_type:
            type: ExprType
        """
        self.key_type = key_type
        self.value_type = value_type

    def __str__(self) -> str:
        """
        title: Return string representation of DictType.
        returns:
          type: str
        """
        return f"DictType[{self.key_type}, {self.value_type}]"


@public
@typechecked
class TupleType(CollectionType):
    """
    title: Tuple data type expression.
    attributes:
      element_types:
        type: list[ExprType]
    """

    element_types: list[ExprType]

    def __init__(self, element_types: list[ExprType]) -> None:
        """
        title: Initialize TupleType with multiple element types.
        parameters:
          element_types:
            type: list[ExprType]
        """
        self.element_types = element_types

    def __str__(self) -> str:
        """
        title: Return string representation of TupleType.
        returns:
          type: str
        """
        types_str = ", ".join(str(t) for t in self.element_types)
        return f"TupleType[{types_str}]"
