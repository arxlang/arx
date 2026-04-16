# Classes

Arx class declarations use annotation lines for modifiers. Declaration lines
stay minimal: a field starts with its name, and a method starts with `fn`.

## Class Syntax

```arx
class Counter(BaseCounter, Audited):
  @[public, static, constant]
  version: int32 = 1

  value: int32 = 0

  @[private]
  internal: int32 = 1

  fn get(self) -> int32:
    return self.value

  @[protected, override]
  fn process(self, x: int32) -> int32:
    return x + 1
```

Optional class-level annotations use the same surface form:

```arx
@[public, abstract]
class Shape:
  @[public, abstract]
  fn area(self) -> float64
```

## Annotation Rules

- Modifiers must be written as `@[...]` on the line immediately above the target
  declaration.
- Modifiers never appear before the declaration name or before `fn`.
- Annotation lists are comma-separated and must not be empty.
- An annotation must be followed by exactly one declaration. Floating
  annotations are rejected.

Supported modifiers:

- Visibility: `public`, `private`, `protected`
- Storage and mutability: `static`, `constant`, `mutable`
- Dispatch and inheritance: `override`, `abstract`, `virtual`, `final`
- Parse-and-preserve only: `inline`, `extern`, `sealed`, `readonly`

## Defaults

Defaults are applied during validation or semantic normalization, not injected
into the parsed AST.

- Fields default to `public` visibility and `mutable` mutability.
- Methods default to `public` visibility.
- Only explicitly written modifiers are preserved in the surface AST.

For example, these declarations are equivalent semantically:

```arx
value: int32 = 0

fn get(self) -> int32:
  return self.value
```

```arx
@[public, mutable]
value: int32 = 0

@[public]
fn get(self) -> int32:
  return self.value
```

## IRx Alignment

The surface AST preserves explicit modifier metadata structurally so a later
lowering pass can map it directly onto IRx class members without re-reading raw
syntax.

- `public` / `private` / `protected` map directly to IRx visibility.
- `static` maps directly to class-static storage or dispatch.
- `constant` and `mutable` map directly to IRx mutability.
- `override` stays explicit for later override metadata and dispatch checks.
- Base-class lists preserve declaration order so later semantic analysis can
  apply IRx's class linearization rules.
