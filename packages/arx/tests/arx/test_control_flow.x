```
title: Repository control-flow tests
summary: Cover if/elif chains, while loops, for-in loops, and count loops.
```

fn classify(value: i32) -> i32:
  ```
  title: classify
  summary: Classifies one integer as negative, zero, or positive.
  ```
  if value < 0:
    return 0 - 1
  elif value == 0:
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
  for i in range(0, limit):
    return i
  return limit

fn make_values() -> list[i32]:
  ```
  title: make_values
  summary: Builds one list for function-call iterable coverage.
  ```
  return range(0, 4)

fn skipped_count_loop() -> i32:
  ```
  title: skipped_count_loop
  summary: Uses one count loop whose body is skipped entirely.
  ```
  for i: i32 = 3; i < 3; i + 1:
    return 1
  return 0

fn test_if_elif_else_paths() -> none:
  ```
  title: test_if_elif_else_paths
  summary: Covers every branch and ordered condition effects with early stopping.
  ```
  assert classify(0 - 2) == (0 - 1)
  assert classify(0) == 0
  assert classify(2) == 1

  for stop in [1, 2, 3, 4]:
    checks: i32 = 0
    branch: i32 = 0
    if ++checks == stop:
      branch = 1
    elif ++checks == stop:
      branch = 2
    elif ++checks == stop:
      branch = 3
    if stop == 4:
      assert checks == 3
      assert branch == 0
    else:
      assert checks == stop
      assert branch == stop

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
  for i in range(0, 4):
    assert i < 4, "range loop values should stay below the stop bound"
  assert first_range_value(4) == 0

fn test_for_in_list_asserts() -> none:
  ```
  title: test_for_in_list_asserts
  summary: Executes for-in loops over one list variable and one list literal.
  ```
  values: list[i32] = range(0, 4)
  total_from_var: i32 = 0
  for value in values:
    total_from_var = total_from_var + value
  assert total_from_var == 6, "for-in over a list variable should sum to 6"

  total_from_literal: i32 = 0
  for value in [1, 2, 3]:
    total_from_literal = total_from_literal + value
  assert total_from_literal == 6, "for-in over a list literal should sum to 6"

  total_from_call: i32 = 0
  for value in make_values():
    total_from_call = total_from_call + value
  assert total_from_call == 6, "for-in over a function call should sum to 6"

fn test_for_count_loop_asserts() -> none:
  ```
  title: test_for_count_loop_asserts
  summary: Executes one count loop and one skipped count loop.
  ```
  for i: i32 = 0; i < 3; i + 1:
    assert i < 3, "count loop values should stay below the exit condition"
  assert skipped_count_loop() == 0

  i: i32 = 42
  total: i32 = 0
  for i: i32 = 0; i < 4; i += 1:
    total += i * 2
    for i: i32 = 100; i < 101; i += 1:
      assert i == 100
  assert total == 12
  assert i == 42

fn test_prefix_mutation_values() -> none:
  ```
  title: test_prefix_mutation_values
  summary: Prefix mutation stores and returns the updated value, including loop updates.
  ```
  value: i32 = 3
  increased: i32 = ++value
  assert value == 4
  assert increased == 4
  decreased: i32 = --value
  assert value == 3
  assert decreased == 3

  total: i32 = 0
  for i: i32 = 0; i < 3; ++i:
    total = total + i
  assert total == 3
