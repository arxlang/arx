```
title: Example compiled test module
summary: Demonstrates Arx assertions and the `arx test` runner.
```
add: fn(a: i32, b: i32) -> i32:
  ```
  title: add
  summary: Returns the sum of two integer values.
  ```
  return a + b

test_add: fn() -> none:
  ```
  title: test_add
  summary: Verifies the helper function using compiled assertions.
  ```
  assert add(1, 2) == 3
  assert add(2, 2) == 4, "add(2, 2) should be 4"
  return none
