```
title: Owned list expressions
summary: Exercise expression order, ownership, element copies, and length.
```

class Trace:
  ```
  title: Mutable evaluation order recorder
  ```
  @[public, mutable]
  value: i32 = 0

fn record(log: Trace, value: i32) -> i32:
  ```
  title: Record exactly one element evaluation
  ```
  log.value = log.value * 10 + value
  if value == 9:
    raise ValueError("failed element")
  return value

fn make(log: Trace) -> list[i32]:
  ```
  title: Return owned expression storage
  ```
  return [record(log, 1), record(log, 2) + 1, cast(4, i32)]

fn count(values: list[i32]) -> i64:
  ```
  title: Borrow a list through a call
  ```
  return len(values)

fn first_word(values: list[str]) -> str:
  ```
  title: Return an independent copy of a list element
  ```
  return values[0]

fn first_iteration(values: list[str]) -> str:
  ```
  title: Copy a string iteration value out of a borrowed list
  ```
  for word in values:
    return word
  return "empty"

fn test_owned_lists() -> none:
  ```
  title: Build, borrow, move, and replace owned lists
  ```
  var log: Trace = Trace()
  var values: list[i32] = make(log)
  assert log.value == 12
  assert values[1] == 3
  assert values[2] == 4
  assert count([5, 6]) == 2
  values = [values[0] + 6]
  assert values[0] == 7
  values = []
  assert len(values) == 0
  var wide: i64 = [1, 7693600637][1]
  assert wide == [7693600637, 1][0]
  var narrow: i8 = [1, 2][0]
  assert narrow == 1

fn test_partial_construction() -> none:
  ```
  title: Stop at a failed element and preserve the assignment destination
  ```
  var log: Trace = Trace()
  var values: list[i32] = [7]
  var caught: bool = false
  try:
    values = [record(log, 1), record(log, 9), record(log, 3)]
  except ValueError:
    caught = true
  assert caught
  assert log.value == 19
  assert values[0] == 7

fn test_owned_string_elements() -> none:
  ```
  title: Copy inserted and indexed strings across independent owner lifetimes
  ```
  var source: str = "owned" + " word"
  var values: list[str] = [source, "other"]
  source = "replacement" + "!"
  var first: str = first_word(values)
  values.append(first)
  values = []
  assert first == "owned word"
  assert first_iteration(["first", "second"]) == "first"
  values = ["stable"]
  var retained: str = first_iteration(values)
  values = []
  assert retained == "stable"

fn return_iterated_list() -> list[i32]:
  ```
  title: Return the iterated owner without losing its storage
  ```
  var values: list[i32] = [7, 8]
  for value in values:
    return values
  return values

fn test_iteration_owner_boundaries() -> none:
  ```
  title: Preserve append bounds and replace only independent or released owners
  ```
  var values: list[i32] = [1, 2, 3]
  var other: list[i32] = []
  var total: i32 = 0
  for value in values:
    values.append(9)
    other = [value]
    total += other[0]
    for inner in [0]:
      var values: list[i32] = [inner]
      values = [7]
      assert values[0] == 7
  assert total == 6
  assert len(values) == 6
  values = [total]
  for values in values:
    assert values == 6
  values = []
  for value in values:
    assert false
  for value in return_iterated_list():
    total += value
  assert total == 21
  values = [1]
  try:
    for value in values:
      raise ValueError("leave iteration")
  except ValueError:
    values = [2]
  assert values[0] == 2
