```
title: Classes example
summary: Demonstrates annotated class fields and methods.
```
class Counter:
  @[public, static, constant]
  version: int32 = 1

  @[private]
  internal: int32 = 1

  value: int32 = 0

  fn get(self) -> int32:
    ```
    title: get
    summary: Returns the current counter value.
    ```
    return self.value

class Math:
  @[public, static]
  fn twice(x: int32) -> int32:
    ```
    title: twice
    summary: Returns the provided value multiplied by two.
    ```
    return x + x
