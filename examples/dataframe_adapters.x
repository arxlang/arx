```
title: Explicit legacy adapters and logical DataFrame columns
```
class OptionalColumns:
  ```
  title: Retained nullable legacy columnar owners
  ```
  @[public, mutable]
  rows: dataframe[...] | none
  @[public, mutable]
  values: series[i32 | none] | none

fn restore(value: dataframe[...]) -> table:
  return to_table(value)

fn optional_rows(value: dataframe[...] | none = none) -> dataframe[...] | none:
  return value

fn optional_series(value: series[i32 | none] | none = none) -> series[i32 | none] | none:
  return value

fn main() -> i32:
  var rows: dataframe[name: str, count: i32 | none, nested: scalar[list[item:i32 | none]]] = dataframe({name: ["Ada", "λ"], count: [1, none], nested: [scalar[list[item:i32 | none]](array[i32 | none](1, none)), scalar[list[item:i32 | none]](array[i32 | none]())]})
  var names: chunked_array[string] = to_chunked(rows.name)
  assert scalar_text(expect_valid(array_at(names, 1))) == "λ"
  var counts: chunked_array[i32 | none] = to_chunked(rows.count)
  assert is_null(array_at(counts, 1))
  var nested: chunked_array[list[item:i32 | none]] = to_chunked(rows.nested)
  assert array_length(scalar_values(expect_valid(array_at(nested, 0)))) == 2
  var series_value: series[scalar[string]] = to_series(names)
  assert array_equal(to_chunked(series_value), names)
  var again: table = restore(to_dataframe(to_table(rows)))
  var checked: chunked_array[string] = column_as(again, 0, field[name:string])
  assert array_equal(checked, names)
  assert num_rows(again) == 2
  var box: OptionalColumns = OptionalColumns()
  assert is_null(box.rows)
  assert is_null(box.values)
  assert is_null(optional_rows())
  assert is_null(optional_series())
  var empty: dataframe[...] | none = to_dataframe(table[](0))
  assert is_valid(empty)
  assert num_rows(to_table(expect_valid(empty))) == 0
  box.rows = optional_rows(to_dataframe(again))
  box.values = optional_series(to_series(counts))
  box.rows = box.rows
  box.values = box.values
  var kept: dataframe[...] | none = box.rows
  var kept_values: series[i32 | none] | none = box.values
  box.rows = none
  box.values = none
  assert num_rows(to_table(expect_valid(kept))) == 2
  assert is_null(array_at(to_chunked(expect_valid(kept_values)), 1))
  if is_valid(kept_values):
    assert array_length(to_chunked(kept_values)) == 2
  kept = none
  kept_values = none
  return 0
