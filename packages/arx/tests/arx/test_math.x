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

fn test_square_wraps_i32() -> none:
  ```
  title: test_square_wraps_i32
  summary: Preserves ordinary modulo multiplication instead of checked overflow.
  ```
  assert math.square(46341) == 0 - 2147479015
  assert math.square(65536) == 0
  assert math.square(0 - 65536) == 0
  assert math.square(2147483647) == 1
  assert math.square((0 - 2147483647) - 1) == 0
