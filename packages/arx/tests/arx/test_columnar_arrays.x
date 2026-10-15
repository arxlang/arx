```
title: Native primitive arrays and nullable scalar access
```
fn make_values() -> array[i32 | none]:
  ```
  title: Return a slice that outlives its parent binding.
  ```
  var original: array[i32 | none] = array[i32 | none](9, 1, none, 3, 8)
  return array_slice(original, 1, 3)

fn borrow_copy(values: array[i32 | none]) -> array[i32 | none]:
  ```
  title: Return an independently retained owner of immutable storage.
  ```
  return values

fn test_columnar_arrays() -> none:
  ```
  title: Inspect and transform offset arrays without importing Arrow.
  ```
  var values: array[i32 | none] = make_values()
  assert array_length(values) == 3
  assert array_offset(values) == 1
  assert array_null_count(values) == 1
  assert expect_valid(array_at(values, 0)) == 1
  assert is_null(array_at(values, 1))
  assert expect_valid(array_at(values, 2)) == 3
  var alias: array[i32 | none] = borrow_copy(values)
  var copy: array[i32 | none] = array_copy(values)
  assert array_offset(copy) == 0
  assert array_equal(values, copy)
  var empty: array[i32 | none] = array[i32 | none]()
  assert array_equal(array_concat(empty, alias), values)
  var joined: array[i32 | none] = array_concat(values, copy)
  assert array_length(joined) == 6
  assert array_null_count(joined) == 2
  var index: i32 = 0
  var total: i32 = 0
  while index < array_length(joined):
    var item: i32 | none = array_at(joined, index)
    if is_valid(item):
      total = total + item
    index = index + 1
  assert total == 8
  var flags: array[bool | none] = array[bool | none](true, false, none, true)
  var bit_slice: array[bool | none] = array_slice(flags, 1, 3)
  assert !expect_valid(array_at(bit_slice, 0))
  assert is_null(array_at(bit_slice, 1))
  assert expect_valid(array_at(bit_slice, 2))
  var unsigned: array[u64] = array[u64](cast(-1, u64))
  assert expect_valid(array_at(unsigned, 0)) == cast(-1, u64)
  var reals: array[f32 | none] = array[f32 | none](1.5, none, -0.5)
  assert expect_valid(array_at(reals, 0)) == 1.5
  assert is_null(array_at(reals, 1))
  var computed: array[i32 | none] = array[i32 | none](array_at(values, 0) + 2)
  assert expect_valid(array_at(computed, 0)) == 3
