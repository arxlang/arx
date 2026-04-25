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

## Default Parameter Values

Function, method, and extern parameters can declare trailing default values with
`=`. Calls may omit those trailing arguments.

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

````arx
```
title: Extern prototype example
summary: Declares an external function signature.
```
extern putchard(x: i32) -> i32
````
