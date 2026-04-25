# Data Types

Arx uses explicit type annotations for variables, function parameters, and
function return types.

## Type Annotations

- Function parameters must always be typed.
- Function return type is declared with `-> type` and is always required,
  including `-> none`.
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

## Common Annotation Forms

```arx
fn summarize(name: str, values: list[i32]) -> none:
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  var count: i32 = 0
  print(grid[0, 1])
  return
```

Common places where types appear:

- function parameters: `fn add(a: i32, b: i32) -> i32:`
- function return types: `fn test_add() -> none:`
- variable declarations: `var total: i32 = 0`
- generic collection annotations: `list[i32]`
- unsized tensor annotations: `tensor[i32]`
- shaped tensor annotations: `tensor[i32, 4]`
- multidimensional tensor annotations: `tensor[i32, 2, 2]`

## Built-in Type Reference

For the catalog of built-in types, aliases, and examples, see
[Built-in Types](built-in-types.md).

That page covers:

- numeric types and aliases
- `none` as the unit type and value
- string, character, and temporal types
- lists, tensors, and current limitations
- the `cast(value, type)` helper
