"""
title: Canonical logical type and schema validation.
summary: >-
  Keep structural identity and parameter validation independent of PyArrow and
  LLVM. Failures carry a logical field path, never an invented source span.
"""

from __future__ import annotations

import re

from dataclasses import replace
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

from irx.typecheck import typechecked

MAX_SCHEMA_DEPTH = 64
INT32_MAX = 2**31 - 1
INT32_MIN = -(2**31)
UNION_CODE_MAX = 127
MAP_ENTRY_FIELD_COUNT = 2
DECIMAL_PRECISIONS = {
    LogicalKind.DECIMAL32: 9,
    LogicalKind.DECIMAL64: 18,
    LogicalKind.DECIMAL128: 38,
    LogicalKind.DECIMAL256: 76,
}
LIST_KINDS = frozenset(
    {
        LogicalKind.LIST,
        LogicalKind.LARGE_LIST,
        LogicalKind.FIXED_LIST,
        LogicalKind.LIST_VIEW,
        LogicalKind.LARGE_LIST_VIEW,
    }
)
UNION_KINDS = frozenset({LogicalKind.SPARSE_UNION, LogicalKind.DENSE_UNION})
INTEGER_KINDS = frozenset(
    {
        LogicalKind.INT8,
        LogicalKind.INT16,
        LogicalKind.INT32,
        LogicalKind.INT64,
        LogicalKind.UINT8,
        LogicalKind.UINT16,
        LogicalKind.UINT32,
        LogicalKind.UINT64,
    }
)
EXTENSION_KEYS = frozenset(
    {
        b"ARROW:extension:name",
        b"ARROW:extension:metadata",
    }
)
REQUIRED_PARAMETERS: dict[LogicalKind, frozenset[ParameterKind]] = {
    **{
        kind: frozenset({ParameterKind.PRECISION, ParameterKind.SCALE})
        for kind in DECIMAL_PRECISIONS
    },
    **{
        kind: frozenset({ParameterKind.TIME_UNIT})
        for kind in (
            LogicalKind.TIME32,
            LogicalKind.TIME64,
            LogicalKind.TIMESTAMP,
            LogicalKind.DURATION,
        )
    },
    **{kind: frozenset({ParameterKind.TYPE_CODES}) for kind in UNION_KINDS},
    LogicalKind.FIXED_BINARY: frozenset({ParameterKind.BYTE_WIDTH}),
    LogicalKind.FIXED_LIST: frozenset({ParameterKind.LIST_SIZE}),
    LogicalKind.EXTENSION: frozenset(
        {
            ParameterKind.EXTENSION_NAME,
            ParameterKind.EXTENSION_METADATA,
        }
    ),
}
DEFAULT_PARAMETERS: dict[LogicalKind, LogicalParameter] = {
    LogicalKind.TIMESTAMP: LogicalParameter(ParameterKind.TIMEZONE, ""),
    LogicalKind.DICTIONARY: LogicalParameter(ParameterKind.ORDERED, False),
    LogicalKind.MAP: LogicalParameter(ParameterKind.KEYS_SORTED, False),
}


@public
@typechecked
class SchemaError(ValueError):
    """
    title: An invalid or unsupported schema component with a logical path.
    attributes:
      path:
        type: tuple[str, Ellipsis]
      detail:
        type: str
    """

    path: tuple[str, ...]
    detail: str

    def __init__(self, message: str, path: tuple[str, ...] = ()) -> None:
        """
        title: Preserve structured details for host diagnostics.
        parameters:
          message:
            type: str
          path:
            type: tuple[str, Ellipsis]
        """
        self.path = path
        self.detail = message
        super().__init__(f"{'/'.join(path) or '<schema>'}: {message}")


@private
@typechecked
def validate_text(value: str, path: tuple[str, ...]) -> None:
    """
    title: Reject names that cannot round-trip through C Data UTF-8 strings.
    parameters:
      value:
        type: str
      path:
        type: tuple[str, Ellipsis]
    """
    if "\x00" in value:
        raise SchemaError("text must not contain NUL", path)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise SchemaError("text must be valid UTF-8", path) from error


@public
@typechecked
def canonical_metadata(
    metadata: Metadata, *, path: tuple[str, ...] = ()
) -> Metadata:
    """
    title: Canonicalize binary metadata without decoding or losing bytes.
    parameters:
      metadata:
        type: Metadata
      path:
        type: tuple[str, Ellipsis]
    returns:
      type: Metadata
    """
    keys = [key for key, _ in metadata]
    if len(set(keys)) != len(keys):
        raise SchemaError("duplicate metadata keys", path)
    return tuple(sorted(metadata))


@private
@typechecked
def validate_timezone(value: str, path: tuple[str, ...]) -> None:
    """
    title: Validate naive, IANA, or signed hour-minute timezone annotations.
    parameters:
      value:
        type: str
      path:
        type: tuple[str, Ellipsis]
    """
    validate_text(value, path)
    if not value:
        return
    if re.fullmatch(r"[+-](?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        return
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise SchemaError(f"unknown timezone {value!r}", path) from error


@private
@typechecked
def validate_parameter(
    kind: LogicalKind, parameter: LogicalParameter, path: tuple[str, ...]
) -> None:
    """
    title: Validate one parameter domain using the pinned Arrow contract.
    parameters:
      kind:
        type: LogicalKind
      parameter:
        type: LogicalParameter
      path:
        type: tuple[str, Ellipsis]
    """
    key, value = parameter.kind, parameter.value
    if key is ParameterKind.TIME_UNIT:
        allowed = set(TimeUnit)
        if kind is LogicalKind.TIME32:
            allowed = {TimeUnit.SECOND, TimeUnit.MILLISECOND}
        if kind is LogicalKind.TIME64:
            allowed = {TimeUnit.MICROSECOND, TimeUnit.NANOSECOND}
        if not isinstance(value, TimeUnit) or value not in allowed:
            raise SchemaError(f"invalid {kind.value} time unit", path)
        return
    if key in {ParameterKind.KEYS_SORTED, ParameterKind.ORDERED}:
        if type(value) is not bool:
            raise SchemaError(f"{key.value} must be Boolean", path)
        return
    if key is ParameterKind.TYPE_CODES:
        if not isinstance(value, tuple) or any(
            type(code) is not int or not 0 <= code <= UNION_CODE_MAX
            for code in value
        ):
            raise SchemaError("union codes must be integers in [0, 127]", path)
        if len(set(value)) != len(value):
            raise SchemaError("duplicate union codes", path)
        return
    if key is ParameterKind.EXTENSION_METADATA:
        if not isinstance(value, bytes):
            raise SchemaError("extension metadata must be bytes", path)
        return
    if key in {ParameterKind.EXTENSION_NAME, ParameterKind.TIMEZONE}:
        if not isinstance(value, str):
            raise SchemaError(f"{key.value} must be text", path)
        validate_text(value, path)
        if key is ParameterKind.TIMEZONE:
            validate_timezone(value, path)
        elif not value:
            raise SchemaError("extension name must not be empty", path)
        return
    if type(value) is not int or not INT32_MIN <= value <= INT32_MAX:
        raise SchemaError(f"{key.value} must be a signed 32-bit integer", path)
    if key is ParameterKind.PRECISION:
        if not 1 <= value <= DECIMAL_PRECISIONS[kind]:
            raise SchemaError(f"invalid {kind.value} precision", path)
    elif key in {ParameterKind.BYTE_WIDTH, ParameterKind.LIST_SIZE}:
        if value < 0:
            raise SchemaError(f"{key.value} must be nonnegative", path)


@private
@typechecked
def canonical_parameters(
    type_: LogicalType, path: tuple[str, ...]
) -> tuple[LogicalParameter, ...]:
    """
    title: Reject duplicate, missing, and irrelevant type parameters.
    parameters:
      type_:
        type: LogicalType
      path:
        type: tuple[str, Ellipsis]
    returns:
      type: tuple[LogicalParameter, Ellipsis]
    """
    parameters = {parameter.kind: parameter for parameter in type_.parameters}
    if len(parameters) != len(type_.parameters):
        raise SchemaError("duplicate logical parameters", path)
    required = REQUIRED_PARAMETERS.get(type_.kind, frozenset())
    default = DEFAULT_PARAMETERS.get(type_.kind)
    allowed = required | ({default.kind} if default is not None else set())
    if set(parameters) - allowed:
        raise SchemaError("unexpected logical parameters", path)
    if required - set(parameters):
        raise SchemaError("missing required logical parameters", path)
    if default is not None:
        parameters.setdefault(default.kind, default)
    for parameter in parameters.values():
        validate_parameter(type_.kind, parameter, path)
    return tuple(sorted(parameters.values(), key=lambda item: item.kind.value))


@public
@typechecked
def parameter_value(type_: LogicalType, key: ParameterKind) -> ParameterValue:
    """
    title: Read one parameter from a validated descriptor.
    parameters:
      type_:
        type: LogicalType
      key:
        type: ParameterKind
    returns:
      type: ParameterValue
    """
    for parameter in type_.parameters:
        if parameter.kind is key:
            return parameter.value
    raise SchemaError(f"missing parameter {key.value}")


@private
@typechecked
def validate_synthetic_field(
    field: SchemaField, name: str, path: tuple[str, ...]
) -> None:
    """
    title: Prevent metadata loss on children representing type parameters.
    parameters:
      field:
        type: SchemaField
      name:
        type: str
      path:
        type: tuple[str, Ellipsis]
    """
    if field.name != name or field.nullable or field.metadata:
        raise SchemaError(
            f"{name} must be a nonnullable bare type child", path
        )


@private
@typechecked
def validate_nested(type_: LogicalType, path: tuple[str, ...]) -> None:
    """
    title: Validate recursive child cardinality and physical invariants.
    parameters:
      type_:
        type: LogicalType
      path:
        type: tuple[str, Ellipsis]
    """
    kind, fields = type_.kind, type_.fields
    counts = {
        **{kind: 1 for kind in LIST_KINDS},
        LogicalKind.MAP: 1,
        LogicalKind.EXTENSION: 1,
        LogicalKind.DICTIONARY: 2,
        LogicalKind.RUN_END_ENCODED: 2,
    }
    expected = counts.get(kind, 0)
    if kind not in {*UNION_KINDS, LogicalKind.STRUCT}:
        if len(fields) != expected:
            raise SchemaError(
                f"{kind.value} requires {expected} children", path
            )
    if kind in UNION_KINDS:
        codes = parameter_value(type_, ParameterKind.TYPE_CODES)
        if not isinstance(codes, tuple) or len(codes) != len(fields):
            raise SchemaError("union codes must match the child count", path)
    if kind is LogicalKind.MAP:
        entries = fields[0]
        if entries.nullable or entries.type_.kind is not LogicalKind.STRUCT:
            raise SchemaError("map entries must be a nonnullable struct", path)
        if len(entries.type_.fields) != MAP_ENTRY_FIELD_COUNT:
            raise SchemaError("map entries require key and value fields", path)
        if entries.type_.fields[0].nullable:
            raise SchemaError("map keys must not be nullable", path)
        if (
            entries.name != "entries"
            or entries.metadata
            or tuple(field.name for field in entries.type_.fields)
            != ("key", "value")
        ):
            raise SchemaError(
                "map children require entries/key/value names and no "
                "entries metadata to round-trip through C Data",
                path,
            )
    if kind is LogicalKind.DICTIONARY:
        validate_synthetic_field(fields[0], "indices", path)
        validate_synthetic_field(fields[1], "values", path)
        if fields[0].type_.kind not in INTEGER_KINDS:
            raise SchemaError("dictionary indices must be integers", path)
    if kind is LogicalKind.EXTENSION:
        validate_synthetic_field(fields[0], "storage", path)
        if fields[0].type_.kind is LogicalKind.EXTENSION:
            raise SchemaError("extension storage cannot be an extension", path)
    if kind is LogicalKind.RUN_END_ENCODED:
        run_ends = fields[0]
        validate_synthetic_field(run_ends, "run_ends", path)
        values = fields[1]
        if (
            values.name != "values"
            or not values.nullable
            or values.metadata
            or values.type_.kind is LogicalKind.RUN_END_ENCODED
        ):
            raise SchemaError(
                "run-end values require a nullable bare values child and "
                "must not themselves be run-end encoded",
                path,
            )
        if run_ends.nullable or run_ends.type_.kind not in {
            LogicalKind.INT16,
            LogicalKind.INT32,
            LogicalKind.INT64,
        }:
            raise SchemaError("run ends require nonnullable int16/32/64", path)


@private
@typechecked
def canonical_fields(
    fields: tuple[SchemaField, ...], path: tuple[str, ...], depth: int
) -> tuple[SchemaField, ...]:
    """
    title: Validate field identity, child types and metadata recursively.
    parameters:
      fields:
        type: tuple[SchemaField, Ellipsis]
      path:
        type: tuple[str, Ellipsis]
      depth:
        type: int
    returns:
      type: tuple[SchemaField, Ellipsis]
    """
    names = [field.name for field in fields]
    if len(set(names)) != len(names):
        raise SchemaError("duplicate field names", path)
    result: list[SchemaField] = []
    for field in fields:
        child_path = (*path, field.name)
        validate_text(field.name, child_path)
        metadata = canonical_metadata(field.metadata, path=child_path)
        if any(key in EXTENSION_KEYS for key, _ in metadata):
            raise SchemaError(
                "use an extension descriptor for reserved keys", child_path
            )
        result.append(
            replace(
                field,
                type_=canonical_logical_type(
                    field.type_, path=child_path, depth=depth + 1
                ),
                metadata=metadata,
            )
        )
    return tuple(result)


@public
@typechecked
def canonical_logical_type(
    type_: LogicalType, *, path: tuple[str, ...] = (), depth: int = 0
) -> LogicalType:
    """
    title: Resolve structural logical identity and reject invalid recursion.
    parameters:
      type_:
        type: LogicalType
      path:
        type: tuple[str, Ellipsis]
      depth:
        type: int
    returns:
      type: LogicalType
    """
    if depth >= MAX_SCHEMA_DEPTH:
        raise SchemaError("schema exceeds maximum nesting depth", path)
    result = replace(
        type_,
        parameters=canonical_parameters(type_, path),
        fields=canonical_fields(type_.fields, path, depth),
    )
    validate_nested(result, path)
    return result


@public
@typechecked
def canonical_schema(schema: Schema) -> Schema:
    """
    title: Validate a static schema while preserving ordered fields.
    parameters:
      schema:
        type: Schema
    returns:
      type: Schema
    """
    metadata = canonical_metadata(schema.metadata)
    if any(key in EXTENSION_KEYS for key, _ in metadata):
        raise SchemaError("reserved extension keys require an extension type")
    return Schema(canonical_fields(schema.fields, (), 0), metadata=metadata)
