"""
title: Lossless logical type and schema compatibility.
summary: >-
  Classify conversions without executing casts. Narrowing, nullable removal,
  temporal rescaling, dictionaries, and metadata loss require explicit checks;
  unrelated nested layouts are incompatible.
"""

from __future__ import annotations

from enum import IntEnum

from astx.schema import (
    LogicalKind,
    LogicalType,
    ParameterKind,
    Schema,
    SchemaField,
)
from public import private, public

from irx.analysis.schema import (
    DECIMAL_PRECISIONS,
    INTEGER_KINDS,
    canonical_logical_type,
    canonical_schema,
    parameter_value,
)
from irx.analysis.schema_types import BIT_WIDTHS
from irx.typecheck import typechecked

FLOAT_MANTISSA_BITS = {
    LogicalKind.FLOAT16: 11,
    LogicalKind.FLOAT32: 24,
    LogicalKind.FLOAT64: 53,
}
OFFSET_WIDENING = {
    LogicalKind.STRING: LogicalKind.LARGE_STRING,
    LogicalKind.BINARY: LogicalKind.LARGE_BINARY,
    LogicalKind.LIST: LogicalKind.LARGE_LIST,
    LogicalKind.LIST_VIEW: LogicalKind.LARGE_LIST_VIEW,
}


@public
@typechecked
class SchemaConversion(IntEnum):
    """
    title: Increasing requirements for one structural conversion.
    """

    EXACT = 0
    LOSSLESS = 1
    EXPLICIT = 2
    INCOMPATIBLE = 3


@private
@typechecked
def numeric_conversion(
    source: LogicalKind, target: LogicalKind
) -> SchemaConversion:
    """
    title: Classify whole-domain numeric representability.
    parameters:
      source:
        type: LogicalKind
      target:
        type: LogicalKind
    returns:
      type: SchemaConversion
    """
    if source in INTEGER_KINDS and target in INTEGER_KINDS:
        source_signed = source.value.startswith("int")
        target_signed = target.value.startswith("int")
        widening = BIT_WIDTHS[target] >= BIT_WIDTHS[source]
        if source_signed != target_signed:
            widening = (
                target_signed and BIT_WIDTHS[target] > BIT_WIDTHS[source]
            )
        return (
            SchemaConversion.LOSSLESS
            if widening
            else SchemaConversion.EXPLICIT
        )
    if source in FLOAT_MANTISSA_BITS and target in FLOAT_MANTISSA_BITS:
        return (
            SchemaConversion.LOSSLESS
            if BIT_WIDTHS[target] >= BIT_WIDTHS[source]
            else SchemaConversion.EXPLICIT
        )
    if source in INTEGER_KINDS and target in FLOAT_MANTISSA_BITS:
        bits = BIT_WIDTHS[source] - int(source.value.startswith("int"))
        return (
            SchemaConversion.LOSSLESS
            if FLOAT_MANTISSA_BITS[target] >= bits
            else SchemaConversion.EXPLICIT
        )
    numeric = INTEGER_KINDS | FLOAT_MANTISSA_BITS.keys()
    if source in numeric and target in numeric:
        return SchemaConversion.EXPLICIT
    return SchemaConversion.INCOMPATIBLE


@private
@typechecked
def field_conversion(
    source: SchemaField, target: SchemaField
) -> SchemaConversion:
    """
    title: Preserve names and independently classify nullability and metadata.
    parameters:
      source:
        type: SchemaField
      target:
        type: SchemaField
    returns:
      type: SchemaConversion
    """
    if source.name != target.name:
        return SchemaConversion.INCOMPATIBLE
    result = (
        SchemaConversion.LOSSLESS
        if source.type_.kind is LogicalKind.NULL and target.nullable
        else canonical_conversion(source.type_, target.type_)
    )
    if (
        source.nullable and not target.nullable
    ) or source.metadata != target.metadata:
        return max(result, SchemaConversion.EXPLICIT)
    if source.nullable != target.nullable:
        return max(result, SchemaConversion.LOSSLESS)
    return result


@private
@typechecked
def children_conversion(
    source: tuple[SchemaField, ...], target: tuple[SchemaField, ...]
) -> SchemaConversion:
    """
    title: Classify nested fields without reordering or dropping columns.
    parameters:
      source:
        type: tuple[SchemaField, Ellipsis]
      target:
        type: tuple[SchemaField, Ellipsis]
    returns:
      type: SchemaConversion
    """
    if len(source) != len(target):
        return SchemaConversion.INCOMPATIBLE
    return max(
        (field_conversion(a, b) for a, b in zip(source, target)),
        default=SchemaConversion.EXACT,
    )


@private
@typechecked
def decimal_conversion(
    source: LogicalType, target: LogicalType
) -> SchemaConversion:
    """
    title: Preserve decimal scale and whole-domain integer digits.
    parameters:
      source:
        type: LogicalType
      target:
        type: LogicalType
    returns:
      type: SchemaConversion
    """
    source_precision = parameter_value(source, ParameterKind.PRECISION)
    source_scale = parameter_value(source, ParameterKind.SCALE)
    target_precision = parameter_value(target, ParameterKind.PRECISION)
    target_scale = parameter_value(target, ParameterKind.SCALE)
    if (
        isinstance(source_precision, int)
        and isinstance(source_scale, int)
        and isinstance(target_precision, int)
        and isinstance(target_scale, int)
        and target_scale >= source_scale
        and target_precision - target_scale >= source_precision - source_scale
    ):
        return SchemaConversion.LOSSLESS
    return SchemaConversion.EXPLICIT


@private
@typechecked
def canonical_conversion(
    source: LogicalType, target: LogicalType
) -> SchemaConversion:
    """
    title: Classify canonical descriptors conservatively.
    parameters:
      source:
        type: LogicalType
      target:
        type: LogicalType
    returns:
      type: SchemaConversion
    """
    if source == target:
        return SchemaConversion.EXACT
    if (
        source.kind is LogicalKind.EXTENSION
        or target.kind is LogicalKind.EXTENSION
    ):
        return SchemaConversion.INCOMPATIBLE
    if source.kind in DECIMAL_PRECISIONS and target.kind in DECIMAL_PRECISIONS:
        return decimal_conversion(source, target)
    if (
        source.kind is target.kind
        or OFFSET_WIDENING.get(source.kind) is target.kind
    ):
        nested = children_conversion(source.fields, target.fields)
        if source.kind is LogicalKind.DICTIONARY:
            return max(nested, SchemaConversion.EXPLICIT)
        if source.parameters != target.parameters:
            return max(nested, SchemaConversion.EXPLICIT)
        return max(nested, SchemaConversion.LOSSLESS)
    return numeric_conversion(source.kind, target.kind)


@public
@typechecked
def logical_conversion(
    source: LogicalType, target: LogicalType
) -> SchemaConversion:
    """
    title: Validate descriptors before selecting an implicit or explicit cast.
    parameters:
      source:
        type: LogicalType
      target:
        type: LogicalType
    returns:
      type: SchemaConversion
    """
    return canonical_conversion(
        canonical_logical_type(source), canonical_logical_type(target)
    )


@public
@typechecked
def schema_conversion(source: Schema, target: Schema) -> SchemaConversion:
    """
    title: Classify a schema conversion including schema-level metadata.
    parameters:
      source:
        type: Schema
      target:
        type: Schema
    returns:
      type: SchemaConversion
    """
    source, target = canonical_schema(source), canonical_schema(target)
    result = children_conversion(source.fields, target.fields)
    if source.metadata != target.metadata:
        return max(result, SchemaConversion.EXPLICIT)
    return result
