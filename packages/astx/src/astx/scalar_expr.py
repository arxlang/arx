"""
title: Typed logical scalar expressions.
"""

from __future__ import annotations

from enum import Enum

from public import public

from astx.base import DataType, Expr, ReprStruct, SourceLocation
from astx.schema import ScalarType
from astx.tools.typing import typechecked
from astx.types import AnyType


@public
@typechecked
class ScalarLiteral(DataType):
    """
    title: Construct a typed logical scalar.
    attributes:
      type_:
        type: ScalarType
      values:
        type: tuple[Expr, Ellipsis]
      loc:
        type: SourceLocation
    """

    type_: ScalarType
    values: tuple[Expr, ...]
    loc: SourceLocation

    def __init__(
        self,
        type_: ScalarType,
        values: tuple[Expr, ...],
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Initialize an explicitly typed sequence of scalar expressions.
        parameters:
          type_:
            type: ScalarType
          values:
            type: tuple[Expr, Ellipsis]
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        self.type_ = type_
        self.values = values
        if loc is not None:
            self.loc = loc

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the declared type and all element expressions.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "ScalarLiteral",
            {
                "type": self.type_.get_struct(simplified),
                "values": [
                    value.get_struct(simplified) for value in self.values
                ],
            },
            simplified,
        )


@public
@typechecked
class ScalarOperation(Enum):
    """
    title: Closed scalar primitives, independent of backend symbols.
    """

    EQUAL = "scalar_equal"
    TEXT = "scalar_text"
    BYTES = "scalar_bytes"
    VALUES = "scalar_values"
    STORAGE = "scalar_storage"
    FIELD = "scalar_field"


@public
@typechecked
class ScalarQuery(DataType):
    """
    title: Apply a typed scalar operation without selecting native storage.
    attributes:
      operation:
        type: ScalarOperation
      arguments:
        type: tuple[Expr, Ellipsis]
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    operation: ScalarOperation
    arguments: tuple[Expr, ...]
    type_: DataType
    loc: SourceLocation

    def __init__(
        self,
        operation: ScalarOperation,
        arguments: tuple[Expr, ...],
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Initialize a closed query with ordered expression arguments.
        parameters:
          operation:
            type: ScalarOperation
          arguments:
            type: tuple[Expr, Ellipsis]
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        self.operation = operation
        self.arguments = arguments
        self.type_ = AnyType()
        if loc is not None:
            self.loc = loc

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the operation and arguments in structural snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "ScalarQuery",
            {
                "operation": self.operation.value,
                "arguments": [
                    arg.get_struct(simplified) for arg in self.arguments
                ],
            },
            simplified,
        )
