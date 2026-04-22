# Built-in Types

Arx has a small set of built-in types that can be used in variable annotations,
function parameters, and function return types. This page is the reference for
their canonical spellings, accepted aliases, and current surface syntax.

## Overview

| Canonical type    | Accepted aliases | Category   | Example                                           | Notes                                    |
| ----------------- | ---------------- | ---------- | ------------------------------------------------- | ---------------------------------------- |
| `i8`              | `int8`           | integer    | `var a: i8 = 8`                                   | 8-bit integer                            |
| `i16`             | `int16`          | integer    | `var b: i16 = 16`                                 | 16-bit integer                           |
| `i32`             | `int32`          | integer    | `var c: i32 = 32`                                 | 32-bit integer                           |
| `i64`             | `int64`          | integer    | `var d: i64 = 64`                                 | 64-bit integer                           |
| `f16`             | `float16`        | float      | `var x: f16 = 1.5`                                | 16-bit float                             |
| `f32`             | `float32`        | float      | `var y: f32 = 3.25`                               | 32-bit float                             |
| `f64`             | `float64`        | float      | `var z: f64 = 9.5`                                | 64-bit float                             |
| `bool`            | `boolean`        | boolean    | `var ok: bool = true`                             | Uses `true` and `false` literals         |
| `none`            | —                | unit       | `fn log() -> none:`                               | Also the single value of the `none` type |
| `str`             | `string`         | text       | `var s: str = "hi"`                               | UTF-8 string                             |
| `char`            | —                | text       | `var ch: char = 'A'`                              | Currently mapped to `i8`                 |
| `datetime`        | —                | temporal   | `datetime("2026-03-05T12:30:59")`                 | Constructor-style literal form           |
| `timestamp`       | —                | temporal   | `timestamp("2026-03-05T12:30:59Z")`               | Constructor-style literal form           |
| `date`            | —                | temporal   | `var d: date`                                     | Recognized as a built-in type name       |
| `time`            | —                | temporal   | `var t: time`                                     | Recognized as a built-in type name       |
| `array[T]`        | —                | collection | `var ids: array[i32] = [1, 2, 3]`                 | Legacy list-style spelling               |
| `array[T, N]`     | —                | collection | `var ids: array[i32, 4] = [1, 2, 3, 4]`           | Builtin shaped 1D array                  |
| `ndarray[T, ...]` | —                | collection | `var grid: ndarray[i32, 2, 2] = [[1, 2], [3, 4]]` | Builtin multidimensional array           |

## Numeric Types

Arx accepts both short canonical names and longer aliases in type annotations:

- integers: `i8`, `i16`, `i32`, `i64`
- integer aliases: `int8`, `int16`, `int32`, `int64`
- floats: `f16`, `f32`, `f64`
- float aliases: `float16`, `float32`, `float64`

```arx
fn numeric_demo(a: int32, b: float32) -> f64:
  var count: i64 = 64
  return cast(a, f64) + cast(b, f64)
```

## `none`

`none` is the built-in unit type and also the single value of that type. Use it
for functions that do not return a meaningful result.

```arx
fn log_message() -> none:
  print("ok")
  return

fn done() -> none:
  return none

var marker: none = none
```

For `-> none` functions:

- the return type annotation is still mandatory
- bare `return` returns `none`
- reaching the end of the function also implicitly returns `none`

## Text Types

Use `str` for strings and `char` for single-byte character values.

```arx
fn text_demo() -> none:
  var greeting: str = "hello"
  var initial: char = 'A'
  return none
```

`char` currently maps to `i8`, so it should be treated as a low-level character
representation rather than a separate rich text type.

## Temporal Types

Arx currently documents constructor-style surface syntax for `datetime` and
`timestamp` values.

```arx
fn time_demo() -> none:
  var dt: datetime = datetime("2026-03-05T12:30:59")
  var ts: timestamp = timestamp("2026-03-05T12:30:59.123456789")
  return none
```

The parser also recognizes `date` and `time` as built-in type names in
annotations.

## Arrays And Ndarrays

Use `array[T, N]` for shaped 1D arrays and `ndarray[T, d0, d1, ...]` for
multidimensional arrays.

```arx
fn array_demo() -> none:
  var ids: array[i32, 4] = [1, 2, 3, 4]
  var grid: ndarray[i32, 2, 2] = [[1, 2], [3, 4]]
  print(ids[2])
  print(grid[1, 0])
  return none
```

Current ndarray rules in this phase:

- shapes are declared in the type annotation
- literals must be rectangular and match the declared shape
- indexing uses one index per declared dimension
- current lowering is read-only and is focused on literal/default-initialized
  shaped arrays

`array[T]` remains available as the older list-style spelling, but the native
array/ndarray surface for shaped indexing uses `array[T, N]` and
`ndarray[T, ...]`.

## Casting

Use the built-in `cast(value, type)` helper to convert values between supported
types.

```arx
fn cast_demo(a: i32) -> str:
  return cast(a, str)
```

## See Also

- [Data Types](datatypes.md) for annotation rules and placement
- [Functions](functions.md) for function signatures and returns
