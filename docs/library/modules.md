# Modules

A module in Arx is a source file (for example, `math.x`) containing top-level
statements such as imports, function definitions, and extern declarations.

## Module Layout

````arx
```
title: Math module example
summary: Module with one documented function.
```
fn average(x: f32, y: f32) -> f32:
  ```
  title: average
  summary: Returns the arithmetic mean of x and y.
  ```
  return (x + y) * 0.5
````

## Import Syntax

```arx
import std.math
import std.math as math

import sin from std.math
import sin as sine from std.math

import (sin, cos, tan as tangent) from std.math

import (
  sin,
  cos,
  tan as tangent,
) from std.math
```

Rules:

- Import statements are module-level statements.
- Grouped imports use parentheses.
- Grouped imports require `from`.
- Trailing commas are allowed in grouped imports.
- Empty grouped imports are invalid.
- Module paths use dotted notation.

## Module Docstring

Arx supports module docstrings in Douki YAML format, delimited by triple
backticks:

````text
```
title: Module documentation
summary: Optional summary text
```
````

Current placement rule:

- The module docstring must be the **first top-level element** in the file.
- It must begin at **character 0 of line 1** (no leading spaces).

Valid:

````text
```
title: Module docs
```
fn main() -> i32:
  ```
  title: main
  summary: Entry point for the module.
  ```
  return 1
````

Invalid (leading indentation before module docstring):

````text
  ```
  title: Module docs
  ```
fn main() -> i32:
  ```
  title: main
  summary: Entry point for the module.
  ```
  return 1
````

For now, module docstrings are parsed and validated but ignored by AST/IR
generation.
