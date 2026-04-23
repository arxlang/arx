```
title: Repository generator builtin tests
summary: Cover the ambient range builtin list output.
```

fn test_range_returns_zero_based_values() -> none:
  ```
  title: test_range_returns_zero_based_values
  summary: Verifies that range(start, stop) returns zero-based values.
  ```
  var values: list[i32] = range(0, 4)
  var first: i32 = values[0]
  var second: i32 = values[1]
  var third: i32 = values[2]
  var fourth: i32 = values[3]
  assert first == 0, "range(0, 4)[0] should be 0"
  assert second == 1, "range(0, 4)[1] should be 1"
  assert third == 2, "range(0, 4)[2] should be 2"
  assert fourth == 3, "range(0, 4)[3] should be 3"

fn test_range_supports_inline_indexing() -> none:
  ```
  title: test_range_supports_inline_indexing
  summary: Verifies that range results can be indexed inline.
  ```
  var value: i32 = range(0, 3)[2]
  assert value == 2, "range(0, 3)[2] should be 2"

fn test_range_supports_custom_step() -> none:
  ```
  title: test_range_supports_custom_step
  summary: Verifies that range(start, stop, step) honors custom steps.
  ```
  var values: list[i32] = range(2, 8, 2)
  var first: i32 = values[0]
  var second: i32 = values[1]
  var third: i32 = values[2]
  assert first == 2, "range(2, 8, 2)[0] should be 2"
  assert second == 4, "range(2, 8, 2)[1] should be 4"
  assert third == 6, "range(2, 8, 2)[2] should be 6"
