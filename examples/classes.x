```
title: Classes example
summary: Exercises inheritance, class construction, typed class values, and static plus instance access.
```
class BaseCounter:
  @[public, mutable]
  value: int32 = 41

  @[protected]
  fn read_seed(self) -> int32:
    ```
    title: read_seed
    summary: Reads the inherited seed value.
    ```
    return self.value

class Counter(BaseCounter):
  @[public, static, constant]
  version: int32 = 3

  @[private, mutable]
  internal: int32 = 5

  @[protected]
  fn internal_total(self) -> int32:
    ```
    title: internal_total
    summary: Combines private and inherited state.
    ```
    return self.internal + self.value

  fn get(self) -> int32:
    ```
    title: get
    summary: Returns the inherited public counter value.
    ```
    return self.value

  fn read_internal(self) -> int32:
    ```
    title: read_internal
    summary: Uses a protected helper to expose internal state safely.
    ```
    return self.internal_total()

class CounterFactory:
  @[public, static]
  fn make() -> Counter:
    ```
    title: make
    summary: Builds a default counter instance.
    ```
    return Counter()

  @[public, static]
  fn version_value() -> int32:
    ```
    title: version_value
    summary: Reads the static class version.
    ```
    return Counter.version

fn take_counter(counter: Counter) -> int32:
  ```
  title: take_counter
  summary: Combines method and attribute access on a typed class value.
  ```
  return counter.get() + counter.value + counter.read_internal()

fn main() -> int32:
  ```
  title: main
  summary: Exercises class construction, static access, and instance calls.
  ```
  var direct: Counter = Counter()
  var built: Counter = CounterFactory.make()
  var total: int32 = take_counter(direct) + built.get()
  return total + CounterFactory.version_value() + Counter.version
