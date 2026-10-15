"""
title: Host-only schema interchange through Arrow C Data.
summary: >-
  Exchange immutable ASTx descriptors with PyArrow without serializing C++
  layouts. This is a Python interoperability API, not a language execution
  fallback. Temporary C structs borrow Python-owned buffers synchronously.
"""

from __future__ import annotations

import ctypes
import struct

import pyarrow as pa

from astx.schema import (
    LogicalKind,
    LogicalParameter,
    LogicalType,
    Metadata,
    ParameterKind,
    ParameterValue,
    Schema,
    SchemaField,
    TimeUnit,
)
from public import private, public

from irx.analysis.schema import (
    INT32_MAX,
    MAX_SCHEMA_DEPTH,
    SchemaError,
    canonical_schema,
    parameter_value,
)
from irx.analysis.schema_types import (
    SIMPLE_FORMATS,
    TIME_FORMAT_UNITS,
    logical_c_format,
)
from irx.typecheck import typechecked

NULLABLE_FLAG = 2
ORDERED_FLAG = 1
KEYS_SORTED_FLAG = 4
DECIMAL_FORMAT_PARTS = 3
EXTENSION_NAME_KEY = b"ARROW:extension:name"
EXTENSION_METADATA_KEY = b"ARROW:extension:metadata"


@private
@typechecked
class CSchema(ctypes.Structure):
    """
    title: The standard Arrow C Data schema layout, never a C++ layout.
    """

    _fields_ = [
        ("format", ctypes.c_char_p),
        ("name", ctypes.c_char_p),
        ("metadata", ctypes.c_void_p),
        ("flags", ctypes.c_int64),
        ("n_children", ctypes.c_int64),
        ("children", ctypes.POINTER(ctypes.c_void_p)),
        ("dictionary", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("private_data", ctypes.c_void_p),
    ]


@private
@typechecked
def release_schema(address: int | None) -> None:
    """
    title: Mark a borrowed temporary consumed; its Python owner frees buffers.
    parameters:
      address:
        type: int | None
    """
    if address is not None:
        CSchema.from_address(address).release = None


SCHEMA_RELEASE = ctypes.CFUNCTYPE(None, ctypes.c_void_p)(release_schema)


@private
@typechecked
def encode_metadata(metadata: Metadata) -> bytes:
    """
    title: Encode binary metadata using the native-endian C Data contract.
    parameters:
      metadata:
        type: Metadata
    returns:
      type: bytes
    """
    if len(metadata) > INT32_MAX:
        raise SchemaError("too many metadata entries")
    result = bytearray(struct.pack("=i", len(metadata)))
    for key, value in metadata:
        for item in (key, value):
            if len(item) > INT32_MAX:
                raise SchemaError("metadata entry exceeds C Data size limit")
            result.extend(struct.pack("=i", len(item)))
            result.extend(item)
    return bytes(result)


@private
@typechecked
class SchemaExport:
    """
    title: Keep a complete temporary C schema tree alive during import.
    attributes:
      schema:
        type: CSchema
      dictionary:
        type: SchemaExport | None
      children:
        type: tuple[SchemaExport, Ellipsis]
      child_addresses:
        type: ctypes.Array[ctypes.c_void_p]
      metadata_buffer:
        type: ctypes.Array[ctypes.c_char]
    """

    schema: CSchema
    dictionary: SchemaExport | None
    children: tuple[SchemaExport, ...]
    child_addresses: ctypes.Array[ctypes.c_void_p]
    metadata_buffer: ctypes.Array[ctypes.c_char]

    def __init__(self, field: SchemaField) -> None:
        """
        title: Build borrowed C structs from an already validated field.
        parameters:
          field:
            type: SchemaField
        """
        type_ = field.type_
        metadata = field.metadata
        if type_.kind is LogicalKind.EXTENSION:
            name = parameter_value(type_, ParameterKind.EXTENSION_NAME)
            payload = parameter_value(type_, ParameterKind.EXTENSION_METADATA)
            if not isinstance(name, str) or not isinstance(payload, bytes):
                raise SchemaError("unresolved extension parameters")
            metadata = (
                *metadata,
                (EXTENSION_NAME_KEY, name.encode("utf-8")),
                (EXTENSION_METADATA_KEY, payload),
            )
            type_ = type_.fields[0].type_
        self.schema = CSchema()
        self.schema.format = logical_c_format(type_).encode("utf-8")
        self.schema.name = field.name.encode("utf-8")
        self.schema.flags = NULLABLE_FLAG if field.nullable else 0
        self.dictionary: SchemaExport | None = None
        fields = type_.fields
        if type_.kind is LogicalKind.DICTIONARY:
            self.dictionary = SchemaExport(fields[1])
            self.schema.dictionary = ctypes.addressof(self.dictionary.schema)
            if parameter_value(type_, ParameterKind.ORDERED):
                self.schema.flags |= ORDERED_FLAG
            fields = ()
        if type_.kind is LogicalKind.MAP:
            if parameter_value(type_, ParameterKind.KEYS_SORTED):
                self.schema.flags |= KEYS_SORTED_FLAG
        self.children = tuple(SchemaExport(child) for child in fields)
        self.child_addresses = (ctypes.c_void_p * len(self.children))(
            *(ctypes.addressof(child.schema) for child in self.children)
        )
        self.schema.n_children = len(self.children)
        self.schema.children = self.child_addresses
        self.metadata_buffer = ctypes.create_string_buffer(
            encode_metadata(metadata)
        )
        self.schema.metadata = ctypes.addressof(self.metadata_buffer)
        self.schema.release = ctypes.cast(
            SCHEMA_RELEASE, ctypes.c_void_p
        ).value


@private
@typechecked
def decode_metadata(address: int | None) -> Metadata:
    """
    title: Read metadata only from a live, trusted PyArrow-owned C schema.
    parameters:
      address:
        type: int | None
    returns:
      type: Metadata
    """
    if address is None:
        return ()
    count = ctypes.c_int32.from_address(address).value
    if count < 0:
        raise SchemaError("negative metadata count")
    offset = address + ctypes.sizeof(ctypes.c_int32)
    items: list[bytes] = []
    for _ in range(count * 2):
        size = ctypes.c_int32.from_address(offset).value
        if size < 0:
            raise SchemaError("negative metadata length")
        offset += ctypes.sizeof(ctypes.c_int32)
        items.append(ctypes.string_at(offset, size))
        offset += size
    return tuple(zip(items[::2], items[1::2]))


@private
@typechecked
def parameterized(
    kind: LogicalKind,
    *parameters: tuple[ParameterKind, ParameterValue],
    fields: tuple[SchemaField, ...] = (),
) -> LogicalType:
    """
    title: Build parsed parameters after checking the supported value domain.
    parameters:
      kind:
        type: LogicalKind
      fields:
        type: tuple[SchemaField, Ellipsis]
      parameters:
        type: tuple[ParameterKind, ParameterValue]
        variadic: positional
    returns:
      type: LogicalType
    """
    return LogicalType(
        kind,
        fields=fields,
        parameters=tuple(
            LogicalParameter(key, value) for key, value in parameters
        ),
    )


@private
@typechecked
def parse_format(format_: str, fields: tuple[SchemaField, ...]) -> LogicalType:
    """
    title: Decode the C Data logical format without consulting Python classes.
    parameters:
      format_:
        type: str
      fields:
        type: tuple[SchemaField, Ellipsis]
    returns:
      type: LogicalType
    """
    simple = {value: key for key, value in SIMPLE_FORMATS.items()}
    if format_ in simple:
        return LogicalType(simple[format_], fields=fields)
    prefix, _, suffix = format_.partition(":")
    if prefix in {"w", "+w"}:
        kind = (
            LogicalKind.FIXED_BINARY
            if prefix == "w"
            else LogicalKind.FIXED_LIST
        )
        key = (
            ParameterKind.BYTE_WIDTH
            if prefix == "w"
            else ParameterKind.LIST_SIZE
        )
        return parameterized(kind, (key, int(suffix)), fields=fields)
    if prefix == "d":
        parts = [int(part) for part in suffix.split(",")]
        width = parts[2] if len(parts) == DECIMAL_FORMAT_PARTS else 128
        return parameterized(
            LogicalKind(f"decimal{width}"),
            (ParameterKind.PRECISION, parts[0]),
            (ParameterKind.SCALE, parts[1]),
        )
    if prefix in {"+ud", "+us"}:
        kind = (
            LogicalKind.DENSE_UNION
            if prefix == "+ud"
            else LogicalKind.SPARSE_UNION
        )
        codes = (
            tuple(int(code) for code in suffix.split(",")) if suffix else ()
        )
        return parameterized(
            kind, (ParameterKind.TYPE_CODES, codes), fields=fields
        )
    unit_code = prefix[-1:]
    units = {code: unit for unit, code in TIME_FORMAT_UNITS.items()}
    if unit_code not in units:
        raise SchemaError(f"unsupported C Data format {format_!r}")
    unit = units[unit_code]
    if prefix.startswith("ts"):
        return parameterized(
            LogicalKind.TIMESTAMP,
            (ParameterKind.TIME_UNIT, unit),
            (ParameterKind.TIMEZONE, suffix),
        )
    if prefix.startswith("tD"):
        return parameterized(
            LogicalKind.DURATION, (ParameterKind.TIME_UNIT, unit)
        )
    if prefix.startswith("tt"):
        kind = (
            LogicalKind.TIME32
            if unit in {TimeUnit.SECOND, TimeUnit.MILLISECOND}
            else LogicalKind.TIME64
        )
        return parameterized(kind, (ParameterKind.TIME_UNIT, unit))
    raise SchemaError(f"unsupported C Data format {format_!r}")


@private
@typechecked
def import_field(
    address: int, depth: int = 0, *, schema_root: bool = False
) -> SchemaField:
    """
    title: Copy a live PyArrow schema recursively before releasing its capsule.
    parameters:
      address:
        type: int
      depth:
        type: int
      schema_root:
        type: bool
    returns:
      type: SchemaField
    """
    if depth >= MAX_SCHEMA_DEPTH:
        raise SchemaError("schema exceeds maximum nesting depth")
    schema = CSchema.from_address(address)
    if not schema.release or schema.format is None or schema.n_children < 0:
        raise SchemaError("invalid or released C schema")
    fields = tuple(
        import_field(schema.children[index], depth + 1)
        for index in range(schema.n_children)
    )
    type_ = parse_format(schema.format.decode("utf-8"), fields)
    if schema.dictionary:
        dictionary = import_field(schema.dictionary, depth + 1)
        if dictionary.metadata:
            raise SchemaError("dictionary value field metadata is unsupported")
        type_ = parameterized(
            LogicalKind.DICTIONARY,
            (ParameterKind.ORDERED, bool(schema.flags & ORDERED_FLAG)),
            fields=(
                SchemaField("indices", type_),
                SchemaField("values", dictionary.type_),
            ),
        )
    if type_.kind is LogicalKind.MAP:
        type_ = parameterized(
            LogicalKind.MAP,
            (ParameterKind.KEYS_SORTED, bool(schema.flags & KEYS_SORTED_FLAG)),
            fields=fields,
        )
    metadata = decode_metadata(schema.metadata)
    metadata_map = dict(metadata)
    if len(metadata_map) != len(metadata):
        raise SchemaError("duplicate metadata keys")
    if not schema_root and EXTENSION_NAME_KEY in metadata_map:
        name = metadata_map.pop(EXTENSION_NAME_KEY).decode("utf-8")
        payload = metadata_map.pop(EXTENSION_METADATA_KEY, b"")
        type_ = parameterized(
            LogicalKind.EXTENSION,
            (ParameterKind.EXTENSION_NAME, name),
            (ParameterKind.EXTENSION_METADATA, payload),
            fields=(SchemaField("storage", type_),),
        )
    return SchemaField(
        (schema.name or b"").decode("utf-8"),
        type_,
        nullable=bool(schema.flags & NULLABLE_FLAG),
        metadata=tuple(metadata_map.items()),
    )


@public
@typechecked
def schema_to_pyarrow(schema: Schema) -> pa.Schema:
    """
    title: Copy a validated logical schema into a PyArrow schema via C Data.
    parameters:
      schema:
        type: Schema
    returns:
      type: pa.Schema
    """
    schema = canonical_schema(schema)
    export = SchemaExport(
        SchemaField(
            "",
            LogicalType(LogicalKind.STRUCT, fields=schema.fields),
            metadata=schema.metadata,
        )
    )
    return pa.Schema._import_from_c(ctypes.addressof(export.schema))


@public
@typechecked
def schema_from_pyarrow(schema: pa.Schema) -> Schema:
    """
    title: Copy PyArrow schema metadata into backend-independent descriptors.
    parameters:
      schema:
        type: pa.Schema
    returns:
      type: Schema
    """
    capsule = schema.__arrow_c_schema__()
    get_pointer = ctypes.pythonapi.PyCapsule_GetPointer
    get_pointer.argtypes = [ctypes.py_object, ctypes.c_char_p]
    get_pointer.restype = ctypes.c_void_p
    address = get_pointer(capsule, b"arrow_schema")
    root = import_field(address, schema_root=True)
    if root.type_.kind is not LogicalKind.STRUCT:
        raise SchemaError("a schema requires a struct root")
    return canonical_schema(Schema(root.type_.fields, metadata=root.metadata))
