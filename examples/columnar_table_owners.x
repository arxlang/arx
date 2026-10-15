```
title: Columnar table owners
```
fn main() -> i32:
  ```
  title: Main.
  ```
  var batch: record_batch[a: i32]{origin: "test"} = record_batch[a: i32]{origin: "test"}(2, array[i32](1, 2))
  var renamed: record_batch[b: i32]{origin: "test"} = rename_columns(batch, "b")
  assert descriptor_equal(container_schema(renamed), schema[b: i32]{origin: "test"})
  var added: record_batch[b: i32, c: bool]{origin: "test"} = add_column(renamed, field[c: bool], array[bool](false, true))
  var replaced: record_batch[b: i64, c: bool]{origin: "test"} = replace_column(added, field[b: i64], array[i64](3, 4))
  var selected: record_batch[c: bool]{origin: "test"} = select_columns(replaced, "c")
  assert array_equal(column(selected, "c"), array[bool](false, true))
  var removed: record_batch[b: i64]{origin: "test"} = remove_column(replaced, "c")
  assert num_columns(removed) == 1
  var maybe: record_batch[b: i64]{origin: "test"} | none = removed
  var child: array[i64] = column(expect_valid(maybe), "b")
  maybe = none
  assert expect_valid(array_at(child, 1)) == 4
  var parent: table[z: f16] | none = table[z: f16](2, chunked_array[f16](array[f16](cast(1.5, f16), cast(2.5, f16))))
  var kept: table[z: f16] | none = parent
  parent = none
  assert num_rows(expect_valid(kept)) == 2
  assert expect_valid(array_at(column(expect_valid(kept), "z"), 1)) == 2.5
  kept = none
  return 0
