"""
title: Resolved descriptor calls and portable C Data schema constants.
summary: >-
  Lowering consumes these immutable facts without inspecting logical types.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import astx

from public import private, public

from irx.analysis.schema import (
    INT32_MAX,
    SchemaError,
    canonical_schema,
    parameter_value,
)
from irx.analysis.schema_types import ResolvedLogicalType, resolve_logical_type
from irx.typecheck import typechecked


@public
@typechecked
class DescriptorOutput(Enum):
    """
    title: Native output representations for the closed descriptor ABI.
    """

    STRING = "string"
    HANDLE = "handle"
    BOOLEAN = "boolean"
    INT64 = "int64"


@public
@typechecked
@dataclass(frozen=True)
class ResolvedCSchema:
    """
    title: Validated portable C Data fields, independent of compiler addresses.
    attributes:
      physical:
        type: ResolvedLogicalType
      name:
        type: str
      metadata:
        type: tuple[tuple[bytes, bytes], Ellipsis]
      flags:
        type: int
      children:
        type: tuple[ResolvedCSchema, Ellipsis]
      dictionary:
        type: ResolvedCSchema | None
    """

    physical: ResolvedLogicalType
    name: str
    metadata: tuple[tuple[bytes, bytes], ...]
    flags: int
    children: tuple[ResolvedCSchema, ...]
    dictionary: ResolvedCSchema | None = None


@public
@typechecked
@dataclass(frozen=True)
class ResolvedDescriptor:
    """
    title: Complete native call selection and representation for a descriptor.
    attributes:
      symbol:
        type: str
      output:
        type: DescriptorOutput
      literal:
        type: ResolvedCSchema | None
      required_features:
        type: tuple[str, Ellipsis]
      required_feature_version:
        type: int
      index_bit_width:
        type: int | None
    """

    symbol: str
    output: DescriptorOutput
    literal: ResolvedCSchema | None = None
    required_features: tuple[str, ...] = ("array",)
    required_feature_version: int = 0x00010200
    index_bit_width: int | None = None


@public
@typechecked
def resolve_c_schema(field: astx.SchemaField) -> ResolvedCSchema:
    """
    title: Validate and resolve a complete C Data field tree.
    parameters:
      field:
        type: astx.SchemaField
    returns:
      type: ResolvedCSchema
    """
    checked = canonical_schema(astx.Schema((field,))).fields[0]
    return resolve_c_schema_field(checked)


@private
@typechecked
def resolve_c_schema_field(field: astx.SchemaField) -> ResolvedCSchema:
    """
    title: Resolve an already validated child without recanonicalizing it.
    parameters:
      field:
        type: astx.SchemaField
    returns:
      type: ResolvedCSchema
    """
    type_ = field.type_
    metadata = field.metadata
    if type_.kind is astx.LogicalKind.EXTENSION:
        name = parameter_value(type_, astx.ParameterKind.EXTENSION_NAME)
        payload = parameter_value(type_, astx.ParameterKind.EXTENSION_METADATA)
        if not isinstance(name, str) or not isinstance(payload, bytes):
            raise SchemaError("unresolved extension parameters")
        metadata = (
            *metadata,
            (b"ARROW:extension:name", name.encode("utf8")),
            (b"ARROW:extension:metadata", payload),
        )
        type_ = type_.fields[0].type_
    if len(metadata) > INT32_MAX or any(
        len(item) > INT32_MAX for pair in metadata for item in pair
    ):
        raise SchemaError("descriptor metadata exceeds C Data size limit")
    physical = resolve_logical_type(type_)
    flags = 2 if field.nullable else 0
    fields = type_.fields
    dictionary = None
    if type_.kind is astx.LogicalKind.DICTIONARY:
        dictionary = resolve_c_schema_field(fields[1])
        fields = ()
        if parameter_value(type_, astx.ParameterKind.ORDERED):
            flags |= 1
    if type_.kind is astx.LogicalKind.MAP:
        if parameter_value(type_, astx.ParameterKind.KEYS_SORTED):
            flags |= 4
    return ResolvedCSchema(
        physical,
        field.name,
        metadata,
        flags,
        tuple(resolve_c_schema_field(child) for child in fields),
        dictionary,
    )
