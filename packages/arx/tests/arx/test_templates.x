```
title: Repository template tests
summary: Cover generic function inference and explicit specialization.
```

type SignedInteger = i8 | i16 | i32 | i64
type UnsignedInteger = u8 | u16 | u32 | u64
type Integer = SignedInteger | UnsignedInteger
type Float = f32 | f64
type Real = Integer | Float

@<T: Real>
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
  @<T: Real>
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

fn test_composed_numeric_bounds() -> none:
  ```
  title: test_composed_numeric_bounds
  summary: Reuse composed integer and float bounds without returning a union.
  ```
  assert isinstance(add(cast(1, i8), cast(2, i8)), i8)
  assert isinstance(add(cast(1, i16), cast(2, i16)), i16)
  assert isinstance(add(cast(1, i64), cast(2, i64)), i64)
  assert isinstance(add(cast(1, u8), cast(2, u8)), u8)
  assert isinstance(add(cast(1, u16), cast(2, u16)), u16)
  assert isinstance(add(cast(1, u32), cast(2, u32)), u32)
  assert isinstance(add(cast(1, u64), cast(2, u64)), u64)
  assert isinstance(add(cast(1.0, f32), cast(2.0, f32)), f32)
  assert add(cast(1, u64), cast(2, u64)) == cast(3, u64)
  assert add(cast(1.0, f32), cast(2.0, f32)) == 3.0
  assert Math.identity(cast(5, u64)) == cast(5, u64)
