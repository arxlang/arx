# Class Model

IRx now has a first-class low-level class system designed for Arx to target
without turning IRx into a high-level object runtime.

## What Classes Add Beyond Structs

- `StructDefStmt` remains the ABI-oriented passive composite type
- `ClassDefStmt` adds inheritance, methods, access control, static members,
  abstract contracts, deterministic dispatch metadata, and deterministic
  construction/lowering
- class values lower as pointers to identified object structs with reserved
  header slots; struct values remain plain by-value composites unless another
  rule says otherwise

## Supported Modifiers

IRx currently supports these class-member modifiers:

- `public`
- `protected`
- `private`
- `static`
- `abstract`
- `constant`
- `mutable`

Current semantics:

- `public` is accessible wherever the containing class value is visible
- `protected` is accessible only inside the declaring class and subclasses
- `private` is accessible only inside the declaring class
- `static` members use class-qualified access and class-scoped global storage
- `abstract` classes cannot be constructed; abstract methods declare a required
  signature that concrete subclasses must implement
- `constant` members are immutable after initialization
- `mutable` members may be reassigned after initialization

## Abstract Classes And Methods

- pass `is_abstract=True` to `ClassDefStmt` to declare an abstract class
- mark a method prototype with `prototype.is_abstract = True` to declare an
  abstract method
- abstract methods must not declare executable bodies
- non-abstract classes must implement all visible inherited abstract methods
- abstract instance methods still reserve dispatch slots so base-typed calls can
  dispatch to concrete subclass implementations
- `ClassConstruct("Name")` rejects abstract classes during semantic analysis

## Inheritance And MRO

IRx supports multiple inheritance with deterministic C3 linearization.

- method lookup follows C3 MRO order
- ambiguous inherited attributes are rejected
- conflicting inherited methods with the same effective signature are rejected
  unless the subclass supplies a legal override
- shared diamond ancestors are stored once in the canonical flattened layout
- base-typed and explicit base-qualified field views use the concrete object
  descriptor, including non-prefix multiple-inheritance bases

## Layout And Dispatch

- every class object starts with lifetime-token, concrete-field-descriptor, and
  dispatch-table slots
- instance fields are flattened in canonical ancestor-first order
- static attributes lower to internal module globals
- instance methods lower to ordinary functions with a hidden receiver parameter
- non-private overridable instance methods use stable dispatch slots
- static methods lower to direct calls with no hidden receiver

## Static Members, Constants, And Mutability

- `StaticFieldAccess("Name", "field")` is the class-qualified read/write form
  for static attributes
- static mutable fields lower to `internal global` storage
- static constant fields lower to `internal constant` storage when possible
- constant instance, base-qualified, and static members reject assignment and
  unary mutation during semantic analysis
- static initialization remains literal/default-only in the current phase

## Access Control

- instance access uses `FieldAccess`
- class-qualified static access uses `StaticFieldAccess`
- explicit legal ancestor access uses `BaseFieldAccess` and `BaseMethodCall`
- access control is enforced during semantic analysis, never deferred to
  lowering or runtime

## ABI And Interop

- IRx-defined functions pass and return class values by pointer
- class methods and dispatch globals use deterministic internal symbol names
- class static storage uses deterministic internal global names
- general classes are **not** part of IRx's stable public foreign ABI yet
- foreign boundaries should still use structs, typed pointers, and opaque
  handles rather than `ClassType`

## Current Limitations

- `ClassConstruct("Name", args, keywords=...)` binds an optional `__init__`
  hook; `__del__` runs on final reference release, before reverse-order field
  cleanup
- lifecycle hooks are compiler entry points, not dispatchable ordinary methods
- IRx's immutable `CLASS_HOOKS` registry owns supported dunder names;
  `LIFECYCLE_HOOKS` selects compiler-only lifecycle signature/invocation rules
- existing `__enter__` and `__exit__` context protocols retain ordinary dispatch
  and call-site signature validation, not lifecycle restrictions
- unsupported dunder method names are rejected, and lifecycle names cannot be
  fields; plain `init` and `deinit` are ordinary methods
- lowering consumes the resolved `is_class_initializer` signature metadata,
  rather than interpreting source method names
- no stable foreign object ABI for general classes
- no callback/function-pointer class interop in the public FFI layer
- overload selection requires exact provided-argument matches after accounting
  for any trailing declared defaults; conversion-ranked method overloads remain
  deferred

## Examples

### Instance Field Plus Method

```python
read_body = astx.Block()
read_body.append(
    astx.FunctionReturn(
        astx.FieldAccess(astx.Identifier("self"), "value")
    )
)
counter = astx.ClassDefStmt(
    name="Counter",
    attributes=[
        astx.VariableDeclaration(name="value", type_=astx.Int32()),
    ],
    methods=[
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                name="read",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=read_body,
        )
    ],
)
```

### Base/Derived Override

```python
base_area_body = astx.Block()
base_area_body.append(astx.FunctionReturn(astx.LiteralInt32(1)))
child_area_body = astx.Block()
child_area_body.append(astx.FunctionReturn(astx.LiteralInt32(2)))
measure_body = astx.Block()
measure_body.append(
    astx.FunctionReturn(
        astx.MethodCall(astx.Identifier("shape"), "area", [])
    )
)
base = astx.ClassDefStmt(
    name="Base",
    methods=[
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                name="area",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=base_area_body,
        )
    ],
)
child = astx.ClassDefStmt(
    name="Child",
    bases=[astx.ClassType("Base")],
    methods=[
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                name="area",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=child_area_body,
        )
    ],
)
measure = astx.FunctionDef(
    prototype=astx.FunctionPrototype(
        name="measure",
        args=astx.Arguments(astx.Argument("shape", astx.ClassType("Base"))),
        return_type=astx.Int32(),
    ),
    body=measure_body,
)
```

### Multiple Inheritance

```python
root = astx.ClassDefStmt(
    name="Root",
    attributes=[astx.VariableDeclaration(name="root", type_=astx.Int32())],
)
left = astx.ClassDefStmt(
    name="Left",
    bases=[astx.ClassType("Root")],
    attributes=[astx.VariableDeclaration(name="left", type_=astx.Boolean())],
)
right = astx.ClassDefStmt(
    name="Right",
    bases=[astx.ClassType("Root")],
    attributes=[astx.VariableDeclaration(name="right", type_=astx.Float64())],
)
child = astx.ClassDefStmt(
    name="Child",
    bases=[astx.ClassType("Left"), astx.ClassType("Right")],
)
```

The effective MRO is `Child -> Left -> Right -> Root`, and the shared `Root`
subobject appears once in the flattened layout.

### Static Constant Example

```python
limit = astx.VariableDeclaration(
    name="limit",
    type_=astx.Int32(),
    mutability=astx.MutabilityKind.constant,
    scope=astx.ScopeKind.global_,
    value=astx.LiteralInt32(99),
)
limit.is_static = True
counter = astx.ClassDefStmt(
    name="Counter",
    attributes=[limit],
)
read_limit = astx.StaticFieldAccess("Counter", "limit")
```

For the normative lowering and semantic details, see
[`docs/semantic-contract.md`](./semantic-contract.md).

## Lifecycle And Ownership

Class layouts now begin with lifetime-token, concrete-field-descriptor, and
dispatch pointers. The descriptor keeps multiple-inheritance base field views
correct even when a base is not a prefix. `ClassLifecyclePhase` metadata orders
base-first field initialization and hooks, deduplicating diamonds. Destruction
reverses phases and fields through a concrete callback, including base-typed
references. The registered `class` native feature owns non-atomic reference
counts, zeroed allocation, and construction progress behind an opaque token.

Local references, independent parameter slots, retained aliases, expression
pins, and owned returns share identity. Owned string fields clone borrows or
move fresh results. File fields require exactly one fresh `open` initializer;
acyclic class fields retain references. Analysis rejects cycles through possible
subtypes, escaping lifecycle receivers, owned statics/globals, classes in
containers/unions/structs/generators, and unmodeled resource fields. Fatal user
calls do not gain cross-frame unwinding. See the
[Arx lifecycle rules](../arx/classes.md) for the exact constructor and cleanup
boundaries. General function/method keywords and a public `File` class remain
separate follow-ups.

## Native-Backed File Builtin

Public File uses this same ClassType/layout/reference lifecycle, not a renamed
opaque handle. Its host-registered native initializer checks creation in the
caller; its private FileType field is released by normal class drop. Public
references may alias and cross normal function boundaries. Native-backed method
metadata preserves call-site status checks and receiver pinning. Canonical File
subclassing is explicitly rejected in this slice. See the
[semantic contract](semantic-contract.md#native-backed-file-class).
