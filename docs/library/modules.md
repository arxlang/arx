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

## Package Layout

When a project uses the default `src/` source root, or declares
`[build].src_dir`, Arx treats files under that source root as package modules
addressed by dotted names.

Example project layout:

```text
.
├── .arxproject.toml
├── src
│   └── geometry
│       ├── __init__.x
│       ├── shared
│       │   └── math.x
│       └── shapes
│           ├── area.x
│           └── helpers.x
└── tests
    └── test_area.x
```

With the default `src/` source root:

- `src/geometry/__init__.x` is module `geometry`
- `src/geometry/shared/math.x` is module `geometry.shared.math`
- `src/geometry/shapes/area.x` is module `geometry.shapes.area`
- `src/geometry/shapes/helpers.x` is module `geometry.shapes.helpers`

Use `__init__.x` as the package root, following the same layout idea as Python
packages.

## Import Syntax

```arx
import geometry.shapes.area
import geometry.shapes.area as area

import circle_area from geometry.shapes.area
import circle_area as area_of_circle from geometry.shapes.area

import (circle_area, square_area) from geometry.shapes.area

import radius_to_diameter from .helpers
import (circle_area, square_area) from .area
import clamp from ..shared.math
```

Rules:

- Import statements are module-level statements.
- Grouped imports use parentheses.
- Grouped imports require `from`.
- Trailing commas are allowed in grouped imports.
- Empty grouped imports are invalid.
- Absolute module paths use dotted notation.
- Relative imports are supported only with `from` imports.
- Relative imports use one or more leading dots before the module path.
- Plain relative module imports such as `import .area` are not supported yet.
- Prefer `from` imports when you want callable declarations without a module
  qualifier.

### Absolute Imports

Use absolute dotted paths for public imports across package boundaries:

```arx
import circle_area from geometry.shapes.area
```

### Namespace Imports

Use a module alias when you want to keep names grouped under a module namespace:

````arx
```
title: Geometry namespace import
summary: Call one module member through a namespace alias.
```
import geometry.shapes.area as area

fn main() -> f64:
  ```
  title: main
  summary: Demonstrates namespace member access.
  ```
  return area.circle_area(10.0)
````

Direct symbol imports remain available when you prefer shorter local names:

```arx
import circle_area from geometry.shapes.area
```

### Relative Imports

Use relative `from` imports for package-internal references. For example, inside
`geometry.shapes.area`:

```arx
import radius_to_diameter from .helpers
import clamp from ..shared.math
```

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
