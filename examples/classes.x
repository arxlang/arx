```
title: Classes example
summary: Exercises inheritance, class construction, typed class values, and static plus instance access.
```
class BaseCounter:
  ```
  title: BaseCounter
  summary: Stores one inherited seed value for derived counters.
  ```
  value: public var :: int32 = 41

  fn read_seed(self) -> protected :: int32:
    ```
    title: read_seed
    summary: Reads the inherited seed value.
    ```
    return self.value

class Counter(BaseCounter):
  ```
  title: Counter
  summary: Extends BaseCounter with private state and helper methods.
  ```
  version: public static const :: int32 = 3

  internal: private var :: int32 = 5

  fn internal_total(self) -> protected :: int32:
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
  ```
  title: CounterFactory
  summary: Builds Counter instances and exposes static class metadata.
  ```
  fn make() -> public static :: Counter:
    ```
    title: make
    summary: Builds a default counter instance.
    ```
    return Counter()

  fn version_value() -> public static :: int32:
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
  direct: Counter = Counter()
  built: Counter = CounterFactory.make()
  total: int32 = take_counter(direct) + built.get()
  return total + CounterFactory.version_value() + Counter.version
