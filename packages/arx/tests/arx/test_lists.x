```
title: Owned list expressions
summary: Exercise expression order, ownership, element copies, and length.
```

class Trace:
  ```
  title: Mutable evaluation order recorder
  ```
  value: public var :: i32 = 0

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

fn count(values: &list[i32]) -> i64:
  ```
  title: Borrow a list through a call
  ```
  return len(values)

fn first_word(values: &list[str]) -> str:
  ```
  title: Return an independent copy of a list element
  ```
  return values[0]

fn first_iteration(values: &list[str]) -> str:
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
  log: Trace = Trace()
  values: list[i32] = make(log)
  assert log.value == 12
  assert values[1] == 3
  assert values[2] == 4
  more: list[i32] = [5, 6]
  assert count(&more) == 2
  values = [values[0] + 6]
  assert values[0] == 7
  values = []
  assert len(values) == 0
  wide: i64 = [1, 7693600637][1]
  assert wide == [7693600637, 1][0]
  narrow: i8 = [1, 2][0]
  assert narrow == 1

fn test_partial_construction() -> none:
  ```
  title: Stop at a failed element and preserve the assignment destination
  ```
  log: Trace = Trace()
  values: list[i32] = [7]
  caught: bool = false
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
  source: str = "owned" + " word"
  values: list[str] = [source, "other"]
  source = "replacement" + "!"
  first: str = first_word(&values)
  values.append(first)
  values = []
  assert first == "owned word"
  words: list[str] = ["first", "second"]
  assert first_iteration(&words) == "first"
  values = ["stable"]
  retained: str = first_iteration(&values)
  values = []
  assert retained == "stable"

fn return_iterated_list() -> list[i32]:
  ```
  title: Return the iterated owner without losing its storage
  ```
  values: list[i32] = [7, 8]
  for value in values:
    return values
  return values

fn clone_words(words: &list[str]) -> list[str]:
  ```
  title: Return a new owner copied from a read-only list parameter
  ```
  return clone(words)

fn test_list_clone() -> none:
  ```
  title: Copy list storage and elements without consuming the source
  ```
  values: list[i32] = [10, 20]
  backup: list[i32] = []
  if true:
    first: auto = &values[0]
    backup = clone(values)
    assert first == 10
  if true:
    editor: auto = &&backup[0]
    editor = 11
  values.append(30)
  assert values[0] == 10
  assert backup[0] == 11
  assert len(backup) == 2
  backup = clone(backup)
  assert backup[1] == 20

  empty: list[bool] = []
  flags: auto = clone(empty)
  flags.append(true)
  assert len(empty) == 0
  assert flags[0]

  log: Trace = Trace()
  assert clone(make(log))[1] == 3
  assert log.value == 12
  source: list[str] = ["", "copied" + " text"]
  words: auto = clone_words(&source)
  source = []
  assert words[0] == ""
  assert words[1] == "copied text"

class FallibleCloneSource:
  ```
  title: Leave a fallible temporary in a clone operand
  ```

  fn words(self) -> list[str]:
    return ["new"]

  fn __del__(self) -> none:
    raise ValueError("clone operand cleanup")

fn test_list_clone_cleanup() -> none:
  ```
  title: Drop an unpublished copy if cleaning up its operand raises
  ```
  destination: list[str] = ["old"]
  try:
    destination = clone(FallibleCloneSource().words())
    assert false
  except ValueError:
    assert destination[0] == "old"

fn test_iteration_owner_boundaries() -> none:
  ```
  title: Preserve append bounds and replace only independent or released owners
  ```
  values: list[i32] = [1, 2, 3]
  other: list[i32] = []
  total: i32 = 0
  for value in values:
    values.append(9)
    other = [value]
    total += other[0]
    for inner in [0]:
      values: list[i32] = [inner]
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


fn grow(values: &&list[i32], fail: bool) -> none:
  ```
  title: Grow borrowed storage and optionally raise after growth
  ```
  before: i64 = count(&values)
  for index in range(0, 24):
    values.append(cast(index, i32))
  assert count(&values) == before + 24
  if fail:
    raise ValueError("after growth")

fn combined_length(left: &list[i32], right: &list[i32]) -> i64:
  ```
  title: Read independently through compatible shared borrows
  ```
  return len(left) + len(right)

fn test_call_scoped_list_borrows() -> none:
  ```
  title: Commit growth through a borrow and release the loan on return or raise
  ```
  values: list[i32] = [99]
  grow(fail=false, values=&&values)
  assert values[24] == 23
  assert combined_length(&values, &values) == 50

  try:
    grow(&&values, true)
    assert false
  except ValueError:
    assert count(&values) == 49
    assert values[48] == 23
  values.append(4)
  assert values[49] == 4


class ListReader:
  ```
  title: View lists through method overloads
  ```
  fn process(self, values: &list[i32]) -> i64:
    ```
    title: Read the length through a shared loan
    ```
    return len(values)

  fn process(self, values: &&list[i32]) -> i64:
    ```
    title: Append through an exclusive loan
    ```
    values.append(1)
    return len(values)

class ListEditor(ListReader):
  ```
  title: Override only the exclusive overload
  ```
  fn process(self, values: &&list[i32]) -> i64:
    ```
    title: Grow the caller list across a buffer reallocation
    ```
    grow(&&values, false)
    return len(values)

  fn size(values: &list[i32]) -> static :: i64:
    ```
    title: Accept a read-only borrow in a static method
    ```
    return len(values)

class ListInitializer:
  ```
  title: Borrow a list for construction
  ```
  fn __init__(self, values: &&list[i32], fail: bool) -> none:
    ```
    title: Grow the list even when construction raises
    ```
    values.append(42)
    if fail:
      raise ValueError("after append")

fn process_through_base(reader: ListReader, values: &&list[i32]) -> i64:
  ```
  title: Dispatch an exclusive method through its base type
  ```
  return reader.process(values=&&values)

fn test_method_list_borrows() -> none:
  ```
  title: Preserve access modes through overload selection and dispatch
  ```
  values: list[i32] = [7]
  editor: ListEditor = ListEditor()
  assert editor.process(&values) == 1
  assert process_through_base(editor, &&values) == 25
  assert ListEditor.size(&values) == 25
  assert values[24] == 23

  try:
    failed: ListInitializer = ListInitializer(fail=true, values=&&values)
    assert false
  except ValueError:
    assert values[25] == 42
  built: ListInitializer = ListInitializer(&&values, false)
  assert values[26] == 42

fn update_list_element(values: &&list[i32]) -> i32:
  ```
  title: Borrow a writable element through an exclusive list parameter
  ```
  first: &&i32 = &&values[0]
  second: &&i32 = &&values[1]
  first += 1
  ++second
  assert values[2] == 30
  return first + second

fn test_list_element_borrows() -> none:
  ```
  title: Check element addresses once and release loans on lexical exits
  ```
  values: list[i32] = [10, 20, 30]
  assert update_list_element(&&values) == 32
  assert values[0] == 11
  assert values[1] == 21

  index: i32 = 0
  scalar: i32 = 5
  item: auto = &&values[++index]
  assert index == 1
  index = 2
  item = 42
  assert index == 2
  item = &&values[0]
  item = &&values[0]
  assert values[1] == 42
  item = &&scalar
  values.append(4)
  values.append(5)
  item = &&values[4]
  assert item == 5
  item = &&scalar

  try:
    entry: auto = &&values[1]
    entry = &&values[99]
    assert false
  except IndexError:
    assert values[1] == 42
  values.append(6)

  backup: list[i32] = [8]
  item = &&values[1]
  try:
    item = &&backup[99]
    assert false
  except IndexError:
    assert item == 42
    item = 43
  finally:
    item = &&scalar
  assert values[1] == 43
  values.append(7)

  try:
    overflow: u64 = 18446744073709551615
    missing: auto = &values[overflow]
    assert false
  except IndexError:
    assert values[0] == 11

  flags: list[bool] = [false, true]
  if true:
    flag: const :: &&bool = &&flags[0]
    flag = true
    assert flags[1]
  assert flags[0]

  reader: &i32 = &values[0]
  same: auto = &values[0]
  assert reader == same
  assert values[0] == 11

fn bump_element(value: &&i32, amount: i32) -> i32:
  ```
  title: Write through a call-scoped exclusive scalar parameter
  ```
  value += amount
  return value

fn combine_elements(left: &i32, right: &i32) -> i32:
  ```
  title: Read two compatible shared loans of the same or disjoint places
  ```
  return left + right

fn exchange_elements(left: &&i32, right: &&i32) -> none:
  ```
  title: Forward one scalar loan and assign through another
  ```
  old: auto = left
  left = right
  right = old
  bump_element(&&right, 1)

class ElementEditor:
  ```
  title: Use scalar loans through constructors and virtual dispatch
  ```
  fn __init__(self, value: &&i32) -> none:
    ```
    title: Update the caller's element before returning
    ```
    ++value

  fn edit(self, flag: &&bool, value: &&i32) -> none:
    ```
    title: Mutate borrowed elements and propagate a checked exception
    ```
    flag = true
    ++value
    raise ValueError("after updating elements")

fn test_call_scoped_list_element_borrows() -> none:
  ```
  title: Bind projected arguments once and release loans on success or failure
  ```
  values: list[i32] = [10, 20, 30]
  index: i32 = -1
  assert bump_element(amount=30, value=&&values[++index]) == 40
  assert index == 0
  assert bump_element(&&values[0], values[2] - 30) == 40
  assert combine_elements(&values[0], &values[0]) == 80
  exchange_elements(&&values[0], &&values[1])
  assert values[0] == 20
  assert values[1] == 41

  try:
    bump_element(&&values[99], ++index)
    assert false
  except IndexError:
    assert index == 0
  values.append(4)

  editor: ElementEditor = ElementEditor(&&values[1])
  flags: list[bool] = [false]
  try:
    editor.edit(&&flags[0], &&values[1])
    assert false
  except ValueError:
    assert flags[0]
    assert values[1] == 43
  values = [1]
  assert bump_element(&&values[0], 1) == 2
