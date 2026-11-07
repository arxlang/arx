```
title: Compiled named call regression
summary: Verifies functions, methods, static calls, and dependent default holes.
```
combine: fn(a: i32, b: i32 = a + 1, c: i32 = b + 1) -> i32:
  ```
  title: combine
  ```
  return a * 100 + b * 10 + c

class Counter:
  ```
  title: Counter
  ```
  value: i32 = 7
  read: fn(self, offset: i32 = self.value) -> i32:
    ```
    title: read
    ```
    return offset

  add: static :: fn(a: i32, b: i32 = 3) -> i32:
    ```
    title: add
    ```
    return a + b

test_keyword_arguments: fn() -> none:
  ```
  title: test_keyword_arguments
  ```
  assert combine(c=9, a=2) == 239
  assert combine(a=4) == 456
  counter: Counter = Counter()
  assert counter.read(offset=3) == 3
  assert counter.read() == 7
  assert Counter.add(b=9, a=2) == 11
