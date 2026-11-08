```
title: Template example
summary: Demonstrates compile-time template specialization for functions.
```
@<T: i32 | f64>
fn add(lhs: T, rhs: T) -> T:
  ```
  title: add
  summary: Adds two values that share the same template-bound type.
  ```
  return lhs + rhs

fn main() -> i32:
  ```
  title: main
  summary: Calls inferred and explicit template specializations.
  ```
  print(add(1, 2))
  print(add<f64>(1.5, 2.5))
  return 0
