```
title: Compiled named call regression
summary: Verifies functions, methods, static calls, and dependent default holes.
```
fn combine(a: i32, b: i32 = a + 1, c: i32 = b + 1) -> i32:
  ```
  title: combine
  ```
  return a * 100 + b * 10 + c

class Counter:
  ```
  title: Counter
  ```
  value: i32 = 7
  fn read(self, offset: i32 = self.value) -> i32:
    ```
    title: read
    ```
    return offset

  @[static]
  fn add(a: i32, b: i32 = 3) -> i32:
    ```
    title: add
    ```
    return a + b

fn test_keyword_arguments() -> none:
  ```
  title: test_keyword_arguments
  ```
  assert combine(c=9, a=2) == 239
  assert combine(a=4) == 456
  var counter: Counter = Counter()
  assert counter.read(offset=3) == 3
  assert counter.read() == 7
  assert Counter.add(b=9, a=2) == 11
