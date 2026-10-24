"""
title: Value-preserving numeric promotion and conversion classification.
summary: >-
  Describe the checked-arithmetic policy independently of LLVM and runtime
  values. This policy covers fixed-width 8-64 bit integers and f16/f32/f64;
  Boolean, nullable, vector, and storage types must be handled by their owning
  semantic resolvers. Classification does not perform a conversion or a check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import astx

from public import private, public

from irx.typecheck import typechecked

SIGNED_TYPES: dict[type[astx.DataType], int] = {
    astx.Int8: 8,
    astx.Int16: 16,
    astx.Int32: 32,
    astx.Int64: 64,
}
UNSIGNED_TYPES: dict[type[astx.DataType], int] = {
    astx.UInt8: 8,
    astx.UInt16: 16,
    astx.UInt32: 32,
    astx.UInt64: 64,
}
FLOAT_PRECISIONS: dict[type[astx.DataType], int] = {
    astx.Float16: 11,
    astx.Float32: 24,
    astx.Float64: 53,
}
FLOAT16_MAX_FINITE_INTEGER = 65504


@public
@typechecked
class NumericConversionKind(str, Enum):
    """
    title: Numeric conversion semantics before choosing an execution mechanism.
    """

    IDENTITY = "identity"
    LOSSLESS = "lossless"
    INTEGER_RANGE = "integer_range"
    FLOAT_TO_INTEGER = "float_to_integer"
    INTEGER_TO_FLOAT = "integer_to_float"
    FLOAT_NARROW = "float_narrow"


@public
@typechecked
@dataclass(frozen=True)
class NumericConversion:
    """
    title: >-
      Classification of a numeric conversion under the checked numeric policy.
    summary: >-
      A required range check must precede publication of the converted value.
      Explicit floating conversions may round or truncate even when a range
      check succeeds; implicit conversions may not lose source-domain values.
    attributes:
      source_type:
        type: astx.DataType
      target_type:
        type: astx.DataType
      kind:
        type: NumericConversionKind
      implicit:
        type: bool
      requires_range_check:
        type: bool
    """

    source_type: astx.DataType
    target_type: astx.DataType
    kind: NumericConversionKind
    implicit: bool
    requires_range_check: bool


@public
@typechecked
def integer_bounds(type_: astx.DataType) -> tuple[int, int] | None:
    """
    title: Return the inclusive domain of a supported integer, excluding bool.
    parameters:
      type_:
        type: astx.DataType
    returns:
      type: tuple[int, int] | None
    """
    width = SIGNED_TYPES.get(type(type_))
    if width is not None:
        return -(1 << (width - 1)), (1 << (width - 1)) - 1
    width = UNSIGNED_TYPES.get(type(type_))
    if width is not None:
        return 0, (1 << width) - 1
    return None


@public
@typechecked
def is_lossless_numeric_conversion(
    source: astx.DataType, target: astx.DataType
) -> bool:
    """
    title: Test containment of full numeric domains, not the current values.
    parameters:
      source:
        type: astx.DataType
      target:
        type: astx.DataType
    returns:
      type: bool
    """
    source_bounds = integer_bounds(source)
    target_bounds = integer_bounds(target)
    if source_bounds is not None and target_bounds is not None:
        return (
            target_bounds[0] <= source_bounds[0]
            and source_bounds[1] <= target_bounds[1]
        )
    source_precision = FLOAT_PRECISIONS.get(type(source))
    target_precision = FLOAT_PRECISIONS.get(type(target))
    if source_precision is not None and target_precision is not None:
        return target_precision >= source_precision
    if source_bounds is not None and target_precision is not None:
        exact_limit = 1 << target_precision
        return (
            -exact_limit <= source_bounds[0]
            and source_bounds[1] <= exact_limit
        )
    return False


@public
@typechecked
def lossless_common_numeric_type(
    lhs: astx.DataType, rhs: astx.DataType
) -> astx.DataType | None:
    """
    title: Select the smallest containing numeric domain or reject the pair.
    summary: >-
      Preserve matching integer signedness; mixed signed/unsigned operands
      require a containing signed type. Integer-only operations never acquire a
      floating result. Mixed floating operands require exact conversion of the
      entire integer domain. Unsupported types fail closed.
    parameters:
      lhs:
        type: astx.DataType
      rhs:
        type: astx.DataType
    returns:
      type: astx.DataType | None
    """
    if type(lhs) in FLOAT_PRECISIONS or type(rhs) in FLOAT_PRECISIONS:
        candidates = FLOAT_PRECISIONS
    elif type(lhs) in UNSIGNED_TYPES and type(rhs) in UNSIGNED_TYPES:
        candidates = UNSIGNED_TYPES
    else:
        candidates = SIGNED_TYPES
    for type_class in candidates:
        candidate = type_class()
        if is_lossless_numeric_conversion(
            lhs, candidate
        ) and is_lossless_numeric_conversion(rhs, candidate):
            return candidate
    return None


@private
@typechecked
def numeric_conversion_kind(
    source: astx.DataType, target: astx.DataType
) -> NumericConversionKind | None:
    """
    title: Classify a supported conversion without inspecting runtime values.
    parameters:
      source:
        type: astx.DataType
      target:
        type: astx.DataType
    returns:
      type: NumericConversionKind | None
    """
    source_integer = integer_bounds(source) is not None
    target_integer = integer_bounds(target) is not None
    source_float = type(source) in FLOAT_PRECISIONS
    target_float = type(target) in FLOAT_PRECISIONS
    if not (source_integer or source_float) or not (
        target_integer or target_float
    ):
        return None
    if type(source) is type(target):
        return NumericConversionKind.IDENTITY
    if is_lossless_numeric_conversion(source, target):
        return NumericConversionKind.LOSSLESS
    if source_integer and target_integer:
        return NumericConversionKind.INTEGER_RANGE
    if source_float and target_integer:
        return NumericConversionKind.FLOAT_TO_INTEGER
    if source_integer and target_float:
        return NumericConversionKind.INTEGER_TO_FLOAT
    return NumericConversionKind.FLOAT_NARROW


@public
@typechecked
def classify_numeric_conversion(
    source: astx.DataType, target: astx.DataType
) -> NumericConversion | None:
    """
    title: Plan implicit eligibility and explicit range checking for numerics.
    summary: >-
      Return None for unsupported domains. Integer-to-float precision loss is
      explicit; a finite-range check is needed only for f16 among supported
      integer widths. Classification alone does not enable checked execution.
    parameters:
      source:
        type: astx.DataType
      target:
        type: astx.DataType
    returns:
      type: NumericConversion | None
    """
    kind = numeric_conversion_kind(source, target)
    if kind is None:
        return None
    implicit = kind in {
        NumericConversionKind.IDENTITY,
        NumericConversionKind.LOSSLESS,
    }
    check = not implicit
    if kind is NumericConversionKind.INTEGER_TO_FLOAT:
        bounds = integer_bounds(source)
        assert bounds is not None
        check = isinstance(target, astx.Float16) and (
            bounds[0] < -FLOAT16_MAX_FINITE_INTEGER
            or bounds[1] > FLOAT16_MAX_FINITE_INTEGER
        )
    return NumericConversion(source, target, kind, implicit, check)
