```
title: Primitive nullable values
summary: Use explicit validity with native scalar storage and no Arrow import.
```

type MaybeCount = i32 | none

fn optional_count(value: MaybeCount = none) -> i64 | none:
  ```
  title: Widen valid counts while preserving missing values.
  ```
  return value

fn missing_count() -> MaybeCount:
  ```
  title: Return an explicitly missing count.
  ```
  return none

fn choose_count(present: bool) -> i32 | none:
  ```
  title: Return valid and null values on separate control-flow paths.
  ```
  if present:
    return 42
  return none

fn widen_real(value: f32 | none) -> f64 | none:
  ```
  title: Widen floating payloads without inspecting missing values.
  ```
  return value

fn main() -> i32:
  ```
  title: Copy and update nullable values without sentinel payloads.
  ```
  var count: MaybeCount = none
  assert is_null(count)
  count = 0
  assert is_valid(count)
  assert expect_valid(count) == 0
  var widened: i64 | none = optional_count(count)
  assert expect_valid(widened) == 0
  count = -1
  assert expect_valid(optional_count(count)) == -1
  count = none
  widened = optional_count(count)
  assert is_null(widened)
  assert is_null(optional_count())
  assert is_null(missing_count())
  var real: f32 | none = 1.5
  assert expect_valid(widen_real(real)) == 1.5
  real = -0.5
  assert expect_valid(widen_real(real)) == -0.5
  count = +1
  assert expect_valid(count) == 1
  real = none
  assert is_null(widen_real(real))
  var enabled: bool | none = false
  assert is_valid(enabled)
  assert !expect_valid(enabled)
  assert expect_valid(choose_count(true)) == 42
  assert is_null(choose_count(false))
  var index: i32 = 0
  while index < 3:
    count = index
    assert expect_valid(optional_count(count)) == index
    count = none
    assert is_null(optional_count(count))
    index = index + 1
  return 0
