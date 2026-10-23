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

## Collection annotations

Runtime-shaped `tensor[T, ...]` remains parameter-only; indexed access requires
a fixed shape. Runtime-schema `dataframe[...]` supports locals, aliases,
parameters, and returns, but not unchecked named-column access. These are
different restrictions. See [collections](collections.md) for storage,
construction, exact schema casts, and nullable operations.

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

## Choosing a type

See [Built-in Types](built-in-types.md) for scalar choices and conversion
boundaries. The lexical manifest owns accepted spellings; it is not an API
support promise.

## Class References

Declared class names denote identity-preserving, reference-managed object
pointers. Local copies and owned returns keep objects alive; final release runs
`__del__` and drops owned fields. Acyclic instance class/string/file fields are
supported, but class values in containers/unions/structs, globals/statics, and
generators are rejected. See [Classes](classes.md) for construction and lifetime
rules; there is no general external ownership ABI.
