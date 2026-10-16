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

Declared classes can be used in type annotations and construction expressions.
`Counter()` remains valid when no required initializer parameters are declared.
An optional `init` hook adds positional arguments, constructor keywords, and
literal defaults; an optional `deinit` hook runs at final release.

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
- `Counter(...)` becomes `astx.ClassConstruct` with ordered arguments/keywords
- `Counter.version` becomes `astx.StaticFieldAccess`
- `CounterFactory.make()` becomes `astx.StaticMethodCall`

## Lifecycle Hooks

```arx
class Counter:
  value: i32 = 0

  fn init(self, value: i32 = 1) -> none:
    self.value = value
    return none

  fn deinit(self) -> none:
    print(self.value)
    return none

fn main() -> i32:
  var counter: Counter = Counter(value=7)
  var alias: Counter = counter
  counter = Counter(3)
  assert alias.value == 7
  return 0
```

The two variables initially refer to the same object; copying a reference does
not copy fields. Reassignment releases only the replaced reference. Locals,
discarded temporaries, loop-body locals, and early returns release their
references on ordinary lexical exits. Final release calls `deinit` exactly once,
then drops owned fields and frees storage. Returns preserve object identity and
can outlive the creating function. Calls borrow objects; evaluated class
arguments and receivers are pinned before later arguments can replace fields.
Rebinding a class parameter replaces its independent local reference, not the
caller's binding.

Hook rules:

- `init(self, ...) -> none` and `deinit(self) -> none` are compiler entry
  points, not ordinary callable methods. Explicit calls are rejected.
- Hooks cannot be static, abstract, external, overloaded, templated, or
  variadic. Constructor defaults are existing scalar/string literals, not
  resource values.
- Constructor arguments bind by parameter name, excluding `self`. Unknown,
  duplicate, missing, excessive, and incompatible arguments are errors. Supplied
  expressions evaluate once in source order, including keywords.
- A class without its own `init` has a zero-argument constructor. Base hooks run
  with their defaults; a base requiring arguments is rejected when constructing
  the derived class. Explicit base-argument forwarding is deferred.
- Shared ancestors initialize once in canonical base-first storage order. Each
  phase initializes its declared fields before calling its own `init`. Final
  release reverses those phases, calling each `deinit` before dropping its
  fields in reverse declaration order. This also works through a base-typed
  reference; non-prefix multiple-inheritance views locate concrete storage.
- Inside hooks, `self` is only a field-access receiver: it cannot be aliased,
  returned, passed elsewhere, or used to invoke an ordinary self method. This
  prevents escape during construction and resurrection during destruction.

Only constructors and builtin `open` accept keyword calls in this PR. **General
function/method keyword calls are the next PR**, not implemented here.

## Owned Fields And Boundaries

Scalar fields keep their existing behavior. Instance strings own independent
heap copies (or move fresh owned results); replacing a string field safely
releases its previous allocation. String-field reads produce owned snapshots, so
evaluated arguments, local copies, and returns survive later replacement of that
field. Acyclic class-reference fields hold strong references and default to
empty; dereferencing an empty class value reports a checked runtime error rather
than using a null pointer. Field declarations may refer to already initialized
fields through `self`.

A `file` field must be initialized exactly once with a fresh `open(...)`, either
in its declaration or directly in its declaring class's `init`. Analysis checks
every normal constructor exit, rejects reads before initialization, and rejects
replacement, copies, extraction, and initialization hidden in loops. Ordinary
file methods, including idempotent `close()`, remain available. Final class
release automatically releases the native file wrapper. See the complete
[owned-file example](../../examples/class-lifecycle.x) and
[file API](file-io.md). There is no new public `File` class yet.

This reference-counted subset is synchronous and non-atomic. Cyclic field-type
graphs are rejected conservatively, including edges through assignable subtypes,
even if a particular program would not create a cycle. Class values in
containers/unions/struct fields, owned globals/statics, generator capture,
list/Arrow/resource aggregate fields, and an external class ownership ABI are
not supported. There is no garbage collector, weak reference, resurrection,
explicit deletion, or thread-safe reference counting.

Allocation and empty-reference failures use `ARX-RUNTIME-CLASS-001`. Checked
compiler-local construction failures release initialized fields, run only
completed base-phase destructors, and free partial storage. Native field-release
errors preserve the first error while continuing remaining field releases and
freeing the object. Fatal errors inside called user code still exit without
unwinding caller frames; this is not catchable exception support.

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
