```
title: Repository generator builtin tests
summary: Cover the ambient range builtin list output.
```

test_range_returns_zero_based_values: fn() -> none:
  ```
  title: test_range_returns_zero_based_values
  summary: Verifies that range(start, stop) returns zero-based values.
  ```
  values: list[i32] = range(0, 4)
  first: i32 = values[0]
  second: i32 = values[1]
  third: i32 = values[2]
  fourth: i32 = values[3]
  assert first == 0, "range(0, 4)[0] should be 0"
  assert second == 1, "range(0, 4)[1] should be 1"
  assert third == 2, "range(0, 4)[2] should be 2"
  assert fourth == 3, "range(0, 4)[3] should be 3"

test_range_supports_inline_indexing: fn() -> none:
  ```
  title: test_range_supports_inline_indexing
  summary: Verifies that range results can be indexed inline.
  ```
  value: i32 = range(0, 3)[2]
  assert value == 2, "range(0, 3)[2] should be 2"

test_range_supports_custom_step: fn() -> none:
  ```
  title: test_range_supports_custom_step
  summary: Verifies that range(start, stop, step) honors custom steps.
  ```
  values: list[i32] = range(2, 8, 2)
  first: i32 = values[0]
  second: i32 = values[1]
  third: i32 = values[2]
  assert first == 2, "range(2, 8, 2)[0] should be 2"
  assert second == 4, "range(2, 8, 2)[1] should be 4"
  assert third == 6, "range(2, 8, 2)[2] should be 6"

test_range_supports_descending_step: fn() -> none:
  ```
  title: test_range_supports_descending_step
  summary: Verifies that range(start, stop, step) supports negative steps.
  ```
  values: list[i32] = range(5, 0, 0 - 1)
  first: i32 = values[0]
  second: i32 = values[1]
  third: i32 = values[2]
  fourth: i32 = values[3]
  fifth: i32 = values[4]
  assert first == 5, "range(5, 0, -1)[0] should be 5"
  assert second == 4, "range(5, 0, -1)[1] should be 4"
  assert third == 3, "range(5, 0, -1)[2] should be 3"
  assert fourth == 2, "range(5, 0, -1)[3] should be 2"
  assert fifth == 1, "range(5, 0, -1)[4] should be 1"

test_range_empty_intervals: fn() -> none:
  ```
  title: test_range_empty_intervals
  summary: Equal endpoints and wrong-direction steps produce empty lists.
  ```
  count: i32 = 0
  for value in range(7, 7):
    count = count + 1
  for value in range(7, 7, 0 - 1):
    count = count + 1
  for value in range(3, 0):
    count = count + 1
  for value in range(0, 3, 0 - 1):
    count = count + 1
  assert count == 0
