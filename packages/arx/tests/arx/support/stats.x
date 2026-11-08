```
title: Compiled test support stats module
summary: Shared import helpers that also exercise relative imports.
```

import (add2, scale as multiply) from .arithmetic

fn sum3(first: i32, second: i32, third: i32) -> i32:
  ```
  title: sum3
  summary: Returns the sum of three integer values.
  ```
  return add2(add2(first, second), third)

fn doubled(value: i32) -> i32:
  ```
  title: doubled
  summary: Returns one integer value multiplied by two.
  ```
  return multiply(value, 2)
