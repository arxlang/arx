```
title: Named call arguments
summary: Source-order evaluation and call-time defaults use positional native ABI.
```
fn combine(a: i32, b: i32 = a + 1, c: i32 = b + 1) -> i32:
  ```
  title: combine
  summary: Computes a value from explicit and dependent default parameters.
  ```
  return a * 100 + b * 10 + c

fn main() -> i32:
  ```
  title: main
  summary: Omits a middle default while supplying a later argument by name.
  ```
  assert combine(c=9, a=2) == 239
  assert combine(a=4) == 456
  return 0
