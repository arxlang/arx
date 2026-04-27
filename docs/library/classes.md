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

  @[protected]
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

Template methods use the same `@<...>` prefix form as module functions. Method
modifiers and template parameters may appear in either order as long as each
prefix stays on its own line above the method declaration:

```arx
class Math:
  @<T: i32 | f64>
  @[public, static]
  fn identity(value: T) -> T:
    return value
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
- Declaration metadata: `abstract`, `extern`

Not supported yet:

- `override`, `virtual`, `final`, `sealed`, `readonly`, `inline`

## Defaults

Defaults are applied during parsing and normalization, not written back as
implicit annotation lines.

- Fields default to `public` visibility and `mutable` mutability.
- Methods default to `public` visibility.
- Only explicitly written modifiers are preserved as explicit metadata on the
  emitted IRx/ASTx nodes.

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

## Construction And Typed Class Values

Declared classes can also be used directly in type annotations and default
construction expressions. Construction is currently default-only, so `Counter()`
does not accept constructor arguments yet.

```arx
class Counter:
  @[public, static, constant]
  version: int32 = 3

  fn get(self) -> int32:
    return 1

class CounterFactory:
  @[public, static]
  fn make() -> Counter:
    return Counter()

fn take_counter(counter: Counter) -> int32:
  return counter.get()

fn main() -> int32:
  var counter: Counter = CounterFactory.make()
  return take_counter(counter) + Counter.version
```

This surface syntax maps directly onto IRx-owned class nodes:

- `Counter` in annotations becomes `astx.ClassType`
- `Counter()` becomes `astx.ClassConstruct`
- `Counter.version` becomes `astx.StaticFieldAccess`
- `CounterFactory.make()` becomes `astx.StaticMethodCall`

## IRx Alignment

Arx now emits IRx/ASTx nodes directly instead of maintaining a separate Arx
class AST layer. This is a hard repository boundary: new AST node types or new
lowering behavior for class features belong in IRx/ASTx, not in Arx.

- `class` declarations lower into `astx.ClassDefStmt`.
- Base classes become `astx.ClassType` entries.
- Fields become `astx.VariableDeclaration` with visibility and mutability set
  directly, plus `is_static` when present.
- Methods become `astx.FunctionDef` plus `astx.FunctionPrototype`, with
  visibility set directly and `is_static`, `is_abstract`, or `is_extern`
  attached to the prototype when written.
- Instance member syntax like `self.value` lowers into `astx.FieldAccess`.

This keeps Arx syntax aligned with the IRx semantic boundary while preserving
explicit modifier intent on the same nodes that later lowering consumes.
