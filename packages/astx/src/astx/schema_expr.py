"""
title: Typed construction and inspection of portable schema descriptors.
"""

from __future__ import annotations

from enum import Enum
from typing import cast

from public import public

from astx.base import DataType, Expr, ReprStruct, SourceLocation
from astx.schema import (
    FieldType,
    LogicalType,
    Schema,
    SchemaField,
    SchemaType,
    TypeDescriptorType,
)
from astx.tools.typing import typechecked
from astx.types import Boolean, Int32, Int64, String


@public
@typechecked
class TypeDescriptorLiteral(DataType):
    """
    title: Construct an immutable LogicalType descriptor value.
    attributes:
      value:
        type: LogicalType
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    value: LogicalType
    type_: DataType
    loc: SourceLocation

    def __init__(
        self, value: LogicalType, *, loc: SourceLocation | None = None
    ) -> None:
        """
        title: Initialize a typed descriptor without selecting its backend.
        parameters:
          value:
            type: LogicalType
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        if loc is not None:
            self.loc = loc
        self.value = value
        self.type_ = TypeDescriptorType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the complete immutable descriptor in AST snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "TypeDescriptorLiteral",
            cast(ReprStruct, self.value.get_struct()),
            simplified,
        )


@public
@typechecked
class FieldLiteral(DataType):
    """
    title: Construct an immutable SchemaField descriptor value.
    attributes:
      value:
        type: SchemaField
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    value: SchemaField
    type_: DataType
    loc: SourceLocation

    def __init__(
        self, value: SchemaField, *, loc: SourceLocation | None = None
    ) -> None:
        """
        title: Initialize a typed descriptor without selecting its backend.
        parameters:
          value:
            type: SchemaField
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        if loc is not None:
            self.loc = loc
        self.value = value
        self.type_ = FieldType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the complete immutable descriptor in AST snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "FieldLiteral",
            cast(ReprStruct, self.value.get_struct()),
            simplified,
        )


@public
@typechecked
class SchemaLiteral(DataType):
    """
    title: Construct an immutable Schema descriptor value.
    attributes:
      value:
        type: Schema
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    value: Schema
    type_: DataType
    loc: SourceLocation

    def __init__(
        self, value: Schema, *, loc: SourceLocation | None = None
    ) -> None:
        """
        title: Initialize a typed descriptor without selecting its backend.
        parameters:
          value:
            type: Schema
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        if loc is not None:
            self.loc = loc
        self.value = value
        self.type_ = SchemaType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the complete immutable descriptor in AST snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "SchemaLiteral",
            cast(ReprStruct, self.value.get_struct()),
            simplified,
        )


@public
@typechecked
class DescriptorOperation(Enum):
    """
    title: >-
      Closed descriptor operations, never arbitrary runtime function names.
    """

    SCHEMA_FIELD_COUNT = "schema_nfields"
    SCHEMA_FIELD = "schema_field"
    FIELD_NAME = "field_name"
    FIELD_TYPE = "field_type"
    FIELD_NULLABLE = "field_nullable"
    EQUAL = "descriptor_equal"
    TYPE_BIT_WIDTH = "type_bit_width"
    TYPE_FIELD_COUNT = "type_nfields"
    TYPE_FIELD = "type_field"


@public
@typechecked
class DescriptorQuery(DataType):
    """
    title: >-
      Inspect a descriptor through a typed and semantically checked operation.
    attributes:
      operation:
        type: DescriptorOperation
      arguments:
        type: tuple[Expr, Ellipsis]
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    operation: DescriptorOperation
    arguments: tuple[Expr, ...]
    type_: DataType
    loc: SourceLocation

    def __init__(
        self,
        operation: DescriptorOperation,
        arguments: tuple[Expr, ...],
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Initialize a focused descriptor query for semantic resolution.
        parameters:
          operation:
            type: DescriptorOperation
          arguments:
            type: tuple[Expr, Ellipsis]
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        if loc is not None:
            self.loc = loc
        self.operation = operation
        self.arguments = arguments
        self.type_ = Int64()
        if operation is DescriptorOperation.FIELD_NAME:
            self.type_ = String()
        if operation in {
            DescriptorOperation.EQUAL,
            DescriptorOperation.FIELD_NULLABLE,
        }:
            self.type_ = Boolean()
        elif operation in {
            DescriptorOperation.SCHEMA_FIELD,
            DescriptorOperation.TYPE_FIELD,
        }:
            self.type_ = FieldType()
        elif operation is DescriptorOperation.FIELD_TYPE:
            self.type_ = TypeDescriptorType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render a descriptor query and all operand nodes.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "DescriptorQuery",
            {
                "operation": self.operation.value,
                "arguments": [
                    arg.get_struct(simplified) for arg in self.arguments
                ],
            },
            simplified,
        )


@public
@typechecked
class DescriptorCompatibility(DataType):
    """
    title: Compile-time conversion classification of immutable descriptors.
    attributes:
      source:
        type: LogicalType | Schema
      target:
        type: LogicalType | Schema
      type_:
        type: DataType
      loc:
        type: SourceLocation
    """

    source: LogicalType | Schema
    target: LogicalType | Schema
    type_: DataType
    loc: SourceLocation

    def __init__(
        self,
        source: LogicalType | Schema,
        target: LogicalType | Schema,
        *,
        loc: SourceLocation | None = None,
    ) -> None:
        """
        title: Model conversion requirements without executing a value cast.
        parameters:
          source:
            type: LogicalType | Schema
          target:
            type: LogicalType | Schema
          loc:
            type: SourceLocation | None
        """
        super().__init__()
        if loc is not None:
            self.loc = loc
        self.source = source
        self.target = target
        self.type_ = Int32()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render both complete descriptors in compatibility snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "DescriptorCompatibility",
            cast(
                ReprStruct,
                {
                    "source": self.source.get_struct(),
                    "target": self.target.get_struct(),
                },
            ),
            simplified,
        )
