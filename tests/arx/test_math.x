```
title: Repository stdlib math tests
summary: Validate bundled stdlib math helpers with the compiled test runner.
```

import math from stdlib

fn test_abs() -> none:
  assert math.abs(0 - 4) == 4
  assert math.abs(7) == 7
  return none

fn test_min_and_max() -> none:
  assert math.min(3, 9) == 3
  assert math.max(3, 9) == 9
  return none

fn test_clamp() -> none:
  assert math.clamp(0 - 3, 0, 2) == 0
  assert math.clamp(1, 0, 2) == 1
  assert math.clamp(9, 0, 2) == 2
  return none

fn test_square() -> none:
  assert math.square(5) == 25
  return none
