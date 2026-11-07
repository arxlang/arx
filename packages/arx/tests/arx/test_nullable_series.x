```
title: Nullable scalar and Series tests
summary: Validate null-preserving indexing and owned column kernels.
```

nullable_values: fn() -> series[i32 | none]:
  ```
  title: Return an independently owned column
  ```
  frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3]})
  return frame.x

test_nullable_series: fn() -> none:
  ```
  title: Nullable arithmetic and masks
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
