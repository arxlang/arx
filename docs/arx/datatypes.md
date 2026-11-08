# Data Types

Arx is statically typed. Function parameters and return types use explicit
annotations. Variables may select a type explicitly or request initializer-based
inference with `auto`.

## Type Annotations

- Function parameters must always be typed.
- Function return type is declared with `-> type` and is always required,
  including `-> none`.
- An explicit annotation selects a type: `count: i32 = 1`.
- `count: auto = 1` infers a concrete, fixed type from its required initializer.
  `auto` is an inference marker, not a dynamic type, and is not allowed in
  function signatures. See [declarations](syntax.md#declarations-and-modifiers)
  for supported inference contexts.
- Binding mutability is independent of the selected or inferred type:
  `count: var :: i32 = 1` permits rebinding; `limit: const :: auto = 10` does
  not. Omitting the modifier means `var`; `const` does not freeze referenced
  objects.
- `auto` remains contextual for value identifiers, but cannot name a class, type
  alias, or template parameter.

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
lossless numeric storage type; incompatible runtime unions are rejected. Generic
union bounds constrain template membership without allocating union storage.
Runtime tagged unions and runtime narrowing are not part of the current model.

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
