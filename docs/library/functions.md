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

fn main():
  ```
  title: main
  summary: Calls double with a constant input.
  ```
  return double(10)
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
