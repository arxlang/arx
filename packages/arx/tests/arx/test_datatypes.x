```
title: Repository datatype tests
summary: Cover scalar types, casts, defaults, strings, booleans, and none helpers.
```

fn choose(flag: bool, when_true: i32, when_false: i32) -> i32:
  ```
  title: choose
  summary: Returns one branch-selected integer value.
  ```
  if flag && true:
    return when_true
  else:
    return when_false

fn tag_value(text: str, flag: bool) -> i32:
  ```
  title: tag_value
  summary: Uses typed string and boolean parameters in one branch.
  ```
  if flag:
    return 1
  else:
    return 0

fn widened_total() -> i32:
  ```
  title: widened_total
  summary: Casts across numeric widths and normalizes them to i32.
  ```
  a: i8 = cast(7, i8)
  b: i16 = cast(11, i16)
  c: i64 = cast(13, i64)
  d: f16 = cast(2, f16)
  e: f32 = cast(3, f32)
  f: f64 = cast(4, f64)
  aa: i32 = cast(a, i32)
  bb: i32 = cast(b, i32)
  cc: i32 = cast(c, i32)
  dd: i32 = cast(d, i32)
  ee: i32 = cast(e, i32)
  ff: i32 = cast(f, i32)
  return aa + bb + cc + dd + ee + ff

fn touch() -> none:
  ```
  title: touch
  summary: Exercises one helper with a none return type.
  ```
  sentinel: bool = true

fn fail_if_evaluated() -> bool:
  ```
  title: fail_if_evaluated
  summary: Fails when a short-circuited Boolean right operand is evaluated.
  ```
  assert false
  return true

fn test_boolean_and_string_paths() -> none:
  ```
  title: test_boolean_and_string_paths
  summary: Covers bool parameters, string parameters, and defaults.
  ```
  default_flag: bool
  empty_text: str
  assert choose(true, 10, 20) == 10
  assert choose(false, 10, 20) == 20
  assert choose(default_flag, 1, 2) == 2
  assert tag_value("ok", true) == 1
  assert tag_value(empty_text, false) == 0

fn test_numeric_casts_and_widths() -> none:
  ```
  title: test_numeric_casts_and_widths
  summary: Covers integer and floating-point cast combinations.
  ```
  assert widened_total() == 40

fn test_fixed_width_integer_wrapping() -> none:
  ```
  title: test_fixed_width_integer_wrapping
  summary: Confirms explicitly wrapping arithmetic and casts use modulo semantics.
  ```
  maximum: i32 = 2147483647
  minimum: i32 = wrapping_cast(2147483648, i32)
  assert wrapping_add(maximum, 1) == minimum
  assert wrapping_sub(minimum, 1) == maximum
  assert wrapping_mul(65536, 65536) == 0

fn test_none_helpers() -> none:
  ```
  title: test_none_helpers
  summary: Confirms none-returning helpers can be invoked in tests.
  ```
  touch()
  assert choose(true, 1, 0) == 1

fn test_boolean_short_circuit_evaluation() -> none:
  ```
  title: test_boolean_short_circuit_evaluation
  summary: Confirms Boolean operands evaluate left to right and short circuit.
  ```
  assert (false && fail_if_evaluated()) == false
  assert (true || fail_if_evaluated()) == true
  assert not false or fail_if_evaluated()
  assert not (false and not fail_if_evaluated())

fn test_scalar_remainder_and_negation() -> none:
  ```
  title: test_scalar_remainder_and_negation
  summary: Remainder truncates rather than implementing Python floor modulo.
  ```
  move: i32 = -5
  size: i32 = 100
  assert move / size == 0
  assert move % size == -5
  # For a positive modulus, add only to a negative remainder to avoid overflow.
  position: i32 = move % size
  if position < 0:
    position = position + size
  assert position == 95
  assert not move == size and true
  assert not not (move < size)
  assert !false
  assert 3 - -2 == 5
  assert -move == 5
  assert 17 % 5 * 2 == 4
