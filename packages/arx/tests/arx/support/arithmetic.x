```
title: Compiled test support arithmetic module
summary: Shared helper functions imported by compiled tests under packages/arx/tests/arx.
```

add2: fn(lhs: i32, rhs: i32) -> i32:
  ```
  title: add2
  summary: Returns the sum of two integer values for import coverage.
  ```
  return lhs + rhs

scale: fn(value: i32, factor: i32) -> i32:
  ```
  title: scale
  summary: Multiplies one integer value by one factor.
  ```
  return value * factor
