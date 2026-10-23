```
title: Checked Series slicing, reductions and updates
summary: Preserve nullable values and independent column snapshots.
```
fn main() -> i32:
  var frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3]})
  var column: series[i32 | none] = frame.x
  var reversed: series[i32 | none] = column[::-1]
  assert fill_null(reversed[0], 0) == 3
  assert is_null(reversed[1])
  assert fill_null(series_sum(column), cast(0, i64)) == 4
  var wider: series[i64 | none] = column + cast(2, i64)
  assert fill_null(wider[0], cast(0, i64)) == 3
  column[1] = 9
  assert fill_null(column[1], 0) == 9
  assert is_null(frame.x[1])
  column[0] = none
  assert series_count(column) == 2
  return 0
