```
title: Exact read-only numeric sequences
summary: One generic consumer over lists, tensors, ranges, and typed columns.
```

@<T: i32 | i64 | f64>
first: fn(values: sequence[T]) -> T:
  ```
  title: Read the first item without converting or copying the collection.
  ```
  for item in values:
    assert item == values[0]
    return item
  return values[0]

runtime_item: fn(values: tensor[i64, ...], index: i64) -> i64:
  ```
  title: Use runtime tensor shape with checked nonnegative indexing.
  ```
  assert len(values) == 2
  return values[index]

@<T: i32 | i64 | f64>
column_first: fn(values: series[T]) -> T:
  ```
  title: Infer template variables nested in Series declarations.
  ```
  return first(values)

@<T: i32 | i64 | f64>
list_first: fn(values: list[T]) -> T:
  ```
  title: Infer template variables nested in owned list declarations.
  ```
  for item in values:
    return item
  return values[0]

@<T: i32 | i64 | f64>
nullable_first: fn(values: sequence[nullable[T]]) -> nullable[T]:
  ```
  title: Preserve the column validity contract separately from numeric bits.
  ```
  return values[0]

main: fn() -> i32:
  ```
  title: Exercise the same consumers with inferred and explicit type arguments.
  ```
  values: list[i64] = [9007199254740993, 9223372036854775807]
  tensor_values: tensor[i64, 2] = [9007199254740993, 9223372036854775807]
  frame: dataframe[id:i64, missing:i64 | none] = dataframe({
    id: [9007199254740993, 9223372036854775807],
    missing: [none, 9223372036854775807],
  })
  assert first(values) == 9007199254740993
  assert first<i64>(values) == first(tensor_values)
  assert first<i64>(tensor_values) == first(frame.id)
  assert first<i64>(frame.id) == column_first(frame.id)
  assert list_first(values) == first(values)
  assert first([3, 5]) == 3
  assert first<i64>([3, 5]) == 3
  assert first(range(3, 5)) == 3
  assert runtime_item(tensor_values, 1) == 9223372036854775807
  assert is_null(nullable_first(frame.missing))
  assert is_null(nullable_first<i64>(frame.missing))
  copied: list[i64] = list(tensor_values, max_items=2)
  assert len(copied) == 2
  assert copied[1] == 9223372036854775807
  return 0
