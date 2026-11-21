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
      type_: Type expression to process.
    returns: One stable collection element type name.
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
    title: Immutable, independently iterable integer progression
      value.
    summary: Represent a compact arithmetic progression, not contiguous
      list storage or a stateful generator. Supported numeric domains,
      representation, construction, access, and iteration validity
      belong to semantic hosts.
    """

    def __str__(self) -> str:
        """
        title: Render the range type name.
        returns: String representation of this instance.
        """
        return "RangeType"


@public
@typechecked
class SequenceType(CollectionType):
    """
    title: Read-only ordered, sized, indexable sequence parameter contract.
    summary: The element type preserves width and nullability. Frontends
      may express generic elements; the semantic host validates concrete
      adapters, borrow lifetimes and supported storage. This type does not
      own its elements.
    attributes:
      element_type: Type of each element.
    """

    element_type: DataType

    def __init__(self, element_type: DataType) -> None:
        """
        title: Declare the exact element contract of a borrowed sequence.
        parameters:
          element_type: Type of each element.
        """
        super().__init__()
        self.element_type = element_type

    def __str__(self) -> str:
        """
        title: Render the sequence element contract.
        returns: String representation of this instance.
        """
        return f"SequenceType[{_format_type_name(self.element_type)}]"


@public
@typechecked
class ListType(CollectionType):
    """
    title: List data type expression.
    attributes:
      element_types: Types of element.
      size: Requested or declared size.
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
          element_types: Types of element.
          size: Requested or declared size.
        """
        if size is not None and size < 0:
            raise ValueError("list size must be non-negative")
        self.element_types = element_types
        self.size = size

    def __str__(self) -> str:
        """
        title: Return string representation of ListType.
        returns: String representation of this instance.
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
      element_type: Type of each element.
    """

    element_type: ExprType

    def __init__(self, element_type: ExprType) -> None:
        """
        title: Initialize SetType with an element type.
        parameters:
          element_type: Type of each element.
        """
        self.element_type = element_type

    def __str__(self) -> str:
        """
        title: Return string representation of SetType.
        returns: String representation of this instance.
        """
        return f"SetType[{self.element_type}]"


@public
@typechecked
class DictType(CollectionType):
    """
    title: Dictionary data type expression.
    attributes:
      key_type: Type of key.
      value_type: Type of the stored value.
    """

    key_type: ExprType
    value_type: ExprType

    def __init__(self, key_type: ExprType, value_type: ExprType) -> None:
        """
        title: Initialize DictType with key-value types.
        parameters:
          key_type: Type of key.
          value_type: Type of the stored value.
        """
        self.key_type = key_type
        self.value_type = value_type

    def __str__(self) -> str:
        """
        title: Return string representation of DictType.
        returns: String representation of this instance.
        """
        return f"DictType[{self.key_type}, {self.value_type}]"


@public
@typechecked
class TupleType(CollectionType):
    """
    title: Tuple data type expression.
    attributes:
      element_types: Types of element.
    """

    element_types: list[ExprType]

    def __init__(self, element_types: list[ExprType]) -> None:
        """
        title: Initialize TupleType with multiple element types.
        parameters:
          element_types: Types of element.
        """
        self.element_types = element_types

    def __str__(self) -> str:
        """
        title: Return string representation of TupleType.
        returns: String representation of this instance.
        """
        types_str = ", ".join(str(t) for t in self.element_types)
        return f"TupleType[{types_str}]"
