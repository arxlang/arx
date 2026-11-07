```
title: Repository class tests
summary: Cover inheritance, instance methods, field access, and statics.
```

class BaseCounter:
  ```
  title: BaseCounter
  summary: Stores one inherited counter value.
  ```
  value: public var :: int32 = 41

class Counter(BaseCounter):
  ```
  title: Counter
  summary: Extends BaseCounter with private state and helper methods.
  ```
  version: public static const :: int32 = 3

  internal: private var :: int32 = 5

  internal_total: protected :: fn(self) -> int32:
    ```
    title: internal_total
    summary: Combines inherited and private counter state.
    ```
    return self.internal + self.value

  get: public :: fn(self) -> int32:
    ```
    title: get
    summary: Returns the inherited public counter value.
    ```
    return self.value

  read_internal: public :: fn(self) -> int32:
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
  make: public static :: fn() -> Counter:
    ```
    title: make
    summary: Builds one default Counter instance.
    ```
    return Counter()

  version_value: public static :: fn() -> int32:
    ```
    title: version_value
    summary: Returns the static counter version.
    ```
    return Counter.version

take_counter: fn(counter: Counter) -> int32:
  ```
  title: take_counter
  summary: Combines instance method and field access on one counter.
  ```
  return counter.get() + counter.value + counter.read_internal()

test_class_instance_methods_and_fields: fn() -> none:
  ```
  title: test_class_instance_methods_and_fields
  summary: Verifies construction, instance fields, and instance methods.
  ```
  direct: Counter = Counter()
  assert direct.get() == 41
  assert direct.value == 41
  assert direct.read_internal() == 46

test_class_static_members_and_construction: fn() -> none:
  ```
  title: test_class_static_members_and_construction
  summary: Verifies static factory and static field access.
  ```
  built: Counter = CounterFactory.make()
  assert Counter.version == 3
  assert CounterFactory.version_value() == 3
  assert take_counter(built) == 128
