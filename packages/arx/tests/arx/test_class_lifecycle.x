```
title: Compiled class lifecycle regression
summary: Verifies constructor keywords, aliases, returns, and final destruction.
```

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
