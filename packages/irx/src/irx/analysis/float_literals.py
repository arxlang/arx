"""
title: Single-rounding conversion of exact values to supported binary formats.
summary: >-
  Resolve decimal and integer literals with exact integer arithmetic before
  constructing a host float. No intermediate binary64 rounding, ambient Decimal
  precision, or LLVM behavior determines the selected target value.
"""

from __future__ import annotations

import math

from decimal import Decimal

import astx

from public import private

from irx.analysis.numeric_policy import FLOAT_PRECISIONS
from irx.typecheck import typechecked

# Inclusive normal binary exponents. Precision is shared with numeric policy.
FLOAT_EXPONENTS: dict[type[astx.DataType], tuple[int, int]] = {
    astx.Float16: (-14, 15),
    astx.Float32: (-126, 127),
    astx.Float64: (-1022, 1023),
}


@private
@typechecked
def rounded_float(
    value: int | float | Decimal, target: astx.DataType
) -> float:
    """
    title: Round once to the target binary format, nearest with ties to even.
    summary: >-
      Include subnormals, signed zero, and overflow to infinity. Callers decide
      whether a nonfinite result is legal. Existing floating NaN/infinity are
      preserved; finite decimals are never converted through binary64 first.
    parameters:
      value:
        type: int | float | Decimal
      target:
        type: astx.DataType
    returns:
      type: float
    raises:
      TypeError: If the target is not a supported floating format.
      ValueError: If a Decimal payload is nonfinite.
    """
    format_ = FLOAT_EXPONENTS.get(type(target))
    if format_ is None:
        raise TypeError("literal rounding requires f16, f32, or f64")
    if isinstance(value, float) and not math.isfinite(value):
        return value
    exact = (
        Decimal.from_float(value)
        if isinstance(value, float)
        else Decimal(value)
    )
    if not exact.is_finite():
        raise ValueError("exact floating literals must be finite")
    sign = -1.0 if exact.is_signed() else 1.0
    precision = FLOAT_PRECISIONS[type(target)]
    minimum, maximum = format_
    if exact.is_zero():
        return math.copysign(0.0, sign)

    # Conservative base-10 bounds avoid allocating huge ratios for compact
    # inputs such as 1e1000000000. Inside these bounds ratios stay manageable.
    if exact.adjusted() > maximum + 1:
        return math.copysign(math.inf, sign)
    if exact.adjusted() < minimum - precision:
        return math.copysign(0.0, sign)
    numerator, denominator = exact.copy_abs().as_integer_ratio()
    exponent = numerator.bit_length() - denominator.bit_length()
    below_power = (
        numerator < denominator << exponent
        if exponent >= 0
        else numerator << -exponent < denominator
    )
    if below_power:
        exponent -= 1

    # Subnormals all use the minimum format quantum. Normal values use p bits.
    quantum = max(exponent, minimum) - (precision - 1)
    if quantum >= 0:
        denominator <<= quantum
    else:
        numerator <<= -quantum
    significand, remainder = divmod(numerator, denominator)
    twice = remainder * 2
    if twice > denominator or (twice == denominator and significand % 2):
        significand += 1
    if significand and quantum + significand.bit_length() - 1 > maximum:
        return math.copysign(math.inf, sign)

    # The rounded significand has at most p bits (or is an exact power of 2).
    # Every finite supported target value is exactly representable in binary64.
    return math.copysign(math.ldexp(float(significand), quantum), sign)
