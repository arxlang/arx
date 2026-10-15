```
title: Reusable builders, chunked arrays and nullable owners
```
fn make_values() -> chunked_array[i32 | none]:
  ```
  title: Build two independent chunks and return their shared storage.
  ```
  var b: array_builder[i32 | none] = array_builder[i32 | none]()
  builder_reserve(b, 4)
  var index: i32 = 0
  while index < 3:
    builder_append(b, index)
    index = index + 1
  builder_append(b, none)
  var first: array[i32 | none] = builder_finish(b)
  assert builder_length(b) == 0
  builder_append(b, 4)
  var second: array[i32 | none] = builder_finish(b)
  return chunked_array[i32 | none](first, second)

fn test_columnar_builders() -> none:
  ```
  title: Choose chunk iteration explicitly and keep null separate from empty.
  ```
  var values: chunked_array[i32 | none] = make_values()
  assert chunk_count(values) == 2
  assert array_length(values) == 5
  assert is_null(array_at(values, 3))
  assert expect_valid(array_at(values, 4)) == 4
  var index: i32 = 0
  var length: i64 = 0
  while index < chunk_count(values):
    length = length + array_length(chunk_at(values, index))
    index = index + 1
  assert length == 5
  var combined: array[i32 | none] | none = combine_chunks(values)
  var kept: array[i32 | none] | none = combined
  combined = none
  assert is_null(combined)
  if is_valid(kept):
    assert array_length(kept) == 5
  var half: array[f16] = array[f16](cast(1.5, f16))
  assert expect_valid(array_at(half, 0)) == cast(1.5, f16)
