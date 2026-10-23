```
title: Bundled stdlib math module
summary: >-
  Pure-Arx helpers for signed i8, i16, i32, and i64 scalars. Inferred calls
  require the same concrete argument type and preserve it in the result.
  Explicit specialization uses ordinary argument conversions. Unsigned,
  floating, Boolean, and nullable specializations are not supported.
```

type SignedInteger = i8 | i16 | i32 | i64

@<T: SignedInteger>
fn abs(value: T) -> T:
  ```
  title: abs
  summary: >-
    Returns the absolute value as T. The minimum of T fails an assertion
    because its positive magnitude is not representable, unlike Python's
    arbitrary-precision integer result.
  ```
  var zero: T = cast(0, T)
  if value < zero:
    var magnitude: T = zero - value
    # Only the minimum remains negative after wrapping fixed-width negation.
    assert magnitude > zero, "abs() result is out of range for the input type"
    return magnitude
  else:
    return value

@<T: SignedInteger>
fn min(lhs: T, rhs: T) -> T:
  ```
  title: min
  summary: Returns the smaller of two signed integers as T.
  ```
  if lhs < rhs:
    return lhs
  else:
    return rhs

@<T: SignedInteger>
fn max(lhs: T, rhs: T) -> T:
  ```
  title: max
  summary: Returns the larger of two signed integers as T.
  ```
  if lhs > rhs:
    return lhs
  else:
    return rhs

@<T: SignedInteger>
fn clamp(value: T, lower: T, upper: T) -> T:
  ```
  title: clamp
  summary: >-
    Returns T restricted to the inclusive lower and upper bounds. Equal
    bounds are valid and return that bound. Reversed bounds fail an assertion
    regardless of the input value.
  ```
  assert lower <= upper, "clamp() lower bound must not exceed upper bound"
  if value < lower:
    return lower
  else:
    if value > upper:
      return upper
    else:
      return value

@<T: SignedInteger>
fn square(value: T) -> T:
  ```
  title: square
  summary: >-
    Returns T with its square modulo 2^N, where N is the bit width of T.
    Overflow wraps like ordinary scalar multiplication; it does not trap or
    widen the result.
  ```
  return value * value
