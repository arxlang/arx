```
title: Repository function tests
summary: Cover helper calls, recursion, composition, and none helpers.
```

fn add(lhs: i32, rhs: i32) -> i32:
  ```
  title: add
  summary: Returns the sum of two integer values.
  ```
  return lhs + rhs

fn mul_add(lhs: i32, rhs: i32, extra: i32) -> i32:
  ```
  title: mul_add
  summary: Multiplies two values and adds one extra offset.
  ```
  return (lhs * rhs) + extra

fn add_offset(value: i32, offset: i32 = 1) -> i32:
  ```
  title: add_offset
  summary: Adds an optional integer offset to one value.
  ```
  return value + offset

fn fib(value: i32) -> i32:
  ```
  title: fib
  summary: Returns one recursive Fibonacci value.
  ```
  if value < 3:
    return 1
  else:
    return fib(value - 1) + fib(value - 2)

fn note_call() -> none:
  ```
  title: note_call
  summary: Exercises one helper with a none return type.
  ```
  invoked: i32 = 1

fn test_helper_function_calls() -> none:
  ```
  title: test_helper_function_calls
  summary: Verifies direct helper calls and composed arithmetic.
  ```
  assert add(1, 2) == 3
  assert mul_add(2, 3, 4) == 10
  assert add_offset(4) == 5
  assert add_offset(4, 3) == 7

fn test_recursive_calls() -> none:
  ```
  title: test_recursive_calls
  summary: Verifies recursive helper calls remain available in tests.
  ```
  assert fib(6) == 8

fn test_none_returning_helpers() -> none:
  ```
  title: test_none_returning_helpers
  summary: Calls one none-returning helper before another assertion.
  ```
  note_call()
  assert add(2, 2) == 4


class DeclarationBox:
  value: auto = 1
  maximum: static const :: auto = 10
  fn read(self) -> int32:
    return self.value

fn increment_local(value: var :: int32) -> int32:
  value += 1
  return value

@<T: int32 | int64>
fn fixed_identity(value: const :: T) -> T:
  result: const :: auto = value
  return result

fn test_name_first_binding_and_inference() -> none:
  ```
  title: Name-first binding and inference
  summary: Stable object bindings allow mutation while inferred types remain fixed.
  ```
  DECLARATION_LIMIT: const :: auto = 10
  box: const :: auto = DeclarationBox()
  box.value = 3
  values: const :: auto = [1, 2]
  values.append(box.read())
  assert values[2] == 3
  assert increment_local(value=2) == 3
  assert fixed_identity(values[2]) == 3
  assert fixed_identity<int64>(1) == 1
  assert DeclarationBox.maximum == DECLARATION_LIMIT
  total: auto = 0
  for index: auto = 0; index < 3; ++index:
    total += index
  assert total == 3
