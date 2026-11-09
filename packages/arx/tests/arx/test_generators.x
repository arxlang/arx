```
title: Repository generator builtin tests
summary: Cover the ambient range builtin list output.
```

fn test_range_returns_zero_based_values() -> none:
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

fn test_range_supports_inline_indexing() -> none:
  ```
  title: test_range_supports_inline_indexing
  summary: Verifies that range results can be indexed inline.
  ```
  value: i32 = range(0, 3)[2]
  assert value == 2, "range(0, 3)[2] should be 2"

fn test_range_supports_custom_step() -> none:
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

fn test_range_supports_descending_step() -> none:
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

fn test_range_empty_intervals() -> none:
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

fn test_range_at_i32_boundary() -> none:
  ```
  title: test_range_at_i32_boundary
  summary: Ranges up to both i32 endpoints without wrapping.
  ```
  upper: list[i32] = range(2147483645, 2147483647)
  lower: list[i32] = range(-2147483646, -2147483648, 0 - 1)
  assert upper[0] == 2147483645
  assert upper[1] == 2147483646
  assert lower[0] == -2147483646
  assert lower[1] == -2147483647

fn test_range_supports_i64_values() -> none:
  ```
  title: test_range_supports_i64_values
  summary: Ranges over values larger than the i32 limits.
  ```
  start: i64 = 5000000000
  stop: i64 = 5000000004
  step: i64 = 2
  values: list[i64] = range(start, stop, step)
  assert values[0] == 5000000000
  assert values[1] == 5000000002

fn test_range_at_i64_boundaries() -> none:
  ```
  title: test_range_at_i64_boundaries
  summary: Ranges up to both i64 endpoints without overflow.
  ```
  max: i64 = 9223372036854775807
  min: i64 = -9223372036854775808
  upper: list[i64] = range(max - 2, max)
  lower: list[i64] = range(min + 2, min, 0 - cast(1, i64))
  assert upper[0] == max - 2
  assert upper[1] == max - 1
  assert lower[0] == min + 2
  assert lower[1] == min + 1
