"""
title: Portable logical data types and recursive schemas.
summary: >-
  Model columnar data without importing Arrow or fixing a C++ representation.
  IRx validates semantic constraints before using these descriptors. Binary
  metadata canonicalization is an analysis responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from public import public

from astx.base import ReprStruct
from astx.tools.typing import typechecked
from astx.types.base import AnyType

Metadata = tuple[tuple[bytes, bytes], ...]


@public
@typechecked
class LogicalKind(Enum):
    """
    title: Portable logical storage families.
    """

    NULL = "null"
    BOOL = "bool"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    INT64 = "int64"
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    FLOAT16 = "float16"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    BINARY = "binary"
    LARGE_BINARY = "large_binary"
    BINARY_VIEW = "binary_view"
    STRING = "string"
    LARGE_STRING = "large_string"
    STRING_VIEW = "string_view"
    FIXED_BINARY = "fixed_binary"
    DATE32 = "date32"
    DATE64 = "date64"
    TIME32 = "time32"
    TIME64 = "time64"
    TIMESTAMP = "timestamp"
    DURATION = "duration"
    MONTH_INTERVAL = "month_interval"
    DAY_TIME_INTERVAL = "day_time_interval"
    MONTH_DAY_NANO_INTERVAL = "month_day_nano_interval"
    DECIMAL32 = "decimal32"
    DECIMAL64 = "decimal64"
    DECIMAL128 = "decimal128"
    DECIMAL256 = "decimal256"
    LIST = "list"
    LARGE_LIST = "large_list"
    LIST_VIEW = "list_view"
    LARGE_LIST_VIEW = "large_list_view"
    FIXED_LIST = "fixed_list"
    STRUCT = "struct"
    MAP = "map"
    SPARSE_UNION = "sparse_union"
    DENSE_UNION = "dense_union"
    DICTIONARY = "dictionary"
    RUN_END_ENCODED = "run_end_encoded"
    EXTENSION = "extension"


@public
@typechecked
class TimeUnit(Enum):
    """
    title: Units retained exactly in temporal descriptors.
    """

    SECOND = "s"
    MILLISECOND = "ms"
    MICROSECOND = "us"
    NANOSECOND = "ns"


@public
@typechecked
class ParameterKind(Enum):
    """
    title: Typed parameter keys rather than backend-specific type strings.
    """

    PRECISION = "precision"
    SCALE = "scale"
    TIME_UNIT = "unit"
    TIMEZONE = "timezone"
    BYTE_WIDTH = "byte_width"
    LIST_SIZE = "list_size"
    KEYS_SORTED = "keys_sorted"
    ORDERED = "ordered"
    TYPE_CODES = "type_codes"
    EXTENSION_NAME = "extension_name"
    EXTENSION_METADATA = "extension_metadata"


ParameterValue = int | bool | str | bytes | TimeUnit | tuple[int, ...]


@public
@typechecked
@dataclass(frozen=True, init=False)
class LogicalParameter:
    """
    title: One explicitly typed logical parameter.
    attributes:
      kind:
        type: ParameterKind
      value:
        type: ParameterValue
    """

    kind: ParameterKind
    value: ParameterValue

    def __init__(self, kind: ParameterKind, value: ParameterValue) -> None:
        """
        title: Initialize a parameter with runtime-checked components.
        parameters:
          kind:
            type: ParameterKind
          value:
            type: ParameterValue
        """
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "value", value)


@public
@typechecked
@dataclass(frozen=True, init=False)
class LogicalType:
    """
    title: An immutable recursive logical descriptor.
    summary: >-
      Fields describe nested children. Dictionary children are indices and
      values; extensions have one storage child. No AST or backend object is
      retained inside a descriptor.
    attributes:
      kind:
        type: LogicalKind
      fields:
        type: tuple[SchemaField, Ellipsis]
      parameters:
        type: tuple[LogicalParameter, Ellipsis]
    """

    kind: LogicalKind
    fields: tuple[SchemaField, ...]
    parameters: tuple[LogicalParameter, ...]

    def __init__(
        self,
        kind: LogicalKind,
        *,
        fields: tuple[SchemaField, ...] = (),
        parameters: tuple[LogicalParameter, ...] = (),
    ) -> None:
        """
        title: Initialize a descriptor without choosing language semantics.
        parameters:
          kind:
            type: LogicalKind
          fields:
            type: tuple[SchemaField, Ellipsis]
          parameters:
            type: tuple[LogicalParameter, Ellipsis]
        """
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "parameters", parameters)

    def get_struct(self) -> dict[str, object]:
        """
        title: Render recursive descriptors with lossless hexadecimal bytes.
        returns:
          type: dict[str, object]
        """
        parameters: dict[str, object] = {}
        for parameter in self.parameters:
            value = parameter.value
            parameters[parameter.kind.value] = (
                {"hex": value.hex()}
                if isinstance(value, bytes)
                else value.value
                if isinstance(value, TimeUnit)
                else value
            )
        return {
            "kind": self.kind.value,
            "parameters": parameters,
            "fields": [field.get_struct() for field in self.fields],
        }


@public
@typechecked
@dataclass(frozen=True, init=False)
class SchemaField:
    """
    title: One named field with independent nullability and binary metadata.
    attributes:
      name:
        type: str
      type_:
        type: LogicalType
      nullable:
        type: bool
      metadata:
        type: Metadata
    """

    name: str
    type_: LogicalType
    nullable: bool
    metadata: Metadata

    def __init__(
        self,
        name: str,
        type_: LogicalType,
        *,
        nullable: bool = False,
        metadata: Metadata = (),
    ) -> None:
        """
        title: Initialize a field and validate all collection item types.
        parameters:
          name:
            type: str
          type_:
            type: LogicalType
          nullable:
            type: bool
          metadata:
            type: Metadata
        """
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "type_", type_)
        object.__setattr__(self, "nullable", nullable)
        object.__setattr__(self, "metadata", metadata)

    def get_struct(self) -> dict[str, object]:
        """
        title: Render field identity, nullability and binary metadata.
        returns:
          type: dict[str, object]
        """
        return {
            "name": self.name,
            "type": self.type_.get_struct(),
            "nullable": self.nullable,
            "metadata": [
                (key.hex(), value.hex()) for key, value in self.metadata
            ],
        }


@public
@typechecked
@dataclass(frozen=True, init=False)
class Schema:
    """
    title: A static ordered schema with schema-level binary metadata.
    attributes:
      fields:
        type: tuple[SchemaField, Ellipsis]
      metadata:
        type: Metadata
    """

    fields: tuple[SchemaField, ...]
    metadata: Metadata

    def __init__(
        self,
        fields: tuple[SchemaField, ...] = (),
        *,
        metadata: Metadata = (),
    ) -> None:
        """
        title: Initialize a static schema, including an empty schema.
        parameters:
          fields:
            type: tuple[SchemaField, Ellipsis]
          metadata:
            type: Metadata
        """
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "metadata", metadata)

    def get_struct(self) -> dict[str, object]:
        """
        title: Render ordered schema fields and schema-level metadata.
        returns:
          type: dict[str, object]
        """
        return {
            "fields": [field.get_struct() for field in self.fields],
            "metadata": [
                (key.hex(), value.hex()) for key, value in self.metadata
            ],
        }


@public
@typechecked
class LogicalValueType(AnyType):
    """
    title: Base for typed scalar and one-dimensional columnar values.
    attributes:
      element_type:
        type: LogicalType
      nullable:
        type: bool
    """

    element_type: LogicalType
    nullable: bool

    def __init__(
        self, element_type: LogicalType, *, nullable: bool = False
    ) -> None:
        """
        title: Initialize the logical element contract.
        parameters:
          element_type:
            type: LogicalType
          nullable:
            type: bool
        """
        super().__init__()
        self.element_type = element_type
        self.nullable = nullable

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve the complete logical element in AST snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            type(self).__name__,
            {
                "element_type": self.element_type.get_struct(),
                "nullable": self.nullable,
            },
            simplified,
        )


@public
@typechecked
class ScalarType(LogicalValueType):
    """
    title: A scalar value, including a valid null scalar.
    attributes:
      element_type:
        type: LogicalType
      nullable:
        type: bool
    """


@public
@typechecked
class ArrayType(LogicalValueType):
    """
    title: A contiguous one-dimensional columnar array.
    attributes:
      element_type:
        type: LogicalType
      nullable:
        type: bool
    """


@public
@typechecked
class ArrayBuilderType(LogicalValueType):
    """
    title: A unique mutable builder for a declared logical element type.
    attributes:
      element_type:
        type: LogicalType
      nullable:
        type: bool
    """


@public
@typechecked
class ChunkedArrayType(LogicalValueType):
    """
    title: A logical array composed of zero or more physical chunks.
    attributes:
      element_type:
        type: LogicalType
      nullable:
        type: bool
    """


@public
@typechecked
class SchemaValueType(AnyType):
    """
    title: Base for statically or dynamically schematized row containers.
    attributes:
      schema:
        type: Schema | None
    """

    schema: Schema | None

    def __init__(self, schema: Schema | None = None) -> None:
        """
        title: Initialize a schema; None denotes checked runtime schema access.
        parameters:
          schema:
            type: Schema | None
        """
        super().__init__()
        self.schema = schema

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Preserve empty and runtime schemas distinctly in AST snapshots.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            type(self).__name__,
            {
                "schema": "runtime"
                if self.schema is None
                else self.schema.get_struct(),
            },
            simplified,
        )


@public
@typechecked
class RecordBatchType(SchemaValueType):
    """
    title: An equal-length collection of arrays governed by a schema.
    attributes:
      schema:
        type: Schema | None
    """


@public
@typechecked
class TableType(SchemaValueType):
    """
    title: An equal-length collection of chunked columns.
    attributes:
      schema:
        type: Schema | None
    """


@public
@typechecked
class StreamType(SchemaValueType):
    """
    title: A single-pass stream of record batches governed by a schema.
    attributes:
      schema:
        type: Schema | None
    """


@public
@typechecked
class SchemaType(AnyType):
    """
    title: The type of a runtime schema descriptor value.
    """


@public
@typechecked
class FieldType(AnyType):
    """
    title: The type of a runtime field descriptor value.
    """


@public
@typechecked
class CDataType(AnyType):
    """
    title: An owned interchange value, never an unchecked pair of raw pointers.
    """


@public
@typechecked
class TypeDescriptorType(AnyType):
    """
    title: The type of an immutable runtime logical type descriptor.
    """
