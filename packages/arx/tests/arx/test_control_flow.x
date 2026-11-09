```
title: Repository control-flow tests
summary: Cover branches, loop transfers, cleanup, and finalizer replacement.
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

fn test_loop_transfers() -> none:
  ```
  title: Stop searches and skip work in each source loop form.
  ```
  current: i32 = 0
  total: i32 = 0
  while current < 5:
    current += 1
    if current == 1:
      continue
    if current == 4:
      break
    total += current
  assert current == 4
  assert total == 5

  updates: i32 = 0
  visits: i32 = 0
  total = 0
  for i: i32 = 0; i < 8; i += ++updates:
    visits += 1
    assert visits < 10
    if i == 1:
      continue
    if i == 6:
      break
    total += i
  assert updates == 3
  assert visits == 4
  assert total == 3

  total = 0
  for outer: i32 = 0; outer < 3; outer += 1:
    for inner in [1, 2, 3]:
      if inner == 1:
        continue
      if inner == 3:
        break
      total += inner + outer
  assert total == 9

fn replaced_list_return() -> list[i32]:
  ```
  title: A finalizer break discards and releases a pending owned return.
  ```
  for value in [1]:
    try:
      return [value, 2]
    finally:
      break
  return [9]

fn return_after_break() -> i32:
  ```
  title: An explicit finalizer return replaces a pending loop exit.
  ```
  while true:
    try:
      break
    finally:
      return 11
  return 0

fn test_loop_transfer_finalizers() -> none:
  ```
  title: Loop exits preserve or replace pending completion as specified.
  ```
  count: i32 = 0
  finalized: i32 = 0
  while count < 3:
    count += 1
    try:
      break
    finally:
      finalized += 1
      if count < 3:
        continue
  assert count == 3
  assert finalized == 3

  count = 0
  try:
    for value in [1, 2]:
      try:
        continue
      finally:
        count += 1
        raise ValueError("replace continue")
  except ValueError:
    assert count == 1
  assert count == 1

  handled: i32 = 0
  escaped: i32 = 0
  for value in [1, 2, 3]:
    try:
      raise ValueError("handled")
    except ValueError as error:
      assert error.message == "handled"
      handled += 1
      if value < 3:
        continue
      break
    escaped += 1
  assert handled == 3
  assert escaped == 0

  returned: list[i32] = replaced_list_return()
  assert len(returned) == 1
  assert returned[0] == 9
  assert return_after_break() == 11

fn loop_transfer_owners() -> none:
  ```
  title: Audit iteration owners in the caller's isolated working directory.
  ```
  values: list[i32] = [1, 2, 3]
  for value in values:
    words: list[str] = ["owned", "text"]
    stream: File = open("loop-resource.txt", "w")
    alias: File = stream
    alias.write(words[0])
    if value == 1:
      continue
    break
  values = [4]
  values.append(5)
  assert len(values) == 2
  assert values[0] == 4
  assert values[1] == 5
