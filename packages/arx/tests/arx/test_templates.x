```
title: Repository template tests
summary: Cover generic function inference and explicit specialization.
```

@<T: i32 | f64>
fn add(lhs: T, rhs: T) -> T:
  ```
  title: add
  summary: Returns the sum of two values with the same template type.
  ```
  return lhs + rhs

class Math:
  ```
  title: Math
  summary: Hosts one static generic identity helper.
  ```
  @[public, static]
  @<T: i32 | f64>
  fn identity(value: T) -> T:
    ```
    title: identity
    summary: Returns one value unchanged through a static method.
    ```
    return value

fn test_template_inference() -> none:
  ```
  title: test_template_inference
  summary: Verifies inferred and explicit integer template calls.
  ```
  assert add(1, 2) == 3
  assert add<int32>(3, 4) == 7
  assert Math.identity<int32>(5) == 5

fn test_template_float_specialization() -> none:
  ```
  title: test_template_float_specialization
  summary: Verifies explicit floating-point specialization and casting.
  ```
  var decimal: f64 = add<f64>(1.5, 2.5)
  var rounded: i32 = cast(decimal, i32)
  assert rounded == 4
