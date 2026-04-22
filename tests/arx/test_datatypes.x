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
  var a: i8 = cast(7, i8)
  var b: i16 = cast(11, i16)
  var c: i64 = cast(13, i64)
  var d: f16 = cast(2, f16)
  var e: f32 = cast(3, f32)
  var f: f64 = cast(4, f64)
  var aa: i32 = cast(a, i32)
  var bb: i32 = cast(b, i32)
  var cc: i32 = cast(c, i32)
  var dd: i32 = cast(d, i32)
  var ee: i32 = cast(e, i32)
  var ff: i32 = cast(f, i32)
  return aa + bb + cc + dd + ee + ff

fn touch() -> none:
  ```
  title: touch
  summary: Exercises one helper with a none return type.
  ```
  var sentinel: bool = true

fn test_boolean_and_string_paths() -> none:
  ```
  title: test_boolean_and_string_paths
  summary: Covers bool parameters, string parameters, and defaults.
  ```
  var default_flag: bool
  var empty_text: str
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

fn test_none_helpers() -> none:
  ```
  title: test_none_helpers
  summary: Confirms none-returning helpers can be invoked in tests.
  ```
  touch()
  assert choose(true, 1, 0) == 1
