```
title: Repository stdlib math tests
summary: Validate bundled stdlib math helpers with the compiled test runner.
```

import math from stdlib

fn test_abs() -> none:
  ```
  title: test_abs
  summary: Verifies zero and representable positive and negative magnitudes.
  ```
  assert math.abs(0 - 4) == 4
  assert math.abs(7) == 7
  assert math.abs(0) == 0
  assert math.abs(0 - 1) == 1
  assert math.abs(2147483647) == 2147483647
  assert math.abs(0 - 2147483647) == 2147483647

fn test_min_and_max() -> none:
  ```
  title: test_min_and_max
  summary: Verifies bundled minimum and maximum helpers.
  ```
  assert math.min(3, 9) == 3
  assert math.max(3, 9) == 9

fn test_clamp() -> none:
  ```
  title: test_clamp
  summary: Verifies lower, in-range, and upper clamp behavior.
  ```
  assert math.clamp(0 - 3, 0, 2) == 0
  assert math.clamp(1, 0, 2) == 1
  assert math.clamp(9, 0, 2) == 2
  assert math.clamp(0, 0, 2) == 0
  assert math.clamp(2, 0, 2) == 2

fn test_clamp_integer_limits_and_equal_bounds() -> none:
  ```
  title: test_clamp_integer_limits_and_equal_bounds
  summary: Allows the full i32 interval and single-value inclusive intervals.
  ```
  var minimum: i32 = (0 - 2147483647) - 1
  var maximum: i32 = 2147483647
  assert math.clamp(minimum, minimum, maximum) == minimum
  assert math.clamp(maximum, minimum, maximum) == maximum
  assert math.clamp(0, minimum, maximum) == 0
  assert math.clamp(minimum, maximum, maximum) == maximum
  assert math.clamp(maximum, minimum, minimum) == minimum
  assert math.clamp(3, 3, 3) == 3

fn test_square() -> none:
  ```
  title: test_square
  summary: Verifies representable squares including zero and negative inputs.
  ```
  assert math.square(5) == 25
  assert math.square(0 - 5) == 25
  assert math.square(0) == 0
  assert math.square(1) == 1
  assert math.square(0 - 1) == 1
  assert math.square(46340) == 2147395600

fn test_explicit_wrapping_multiplication() -> none:
  ```
  title: test_explicit_wrapping_multiplication
  summary: Modulo arithmetic requires explicit wrapping, while square is checked.
  ```
  assert wrapping_mul(46341, 46341) == 0 - 2147479015
  assert wrapping_mul(65536, 65536) == 0
  assert wrapping_mul(0 - 65536, 0 - 65536) == 0
  assert wrapping_mul(2147483647, 2147483647) == 1
  assert wrapping_mul((0 - 2147483647) - 1, (0 - 2147483647) - 1) == 0

fn test_template_calls() -> none:
  ```
  title: test_template_calls
  summary: Preserve inferred narrow types or explicitly select a wider type.
  ```
  var narrow: i8 = cast(0 - 12, i8)
  assert isinstance(math.abs(narrow), i8)
  assert math.abs(narrow) == 12
  assert wrapping_mul(narrow, narrow) == 0 - 112
  assert math.square(cast(narrow, i64)) == 144
  assert math.square<int64>(narrow) == 144
  assert isinstance(math.min<i64>(narrow, 0), i64)
  assert math.min<i64>(narrow, 0) == 0 - 12
  assert math.max<int32>(lhs=narrow, rhs=3) == 3
  assert math.clamp<i64>(upper=9, value=narrow, lower=0) == 0
  assert math.abs<int16>(value=narrow) == 12
