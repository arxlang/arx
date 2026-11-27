```
title: Nullable scalar and Series tests
summary: Validate null-preserving indexing and owned column kernels.
```

fn nullable_values() -> series[i32 | none]:
  ```
  title: Return an independently owned column
  ```
  frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3]})
  return frame.x

fn test_nullable_series() -> none:
  ```
  title: Nullable kernels, promotion and checked errors
  ```
  values: series[i32 | none] = nullable_values()
  total: series[i32 | none] = values + values
  missing: nullable[i32] = total[1]
  assert is_null(missing)
  assert fill_null(total[2], 0) == 6
  filled: series[i32] = fill_null(total, 7)
  assert filled[1] == 7
  mask: series[bool] = is_null(total)
  assert mask[1]
  assert !mask[0]
  inverted: series[bool] = not mask
  assert inverted[0]
  assert not inverted[1]
  different: series[bool | none] = not total == 2
  assert is_null(different[1])

  frame: dataframe[x:i32 | none, y:u32] = dataframe({x:[-1, none, 3], y:[2, 4, 6]})
  values = frame.x
  promoted: series[i64 | none] = values + frame.y
  assert fill_null(promoted[0], 0) == 1
  assert is_null(promoted[1])
  sum: i64 | none = series_sum(promoted)
  assert fill_null(sum, 0) == 10
  assert fill_null(series_min(promoted), 0) == 1
  assert fill_null(series_max(promoted), 0) == 9
  assert fill_null(series_mean(promoted), 0.0) == 5.0
  assert series_count(promoted) == 2
  scalar: nullable[i64] = values[2] + cast(2147483647, i64)
  assert fill_null(scalar, 0) == cast(2147483647, i64) + 3
  assert is_null(values[1] + cast(2147483647, i64))
  present: series[bool] = not is_null(promoted)
  assert fill_null(series_any(present), false)
  assert not fill_null(series_all(present), true)

  caught: i32 = 0
  try:
    values = values + 2147483647
  except OverflowError:
    caught = caught + 1
  assert fill_null(values[2], 0) == 3
  assert fill_null(frame.x[2], 0) == 3
  try:
    values[0] = values[2] / 0
  except ZeroDivisionError:
    caught = caught + 1
  assert fill_null(values[0], 0) == -1
  try:
    values / 0
  except ZeroDivisionError:
    caught = caught + 1
  minimum: i32 = -2147483647 - 1
  limits: dataframe[x:i32] = dataframe({x:[minimum]})
  try:
    limits.x / -1
  except OverflowError:
    caught = caught + 1
  optional: nullable[i32] = minimum
  try:
    optional / -1
  except OverflowError:
    caught = caught + 1
  assert caught == 5

  floating: dataframe[x:f64] = dataframe({x:[1.0, 0.0]})
  divided: series[f64] = floating.x / 0.0
  assert divided[0] > 1.0
  assert not (divided[1] == divided[1])
  optional_float: nullable[f64] = 1.0
  assert fill_null(optional_float / 0.0, 0.0) > 1.0
