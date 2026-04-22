```
title: Bundled stdlib math module
summary: Pure-Arx integer helpers shipped with the compiler package.
```

fn abs(value: i32) -> i32:
  ```
  title: abs
  summary: Returns the absolute value of one signed integer.
  ```
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
  summary: Restricts one signed integer to the inclusive lower and upper bound.
  ```
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
  summary: Returns the square of one signed integer value.
  ```
  return value * value
