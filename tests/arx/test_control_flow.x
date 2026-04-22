```
title: Repository control-flow tests
summary: Cover if branches, while loops, range loops, and count loops.
```

fn classify(value: i32) -> i32:
  ```
  title: classify
  summary: Classifies one integer as negative, zero, or positive.
  ```
  if value < 0:
    return 0 - 1
  else:
    if value == 0:
      return 0
    else:
      return 1

fn while_never_runs() -> i32:
  ```
  title: while_never_runs
  summary: Uses one while loop whose body never executes.
  ```
  while false:
    return 1
  return 0

fn first_range_value(limit: i32) -> i32:
  ```
  title: first_range_value
  summary: Returns the first value produced by one range loop.
  ```
  for i in (0:limit:1):
    return i
  return limit

fn skipped_count_loop() -> i32:
  ```
  title: skipped_count_loop
  summary: Uses one count loop whose body is skipped entirely.
  ```
  for var i: i32 = 3; i < 3; i + 1:
    return 1
  return 0

fn test_if_else_paths() -> none:
  ```
  title: test_if_else_paths
  summary: Covers negative, zero, and positive if-else paths.
  ```
  assert classify(0 - 2) == (0 - 1)
  assert classify(0) == 0
  assert classify(2) == 1

fn test_while_zero_iteration() -> none:
  ```
  title: test_while_zero_iteration
  summary: Verifies the while helper returns the fallthrough value.
  ```
  assert while_never_runs() == 0

fn test_for_range_loop_asserts() -> none:
  ```
  title: test_for_range_loop_asserts
  summary: Executes one range loop and validates each yielded index.
  ```
  for i in (0:4:1):
    assert i < 4
  assert first_range_value(4) == 0

fn test_for_count_loop_asserts() -> none:
  ```
  title: test_for_count_loop_asserts
  summary: Executes one count loop and one skipped count loop.
  ```
  for var i: i32 = 0; i < 3; i + 1:
    assert i < 3
  assert skipped_count_loop() == 0
