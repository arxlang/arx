```
title: Bundled stdlib math module
summary: Pure-Arx integer helpers shipped with the compiler package.
```

fn abs(value: i32) -> i32:
  ```
  title: abs
  summary: >-
    Returns the absolute value as i32. The i32 minimum fails an assertion
    because its positive magnitude is not representable, unlike Python's
    arbitrary-precision integer result.
  ```
  assert value != (0 - 2147483647) - 1, "abs() result is out of range for i32"
  if value < 0:
    return 0 - value
  else:
    return value

fn min(lhs: i32, rhs: i32) -> i32:
  ```
  title: min
  summary: Returns the smaller of two signed integers.
  ```
  if lhs < rhs:
    return lhs
  else:
    return rhs

fn max(lhs: i32, rhs: i32) -> i32:
  ```
  title: max
  summary: Returns the larger of two signed integers.
  ```
  if lhs > rhs:
    return lhs
  else:
    return rhs

fn clamp(value: i32, lower: i32, upper: i32) -> i32:
  ```
  title: clamp
  summary: >-
    Restricts one i32 value to the inclusive lower and upper bounds. Equal
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

fn square(value: i32) -> i32:
  ```
  title: square
  summary: >-
    Returns the square modulo 2^32, interpreted as signed i32. Overflow wraps
    like ordinary scalar multiplication; it does not trap or widen the result.
  ```
  return value * value
