```
title: Repository class tests
summary: Cover inheritance, instance methods, field access, and statics.
```

class BaseCounter:
  ```
  title: BaseCounter
  summary: Stores one inherited counter value.
  ```
  @[public, mutable]
  value: int32 = 41

class Counter(BaseCounter):
  ```
  title: Counter
  summary: Extends BaseCounter with private state and helper methods.
  ```
  @[public, static, constant]
  version: int32 = 3

  @[private, mutable]
  internal: int32 = 5

  @[protected]
  fn internal_total(self) -> int32:
    ```
    title: internal_total
    summary: Combines inherited and private counter state.
    ```
    return self.internal + self.value

  @[public]
  fn get(self) -> int32:
    ```
    title: get
    summary: Returns the inherited public counter value.
    ```
    return self.value

  @[public]
  fn read_internal(self) -> int32:
    ```
    title: read_internal
    summary: Exposes the protected total through one public method.
    ```
    return self.internal_total()

class CounterFactory:
  ```
  title: CounterFactory
  summary: Builds counters and exposes static class metadata.
  ```
  @[public, static]
  fn make() -> Counter:
    ```
    title: make
    summary: Builds one default Counter instance.
    ```
    return Counter()

  @[public, static]
  fn version_value() -> int32:
    ```
    title: version_value
    summary: Returns the static counter version.
    ```
    return Counter.version

fn take_counter(counter: Counter) -> int32:
  ```
  title: take_counter
  summary: Combines instance method and field access on one counter.
  ```
  return counter.get() + counter.value + counter.read_internal()

fn test_class_instance_methods_and_fields() -> none:
  ```
  title: test_class_instance_methods_and_fields
  summary: Verifies construction, instance fields, and instance methods.
  ```
  var direct: Counter = Counter()
  assert direct.get() == 41
  assert direct.value == 41
  assert direct.read_internal() == 46

fn test_class_static_members_and_construction() -> none:
  ```
  title: test_class_static_members_and_construction
  summary: Verifies static factory and static field access.
  ```
  var built: Counter = CounterFactory.make()
  assert Counter.version == 3
  assert CounterFactory.version_value() == 3
  assert take_counter(built) == 128
