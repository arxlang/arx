```
title: Logical scalar and tabular builtins
```
fn test_logical_values() -> none:
  ```
  title: Preserve logical children and explicit row order.
  ```
  var source: tensor[i32, 2] = [2, 4]
  var copied: array[i32] = array_from_buffer(source)
  assert expect_valid(array_at(copied, 1)) == 4
  var texts: array[string | none] = array[string | none]("λ", none, "")
  var batch: record_batch[text:string | none] = record_batch[text:string | none](3, texts)
  var selected: record_batch[text:string | none] = take_rows(batch, array[i64](2, 0, 1))
  assert scalar_text(expect_valid(array_at(column(selected, "text"), 0))) == ""
  assert scalar_text(expect_valid(array_at(column(selected, "text"), 1))) == "λ"
  assert is_null(array_at(column(selected, "text"), 2))
  var binary_value: scalar[binary] = scalar[binary](array[u8](cast(0, u8), cast(255, u8)))
  assert expect_valid(array_at(scalar_bytes(binary_value), 1)) == 255
  var nested: scalar[list[item:i32]] = scalar[list[item:i32]](copied)
  assert array_equal(scalar_values(nested), copied)
