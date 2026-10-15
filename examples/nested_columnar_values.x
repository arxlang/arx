```
title: nested columnar values
```
type Row = scalar[struct[name:string, items:list[item:i32 | none], missing:i32 | none]]
fn make() -> Row:
  var values: array[i32 | none] = array[i32 | none](3, none, 7)
  return scalar[struct[name:string, items:list[item:i32 | none], missing:i32 | none]](scalar[string]("row"), scalar[list[item:i32 | none]](values), none)
fn main() -> i32:
  var row: Row = make()
  assert scalar_text(expect_valid(scalar_field(row, "name"))) == "row"
  assert is_null(scalar_field(row, "missing"))
  var items: array[i32 | none] = scalar_values(expect_valid(scalar_field(row, "items")))
  assert expect_valid(array_at(items, 2)) == 7
  assert is_null(array_at(items, 1))
  var rows: array[struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none] = array[struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none](row, none)
  var batch: record_batch[rows:struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none] = record_batch[rows:struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none](2, rows)
  var table_value: table[rows:struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none] = to_table(batch)
  var selected: array[struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none] = column(to_record_batch(slice_rows(table_value, 0, 1)), "rows")
  assert scalar_equal(expect_valid(array_at(selected, 0)), row)
  var order: array[i64] = array[i64](1, 0, 0)
  var reordered: table = runtime_schema(take_rows(table_value, order))
  assert num_rows(reordered) == 3
  var reordered_batch: record_batch = to_record_batch(reordered)
  var reordered_column: array[struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none] = column_as(reordered_batch, 0, field[rows:struct[name:string, items:list[item:i32 | none], missing:i32 | none] | none])
  assert is_null(array_at(reordered_column, 0))
  assert scalar_equal(expect_valid(array_at(reordered_column, 2)), row)
  assert num_rows(take_rows(record_batch[](5), array[i64](4, 1))) == 2
  assert num_rows(take_rows(table[](5), array[i64]())) == 0
  assert num_rows(take_rows(batch, array[i64](1, 0))) == 2
  return 0
