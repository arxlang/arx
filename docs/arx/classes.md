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
An optional `__init__` hook adds positional arguments, constructor keywords, and
literal defaults; an optional `__del__` hook runs at final release.

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

  fn __init__(self, value: i32 = 1) -> none:
    self.value = value
    return none

  fn __del__(self) -> none:
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
references on ordinary lexical exits. Final release calls `__del__` exactly
once, then drops owned fields and frees storage. Returns preserve object
identity and can outlive the creating function. Calls borrow objects; evaluated
class arguments and receivers are pinned before later arguments can replace
fields. Rebinding a class parameter replaces its independent local reference,
not the caller's binding.

Hook rules:

- Double-underscore (dunder) method names are reserved for language protocols.
  The supported lifecycle names are `__init__` and `__del__`; unknown names such
  as `__inti__` or `__str__` are semantic errors, including on static methods.
  Lifecycle hooks cannot be declared as fields. Plain `init` and `deinit` are
  ordinary method names, not compatibility aliases. Existing IRx `__enter__` and
  `__exit__` context protocols remain recognized and callable, but do not enable
  Arx `with` syntax.
- Dunders identify language-defined behavior, not private visibility or
  inheritance from a universal builtin superclass. Implementations are written
  by users; normal visibility annotations still apply.
- `__init__(self, ...) -> none` and `__del__(self) -> none` are compiler entry
  points, not ordinary callable methods. Explicit calls are rejected.
- Hooks cannot be static, abstract, external, overloaded, templated, or
  variadic. Constructor defaults are existing scalar/string literals, not
  resource values.
- Constructor arguments bind by parameter name, excluding `self`. Unknown,
  duplicate, missing, excessive, and incompatible arguments are errors. Supplied
  expressions evaluate once in source order, including keywords.
- A class without its own `__init__` has a zero-argument constructor. Base hooks
  run with their defaults; a base requiring arguments is rejected when
  constructing the derived class. Explicit base-argument forwarding is deferred.
- Shared ancestors initialize once in canonical base-first storage order. Each
  phase initializes its declared fields before calling its own `__init__`. Final
  release reverses those phases, calling each `__del__` before dropping its
  fields in reverse declaration order. This also works through a base-typed
  reference; non-prefix multiple-inheritance views locate concrete storage.
- Inside hooks, `self` is only a field-access receiver: it cannot be aliased,
  returned, passed elsewhere, or used to invoke an ordinary self method. This
  prevents escape during construction and resurrection during destruction.

These names are familiar from Python, but Arx keeps its own lifecycle contract:
normal final-reference release synchronously runs cleanup, base phases chain
automatically, and direct hook calls and resurrection are forbidden. This does
not add Python's garbage collector, `super()` chaining, `__new__`, or unwinding
after fatal errors. Ordinary operations such as `close()` remain callable and
are separate from object destruction.

Ordinary instance and static methods also accept named arguments. An instance
receiver is implicit; it cannot be supplied as a keyword. Keywords bind against
the statically selected declaration, including through inheritance and dynamic
dispatch. Values evaluate in source order, then omitted defaults in declaration
order. See [Functions](functions.md#keyword-arguments). Direct lifecycle-hook
calls remain forbidden.

## Owned Fields And Boundaries

Scalar fields keep their existing behavior. Instance strings own independent
heap copies (or move fresh owned results); replacing a string field safely
releases its previous allocation. String-field reads produce owned snapshots, so
evaluated arguments, local copies, and returns survive later replacement of that
field. Acyclic class-reference fields hold strong references and default to
empty; dereferencing an empty class value reports a checked runtime error rather
than using a null pointer. Field declarations may refer to already initialized
fields through `self`.

A public `File` (or lowercase `file`) field holds an ordinary class reference.
It may be initialized with `File(...)`, `open(...)`, or another File reference,
and may be replaced or shared. Empty fields use the normal checked class
reference behavior. The builtin File class itself owns one private native handle
initialized once by its compiler-provided constructor; users cannot extract or
replace that handle. Final File release invokes normal owned-field cleanup. See
the
[owned-file example](https://github.com/arxlang/arx/blob/main/examples/class-lifecycle.x)
and [file API](file-io.md). File subclassing and reopening are deferred.

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

A runtime-schema `dataframe[...]` method parameter also accepts a statically
typed DataFrame, without converting its data. An exact static-schema overload
wins if present. This permits `CSVStream.write(frame)` and
`ParquetStream.write(frame)` for both kinds of frame; it does not permit
implicit narrowing or general numeric conversion-ranked overloads.
