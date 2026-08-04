# Getting Started

This guide installs the Arx compiler, explains the required native toolchain,
and walks through source inspection, native compilation, Arrow-backed
collections, packages, and tests.

## Requirements

- Python 3.10 or newer
- `pip` for a published installation, or Mamba/Conda plus Poetry for a source
  checkout
- LLVM/Clang-compatible tools for object and executable generation
- a C++ compiler for native Apache Arrow runtime features

Token, AST, and most LLVM-translation workflows do not invoke the system linker.
Building or running an executable does.

## Install from PyPI

```bash
pip install arxlang
arx --version
```

The `arxlang` distribution installs the `arx` Python package and `arx` command.
Its IRx dependency installs PyArrow and Arrow C++ source metadata used when
Arrow-backed runtime features are compiled.

## Install a development checkout

```bash
git clone https://github.com/arxlang/arx.git
cd arx
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

The root environment installs all six workspace packages as editable path
dependencies: Arx, ASTx, IRx, PyArx, AIX, and ArxJIT.

## Your first program

Create `hello.x`:

````arx
```
title: Hello module
summary: Compiles a small typed Arx program.
```

fn add(a: i32, b: i32) -> i32:
  ```
  title: add
  summary: Adds two values.
  ```
  return a + b

fn main() -> i32:
  ```
  title: main
  summary: Prints one result and returns success.
  ```
  print(add(20, 22))
  return 0
````

Inspect each compiler stage:

```bash
arx --show-tokens hello.x
arx --show-ast hello.x
arx --show-llvm-ir hello.x
```

Build and run:

```bash
arx hello.x --output-file hello
./hello

# Equivalent one-step forms
arx --run hello.x
arx run hello.x
```

An Arx executable entry point should normally be `main() -> i32` and return `0`
on success. A single `main(n: i32)` parameter follows the native C `main` ABI
and receives `argc`, not a parsed command-line number.

## Native Arrow-backed values

Arx's public `tensor`, `dataframe`, and `series` abstractions lower into IRx's
native Apache Arrow C++ runtime:

````arx
```
title: Arrow-backed collections
summary: Uses a Tensor, DataFrame, and Series.
```

fn main() -> i32:
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  var scores: series[f64] = rows.score
  return cast(rows.nrows(), i32)
````

Use the committed examples for smoke testing:

```bash
arx --run examples/tensor.x
arx --run examples/dataframe.x
```

See [Collections and Arrow](library/collections.md) for the language rules and
[Native Apache Arrow Support](apache-arrow.md) for the runtime architecture.

## CLI overview

```text
arx [input_files ...] [options]
arx run [input_files ...] [options]
arx test [paths ...] [options]
```

| Option               | Purpose                                                  |
| -------------------- | -------------------------------------------------------- |
| `--show-tokens`      | Print lexer output                                       |
| `--show-ast`         | Print ASTx output                                        |
| `--show-llvm-ir`     | Print generated LLVM IR                                  |
| `--output-file PATH` | Select the object or executable path                     |
| `--lib`              | Emit a library/object artifact rather than an executable |
| `--run`              | Build and run an executable                              |
| `--link-mode MODE`   | Use `auto`, `pie`, or `no-pie` linking                   |
| `--version`          | Print the installed version                              |
| `--shell`            | Reserved; the interactive shell is not implemented       |

## Projects and packages

Arx reads optional project settings from `.arxproject.toml`. A conventional
source tree looks like this:

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

Example manifest:

```toml
[project]
name = "geometry"
version = "0.1.0"
requires-arx = ">=1.0,<2"
dependencies = [
  "sciarx>=0.0.3,<1",
]

[environment]
kind = "conda"
name = "geometry"

[build-system]
dependencies = [
  "arxlang>=1.0,<2",
]

[build]
src_dir = "src"
out_dir = "build"
package = "geometry"
```

`requires-arx` uses standard version-specifier syntax. Project dependencies use
standard requirement strings and may also be direct references. Arx resolves
local project modules before installed Arx packages and never performs network
installation during import resolution.

## Imports

```arx
import geometry.shapes.area
import geometry.shapes.area as area
import circle_area from geometry.shapes.area
import circle_area as area_of_circle from geometry.shapes.area
import (circle_area, square_area) from geometry.shapes.area
import helper from .helpers
import clamp from ..shared.math
```

Relative imports require the `from` form. Plain `import .area` is not supported.
The compiler reserves `stdlib` for bundled pure-Arx modules and `builtins` for
compiler-injected source modules.

```arx
import math from stdlib

fn main() -> i32:
  return math.square(4)
```

## Compiled tests

The test runner discovers `test_*.x` files and zero-argument `test_*` functions
returning `none`:

````arx
```
title: Math tests
summary: Uses fatal assertions in compiled tests.
```

import math from stdlib

fn test_square() -> none:
  assert math.square(3) == 9

fn test_clamp() -> none:
  assert math.clamp(0 - 3, 0, 2) == 0, "lower bound"
````

```bash
arx test
arx test tests/test_math.x --list
arx test -k square
arx test -x
arx test --keep-artifacts
```

Customize discovery in `.arxproject.toml`:

```toml
[tests]
paths = ["tests", "integration"]
exclude = ["tests/experimental_*.x"]
file_pattern = "test_*.x"
function_pattern = "test_*"
```

CLI flags take precedence over project settings. Each selected test runs in its
own compiled subprocess, and assertion failures use IRx's machine-readable
runtime protocol.

## Link-mode troubleshooting

If a linker defaults to PIE but rejects an object relocation, try:

```bash
arx hello.x --link-mode no-pie
```

IRx emits PIC-compatible objects by default, so this option is mainly a
toolchain compatibility fallback.

## Next steps

- [Language reference](library/index.md)
- [Lexical syntax specification](syntax.md)
- [Ecosystem status](ecosystem.md)
- [Roadmap](roadmap.md)
- [Contributing](contributing.md)
