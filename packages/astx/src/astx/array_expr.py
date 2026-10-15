"""
title: Typed columnar array, chunk and builder expressions.
"""

from __future__ import annotations

from enum import Enum

from public import public

from astx.base import DataType, Expr, ReprStruct, SourceLocation
from astx.schema import ArrayBuilderType, ArrayType, ChunkedArrayType
from astx.tools.typing import typechecked
from astx.types import AnyType


@public
@typechecked
class ArrayLiteral(DataType):
    """
    title: Construct a typed array, builder or chunk sequence.
    attributes:
      type_:
        type: ArrayType | ArrayBuilderType | ChunkedArrayType
      values:
        type: tuple[Expr, Ellipsis]
      loc:
        type: SourceLocation
    """

    type_: ArrayType | ArrayBuilderType | ChunkedArrayType
    values: tuple[Expr, ...]
    loc: SourceLocation

    def __init__(
        self,
        type_: ArrayType | ArrayBuilderType | ChunkedArrayType,
        values: tuple[Expr, ...],
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Initialize an explicitly typed sequence of scalar expressions.
        parameters:
          type_:
            type: ArrayType | ArrayBuilderType | ChunkedArrayType
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
            "ArrayLiteral",
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
class ArrayOperation(Enum):
    """
    title: Closed array and builder primitives, independent of backend symbols.
    """

    FROM_BUFFER = "array_from_buffer"
    APPEND = "builder_append"
    RESERVE = "builder_reserve"
    BUILDER_LENGTH = "builder_length"
    FINISH = "builder_finish"
    CHUNK_COUNT = "chunk_count"
    CHUNK_AT = "chunk_at"
    COMBINE = "combine_chunks"
    LENGTH = "array_length"
    NULL_COUNT = "array_null_count"
    OFFSET = "array_offset"
    AT = "array_at"
    SLICE = "array_slice"
    CONCAT = "array_concat"
    COPY = "array_copy"
    EQUAL = "array_equal"


@public
@typechecked
class ArrayQuery(DataType):
    """
    title: Apply a typed array operation without selecting native storage.
    attributes:
      operation:
        type: ArrayOperation
      arguments:
        type: tuple[Expr, Ellipsis]
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    operation: ArrayOperation
    arguments: tuple[Expr, ...]
    type_: DataType
    loc: SourceLocation

    def __init__(
        self,
        operation: ArrayOperation,
        arguments: tuple[Expr, ...],
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Initialize a closed query with ordered expression arguments.
        parameters:
          operation:
            type: ArrayOperation
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
            "ArrayQuery",
            {
                "operation": self.operation.value,
                "arguments": [
                    arg.get_struct(simplified) for arg in self.arguments
                ],
            },
            simplified,
        )
