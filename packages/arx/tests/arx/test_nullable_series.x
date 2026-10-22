```
title: Nullable scalar and Series tests
summary: Validate null-preserving indexing and owned column kernels.
```

fn nullable_values() -> series[i32 | none]:
  ```
  title: Return an independently owned column
  ```
  var frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3]})
  return frame.x

fn test_nullable_series() -> none:
  ```
  title: Nullable arithmetic and masks
  ```
  var values: series[i32 | none] = nullable_values()
  var total: series[i32 | none] = values + values
  var missing: nullable[i32] = total[1]
  assert is_null(missing)
  assert fill_null(total[2], 0) == 6
  var filled: series[i32] = fill_null(total, 7)
  assert filled[1] == 7
  var mask: series[bool] = is_null(total)
  assert mask[1]
  assert !mask[0]
