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
    Returns the absolute value as T. The minimum of T fails checked arithmetic
    because its positive magnitude is not representable, unlike Python's
    arbitrary-precision integer result.
  ```
  var zero: T = cast(0, T)
  if value < zero:
    return zero - value
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
    Returns the square as T. Unrepresentable products fail checked arithmetic
    in every build. Choose a wider specialization before the multiplication
    when needed; the destination type does not widen an already typed result.
  ```
  return value * value
