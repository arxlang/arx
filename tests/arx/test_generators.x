```
title: Repository generator builtin tests
summary: Cover the ambient range builtin list output.
```

import range from builtins.generators

fn test_range_returns_zero_based_values() -> none:
  ```
  title: test_range_returns_zero_based_values
  summary: Verifies that range(stop) returns zero-based values up to stop.
  ```
  var values: list[i32] = range(4)
  assert_value(values[0], 0)
  assert_value(values[1], 1)
  assert_value(values[2], 2)
  assert_value(values[3], 3)

fn test_range_supports_inline_indexing() -> none:
  ```
  title: test_range_supports_inline_indexing
  summary: Verifies that range results can be indexed inline.
  ```
  assert_value(range(3)[2], 2)

fn assert_value(value: i32, expected: i32) -> none:
  ```
  title: assert_value
  summary: Asserts that one integer matches the expected value.
  ```
  assert value == expected
