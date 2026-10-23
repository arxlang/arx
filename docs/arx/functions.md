# Functions

Functions are defined with `fn`, a name, parameters in `()`, and a body after
`:` with indentation.

## Definition Syntax

````arx
```
title: Function definition
summary: Shows the structure of a function declaration.
```
fn add(x: i32, y: i32) -> i32:
  ```
  title: add
  summary: Returns x plus y.
  ```
  return x + y
````

## Calling Functions

````arx
```
title: Function call example
summary: Defines a helper function and calls it from main.
```
fn double(v: i32) -> i32:
  ```
  title: double
  summary: Returns v multiplied by two.
  ```
  return v * 2

fn main() -> i32:
  ```
  title: main
  summary: Calls double with a constant input.
  ```
  return double(10)
````

## Keyword Arguments

Ordinary functions and instance/static methods accept named arguments, including
through imported aliases and module namespaces:

```text
add(y=2, x=1)
add(1, y=2)
helpers.add(x=1, y=2)
counter.read(offset=3)
identity<i32>(value=7)
```

Positional arguments must precede keywords. Names are case-sensitive and must
match the resolved declaration. Existing ordinary function-call lookup remains
module-visible and separate from lexical local-value lookup; builtin/class
shadowing rules are unchanged. Duplicate names, positional/name collisions,
unknown names, and missing required parameters are compilation errors. A named
call may end with a trailing comma. Unpacking (`*args`, `**kwargs`) and
keyword-only/positional-only parameter declarations are not supported.

The receiver is evaluated first, then all explicitly supplied values exactly
once in source order, even when their names reverse parameter order. Omitted
defaults run afterward in parameter declaration order. Unlike Python, Arx
already evaluates defaults at **call time**; they may reference earlier bound
parameters, and method defaults may read `self`. For `f(a, b=a+1, c=b+1)`,
`f(c=9, a=2)` calls with `(2, 3, 9)` and does not evaluate `c`'s default.
Dynamic methods bind names/defaults through the statically selected interface,
then dispatch positional values to the override.

Fixed extern parameter names can be used; any existing C variadic tail stays
positional and uses existing promotions. Keywords do not enable unsupported FFI
types. Parser intrinsics and collection operations without a named-call schema
still reject keywords. Signature-backed bundled functions such as
`range(start=0, stop=3)` use their declared parameters, not Python overloads.

## Default Parameter Values

Function, method, and extern parameters can declare trailing default values with
`=`. Calls may omit defaulted parameters, including a middle default when a
later parameter is supplied by name.

````arx
```
title: Default argument example
summary: Calls a helper using an optional offset.
```
fn add_offset(value: i32, offset: i32 = 1) -> i32:
  ```
  title: add_offset
  summary: Adds an optional offset to value.
  ```
  return value + offset

fn main() -> i32:
  ```
  title: main
  summary: Uses the declared default offset.
  ```
  return add_offset(4)
````

## Template Functions

Function templates use an `@<...>` block on the line immediately before `fn`.
Each template parameter must declare a bound, and bounds may be a single type or
a `|` union of concrete types. Explicit template arguments are written between
the callee name and `(`.

````arx
```
title: Template function example
summary: Uses one bounded template parameter with inferred and explicit calls.
```
@<T: i32 | f64>
fn add(x: T, y: T) -> T:
  ```
  title: add
  summary: Adds two values that share one template-bound type.
  ```
  return x + y

fn main() -> i32:
  ```
  title: main
  summary: Calls template specializations through inference and explicit args.
  ```
  print(add(1, 2))
  print(add<f64>(1.5, 2.5))
  return 0
````

## Function Body Rules

- The block starts after `:`.
- The next line must be indented.
- A function docstring (if present) must be the first element in the function
  block.
- Function docstrings must use Douki YAML and include at least `title`.

Example:

````arx
```
title: Function docstring placement
summary: Function docstring appears as the first body element.
```
fn add(x: i32, y: i32) -> i32:
  ```
  title: Add two numbers
  summary: Returns x + y.
  ```
  return x + y
````

## Extern Prototypes

Arx also supports external function declarations:

[Native package metadata](native-packages.md) can supply build/link requirements
for resolved extern declarations. Calls retain normal parameter/keyword binding;
the compiler does not infer a native dependency from a function's name.

````arx
```
title: Extern prototype example
summary: Declares an external function signature.
```
extern putchard(x: i32) -> i32
````

## Native file construction

[`File` and `open`](file-io.md) share checked construction and return ordinary
File references. Their restricted native settings are not arbitrary Python
keyword forwarding. [Class constructors](classes.md) bind keywords through
`__init__`; ordinary function/method binding follows the rules above.
