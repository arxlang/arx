# Data Types

Arx uses explicit type annotations for variables, function parameters, and
function return types.

## Type Annotations

- Function parameters must always be typed.
- Function return type is declared with `-> type`. When omitted, the return type
  defaults to `void`.
- Variable declarations must include an explicit type with `var name: type`.

````arx
```
title: Typed function signature
summary: Demonstrates required parameter annotations.
```
fn add(a: i32, b: i32) -> i32:
  ```
  title: add
  summary: Returns a + b.
  ```
  return a + b
````

## Built-in Types

| Type        | Meaning                    | Example               |
| ----------- | -------------------------- | --------------------- |
| `i8`        | 8-bit integer              | `var a: i8 = 8`       |
| `i16`       | 16-bit integer             | `var b: i16 = 16`     |
| `i32`       | 32-bit integer             | `var c: i32 = 32`     |
| `i64`       | 64-bit integer             | `var d: i64 = 64`     |
| `f16`       | 16-bit float               | `var x: f16 = 1.5`    |
| `f32`       | 32-bit float               | `var y: f32 = 3.25`   |
| `bool`      | Boolean                    | `var ok: bool = true` |
| `void`      | No value                   | `var n: void = void`  |
| `str`       | String                     | `var s: str = "hi"`   |
| `char`      | Character (mapped to `i8`) | `var ch: char = 'A'`  |
| `datetime`  | Date/time literal          | `datetime("...")`     |
| `timestamp` | Timestamp literal          | `timestamp("...")`    |
| `list[T]`   | List type                  | `list[i32]`           |

## Strings And Characters

````arx
```
title: String and char types
summary: Declares string and char variables.
```
fn text_demo() -> void:
  ```
  title: text_demo
  summary: Uses string and char literals.
  ```
  var greeting: str = "hello"
  var initial: char = 'A'
  return void
````

## Date And Time Literals

````arx
```
title: Datetime and timestamp literals
summary: Creates date/time values from string literals.
```
fn time_demo() -> void:
  ```
  title: time_demo
  summary: Demonstrates datetime/timestamp constructors.
  ```
  var dt: datetime = datetime("2026-03-05T12:30:59")
  var ts: timestamp = timestamp("2026-03-05T12:30:59.123456789")
  return void
````

## Lists

````arx
```
title: List type example
summary: Declares list variables.
```
fn list_demo() -> void:
  ```
  title: list_demo
  summary: Declares populated and empty lists.
  ```
  var ids: list[i32] = [1, 2, 3, 4]
  var empty_ids: list[i32] = []
  return void
````

Current limitation: list code generation is still limited to empty or
homogeneous integer constant lists.

## Casting

Use the built-in `cast(value, type)` to convert values:

````arx
```
title: Casting example
summary: Converts between numeric and string-compatible forms.
```
fn cast_demo(a: i32) -> str:
  ```
  title: cast_demo
  summary: Returns string representation of an integer.
  ```
  return cast(a, str)
````
