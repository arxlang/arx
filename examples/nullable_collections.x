```
title: Nullable by-value collection owners with independent validity
```
class Collections:
  ```
  title: Independently managed optional list and tensor fields
  ```
  @[public, mutable]
  values: list[i32] | none
  @[public, mutable]
  row: tensor[i32, 2] | none

fn row() -> tensor[i32, 2]:
  var result: tensor[i32, 2] = [4, 9]
  return result

fn optional_row(value: tensor[i32, 2] | none = none) -> tensor[i32, 2] | none:
  return value

fn numbers() -> list[i32]:
  var values: list[i32]
  values.append(0)
  values.append(1)
  values.append(2)
  return values

fn empty_list() -> list[i32]:
  var values: list[i32]
  return values

fn optional_list(present: bool) -> list[i32] | none:
  var values: list[i32] | none = none
  if present:
    values = numbers()
  return values

fn total(values: list[i32]) -> i32:
  var result: i32 = 0
  for item in values:
    result = result + item
  return result

fn second(value: tensor[i32, 2]) -> i32:
  return value[1]

fn main() -> i32:
  var missing: list[i32] | none = optional_list(false)
  assert is_null(missing)
  var empty: list[i32] | none = empty_list()
  assert is_valid(empty)
  assert total(expect_valid(empty)) == 0
  var values: list[i32] | none = optional_list(true)
  assert total(expect_valid(values)) == 3
  if is_valid(values):
    assert total(values) == 3
    assert values[1] == 1
    values.append(4)
    assert total(values) == 7
  values = none
  assert is_null(values)
  var box: Collections = Collections()
  assert is_null(box.values)
  assert is_null(box.row)
  box.values = optional_list(true)
  assert total(expect_valid(box.values)) == 3
  box.values = none
  assert is_null(optional_row())
  var original: tensor[i32, 2] | none = optional_row(row())
  var alias: tensor[i32, 2] | none = original
  original = none
  if is_valid(alias):
    assert alias[1] == 9
  assert second(expect_valid(alias)) == 9
  box.row = alias
  box.row = box.row
  alias = none
  assert second(expect_valid(box.row)) == 9
  box.row = none
  var index: i32 = 0
  while index < 32:
    var transient: list[i32] | none = optional_list(true)
    assert total(expect_valid(transient)) == 3
    index = index + 1
  return 0
