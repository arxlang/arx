```
title: Primitive nullable scalar integration
```

fn nullable_count(value: i32 | none = none) -> i64 | none:
  ```
  title: Preserve validity through an argument, default, and widening return.
  ```
  return value

fn test_nullable_scalars() -> none:
  ```
  title: Distinguish valid zero and false from missing values.
  ```
  var count: i32 | none = none
  assert is_null(count)
  count = 0
  assert is_valid(count)
  assert expect_valid(nullable_count(count)) == 0
  count = none
  assert is_null(nullable_count(count))
  assert is_null(nullable_count())
  var enabled: bool | none = false
  assert is_valid(enabled)
  assert !expect_valid(enabled)
