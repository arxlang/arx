```
title: Columnar tables
```
fn identity(value: record_batch[a: i32 | none, b: bool]) -> record_batch[a: i32 | none, b: bool]:
  ```
  title: Identity.
  ```
  return value
fn table_identity(value: table[a: i32 | none, b: bool]) -> table[a: i32 | none, b: bool]:
  ```
  title: Table identity.
  ```
  return value
fn main() -> i32:
  ```
  title: Main.
  ```
  var batch: record_batch[a: i32 | none, b: bool] = record_batch[a: i32 | none, b: bool](3, array[i32 | none](1, none, 3), array[bool](true, false, true))
  var copied: record_batch[a: i32 | none, b: bool] = identity(batch)
  var parent: table[a: i32 | none, b: bool] = table_identity(to_table(copied))
  assert num_rows(parent) == 3
  assert num_columns(parent) == 2
  assert descriptor_equal(container_schema(parent), schema[a: i32 | none, b: bool])
  var extracted: chunked_array[i32 | none] = column(parent, "a")
  assert is_null(array_at(extracted, 1))
  var sliced: table[a: i32 | none, b: bool] = slice_rows(parent, 1, 2)
  assert num_rows(sliced) == 2
  assert is_null(array_at(column(sliced, "a"), 0))
  var selected: table[b: bool, a: i32 | none] = select_columns(parent, "b", "a")
  assert descriptor_equal(container_schema(selected), schema[b: bool, a: i32 | none])
  var renamed: table[c: bool, d: i32 | none] = rename_columns(selected, "c", "d")
  assert expect_valid(array_at(column(renamed, "c"), 0))
  var reduced: table[d: i32 | none] = remove_column(renamed, "c")
  var added: table[d: i32 | none, e: f64] = add_column(reduced, field[e: f64], chunked_array[f64](array[f64](1.0), array[f64](2.0, 3.0)))
  assert chunk_count(column(added, "e")) == 2
  var combined: table[d: i32 | none, e: f64] = table_combine_chunks(added)
  assert chunk_count(column(combined, "e")) == 1
  var replaced: table[d: i32 | none, e: i64] = replace_column(added, field[e: i64], chunked_array[i64](array[i64](4, 5, 6)))
  assert expect_valid(array_at(column(replaced, "e"), 2)) == 6
  var back: record_batch[d: i32 | none, e: i64] = to_record_batch(replaced)
  assert array_equal(column(back, "d"), array[i32 | none](1, none, 3))
  var runtime: table = runtime_schema(replaced)
  var checked: chunked_array[i64] = column_as(runtime, 1, field[e: i64])
  assert expect_valid(array_at(checked, 0)) == 4
  var runtime_batch: record_batch = runtime_schema(back)
  assert array_length(column_as(runtime_batch, 0, field[d: i32 | none])) == 3
  var no_columns: table[] = select_columns(parent)
  assert num_rows(no_columns) == 3
  assert num_columns(no_columns) == 0
  var empty: record_batch[] = record_batch[](5)
  assert num_rows(to_table(empty)) == 5
  assert num_rows(to_record_batch(to_table(empty))) == 5
  var empty_slice: record_batch[] = slice_rows(empty, 5, 0)
  assert num_rows(empty_slice) == 0
  return 0
