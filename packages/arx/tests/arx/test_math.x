```
title: Repository stdlib math tests
summary: Validate bundled stdlib math helpers with the compiled test runner.
```

import math from stdlib

fn test_abs() -> none:
  ```
  title: test_abs
  summary: Verifies absolute-value behavior for negative and positive inputs.
  ```
  assert math.abs(0 - 4) == 4
  assert math.abs(7) == 7

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

fn test_square() -> none:
  ```
  title: test_square
  summary: Verifies squaring behavior for one integer input.
  ```
  assert math.square(5) == 25
