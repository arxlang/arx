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
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2],
    score: [0.5, 1.0],
  })
  var count: i32 = 0
  print(grid[0, 1])
  print(rows.nrows())
  return
```

Common places where types appear:

- function parameters: `fn add(a: i32, b: i32) -> i32:`
- union function parameters: `fn id(value: i32 | i64) -> i32 | i64:`
- function return types: `fn test_add() -> none:`
- variable declarations: `var total: i32 = 0`
- type aliases: `type Number = i32 | i64`
- generic collection annotations: `list[i32]`
- shaped 1D tensor annotations: `tensor[i32, 4]`
- multidimensional tensor annotations: `tensor[i32, 2, 2]`
- runtime-shaped tensor parameters: `fn sink(x: tensor[i32, ...]) -> none:`
- static-schema DataFrame annotations: `dataframe[id: i32, score: f64]`
- runtime-schema DataFrame parameters: `fn sink(rows: dataframe[...]) -> none:`
- typed DataFrame column annotations: `series[f64]`

`tensor[T, ...]` is currently parameter-only. Use fixed-shape tensor annotations
for variables, fields, and return types until runtime-shaped storage and return
semantics are defined. Runtime-shaped tensor parameters can be passed through,
but indexed access currently requires a static-shape tensor annotation.

`dataframe[...]` follows the same current restriction: it is accepted only in
function and extern parameter annotations. Static-schema DataFrames can be
constructed with `dataframe({...})`, and their columns can be accessed with
either `rows.score` or `rows["score"]`.

## Type Aliases And Union Types

Type aliases are top-level declarations. The `type` word is contextual, so
`type Name = ...` declares an alias while `type(value)` calls the builtin
type-name helper.

````arx
```
title: Type alias example
summary: Demonstrates a finite numeric union alias.
```
type Number = i32 | i64

fn identity(value: Number) -> Number:
  ```
  title: identity
  summary: Returns a numeric union value.
  ```
  return value
````

Union annotations use `|`. Numeric unions currently lower through a shared
numeric storage type. Runtime tagged unions and runtime narrowing are not part
of the current model.

## Built-in Type Reference

For the catalog of built-in types, aliases, and examples, see
[Built-in Types](built-in-types.md).

That page covers:

- numeric types and aliases
- `none` as the unit type and value
- string, character, and temporal types
- lists, tensors, dataframes, series, and current limitations
- the `cast(value, type)` helper
- the `isinstance(value, type)` and `type(value)` helpers
