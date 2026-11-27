```
title: Compiled class lifecycle regression
summary: Verifies constructor keywords, aliases, returns, and final destruction.
```

import stdlib.memory as memory

class Counter:
  ```
  title: Counter
  ```
  value: i32 = 0
  destroyed: public static var :: i32 = 0

  fn __init__(self, value: i32 = 1) -> none:
    ```
    title: __init__
    ```
    self.value = value
    return none

  fn __del__(self) -> none:
    ```
    title: __del__
    ```
    Counter.destroyed = Counter.destroyed + 1
    return none

fn make_counter() -> Counter:
  ```
  title: make_counter
  ```
  return Counter(value=7)

fn use_aliases() -> none:
  ```
  title: use_aliases
  ```
  counter: Counter = make_counter()
  alias: Counter = counter
  counter = counter
  counter = Counter()
  assert alias.value == 7
  assert counter.value == 1
  return none

fn test_class_lifecycle() -> none:
  ```
  title: test_class_lifecycle
  ```
  Counter.destroyed = 0
  use_aliases()
  assert Counter.destroyed == 2

class Tagged:
  ```
  title: Immutable fields shared by several strong handles
  ```
  key: const :: i32 = 17
  enabled: const :: bool = true
  destroyed: static var :: i32 = 0

  fn __del__(self) -> none:
    ```
    title: Count finalized instances
    ```
    Tagged.destroyed = Tagged.destroyed + 1

  fn sum_key(self, key: &i32) -> i32:
    ```
    title: Read the receiver and its borrowed field in one call
    ```
    return self.key + key

  fn twice(self) -> i32:
    ```
    title: Borrow an immutable field through the method receiver
    ```
    return self.sum_key(&self.key)

class Padding:
  ```
  title: Give the second base a non-prefix object layout
  ```
  pad: i64 = 123

class DerivedTagged(Padding, Tagged):
  ```
  title: Locate a borrowed field through a non-prefix base view
  ```

class EmptyTagged:
  ```
  title: Keep an empty class reference for checked field access
  ```
  item: Tagged

fn read_tag(key: &i32, offset: i32) -> i32:
  ```
  title: Pass an immutable field address to a free function
  ```
  return key + offset

fn use_const_field_borrows() -> none:
  ```
  title: Keep receiver storage alive through retargeting and call cleanup
  ```
  first: Tagged = Tagged()
  alias: Tagged = first
  second: Tagged = DerivedTagged()
  key: &i32 = &first.key
  alias = second
  assert key == 17
  assert Tagged.destroyed == 0
  assert first.twice() == 34
  key = &second.key
  first = second
  assert Tagged.destroyed == 1
  assert key == 17
  assert read_tag(&second.key, 1) == 18
  enabled: auto = &second.enabled
  assert enabled

  empty: Tagged = EmptyTagged().item
  count: i32 = 0
  try:
    read_tag(&empty.key, ++count)
    assert false
  except RuntimeError:
    assert count == 0
    assert key == 17

fn test_const_field_borrows() -> none:
  ```
  title: Release each receiver exactly once after the borrows expire
  ```
  Tagged.destroyed = 0
  use_const_field_borrows()
  assert Tagged.destroyed == 2

class FallibleCopy:
  ```
  title: Count copy hook invocations and release temporary instances
  ```
  value: i32 = 0
  invoked: static var :: i32 = 0
  released: static var :: i32 = 0

  fn __init__(self, value: i32) -> none:
    ```
    title: Set the value used to select the failure path
    ```
    self.value = value

  fn __copy__(self) -> FallibleCopy:
    ```
    title: Count receiver evaluation and optionally fail the copy
    ```
    FallibleCopy.invoked = FallibleCopy.invoked + 1
    if self.value == 0:
      raise ValueError("copy hook failed")
    return FallibleCopy(self.value + 2)

  fn __del__(self) -> none:
    ```
    title: Fail when releasing a negative-valued receiver
    ```
    FallibleCopy.released = FallibleCopy.released + 1
    if self.value < 0:
      raise RuntimeError("copy receiver cleanup failed")

fn test_class_copy_cleanup() -> none:
  ```
  title: Roll back copy results and preserve the previous destination
  ```
  FallibleCopy.invoked = 0
  FallibleCopy.released = 0
  destination: FallibleCopy = FallibleCopy(3)
  try:
    destination = memory.copy(FallibleCopy(0))
    assert false
  except ValueError:
    assert destination.value == 3
    assert FallibleCopy.released == 1
  try:
    destination = memory.copy(FallibleCopy(-1))
    assert false
  except RuntimeError:
    assert destination.value == 3
    assert FallibleCopy.released == 3
  assert FallibleCopy.invoked == 2
