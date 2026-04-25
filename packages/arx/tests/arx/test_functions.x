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
  var invoked: i32 = 1

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
