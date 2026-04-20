# Getting Started

This guide walks you through installing Arx and compiling your first program.

## Prerequisites

- [Conda](https://docs.conda.io/en/latest/) or
  [Mamba](https://mamba.readthedocs.io/) package manager
- [Poetry](https://python-poetry.org/) (installed via conda)

## Installation

1. Clone the repository:

```bash
git clone https://github.com/arxlang/arx.git
cd arx
```

2. Create the conda environment and install dependencies:

```bash
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

3. Verify the installation:

```bash
arx --version
```

## Your First Program

Create a file called `hello.x`:

````arx
```
title: Hello example
summary: Minimal Arx program that adds two values.
```
fn sum(a: i32, b: i32) -> i32:
  ```
  title: sum
  summary: Returns the sum of a and b.
  ```
  return a + b
````

### View the tokens

```bash
arx --show-tokens hello.x
```

### View the AST

```bash
arx --show-ast hello.x
```

### View the LLVM IR

```bash
arx --show-llvm-ir hello.x
```

### Compile to an object file

```bash
arx hello.x --output-file hello
```

### Control executable link mode

```bash
arx examples/print-star.x --link-mode auto
arx examples/print-star.x --link-mode pie
arx examples/print-star.x --link-mode no-pie
```

## Examples

The `examples/` directory contains several sample programs:

### Sum

````arx
```
title: Sum example
summary: Demonstrates a basic addition function.
```
fn sum(a: i32, b: i32) -> i32:
  ```
  title: sum
  summary: Returns the sum of two values.
  ```
  return a + b;
````

### Average

````arx
```
title: Average example
summary: Demonstrates a basic arithmetic average function.
```
fn average(x: f32, y: f32) -> f32:
  ```
  title: average
  summary: Returns the arithmetic mean of x and y.
  ```
  return (x + y) * 0.5;
````

### Fibonacci

````arx
```
title: Fibonacci example
summary: Computes Fibonacci numbers recursively.
```
fn fib(x: i32) -> i32:
  ```
  title: fib
  summary: Returns the Fibonacci number for the input index.
  ```
  if x < 3:
    return 1
  else:
    return fib(x-1)+fib(x-2)
````

### Constant

````arx
```
title: Constant example
summary: Demonstrates a function that returns its argument unchanged.
```
fn get_constant(x: i32) -> i32:
  ```
  title: get_constant
  summary: Returns the provided value.
  ```
  return x;
````

### Template Functions

````arx
```
title: Template example
summary: Demonstrates compile-time specialization with inferred and explicit calls.
```
@<T: i32 | f64>
fn add(x: T, y: T) -> T:
  ```
  title: add
  summary: Adds two values with the same template-bound type.
  ```
  return x + y

fn main() -> i32:
  ```
  title: main
  summary: Calls both inferred and explicit template specializations.
  ```
  print(add(1, 2))
  print(add<f64>(1.5, 2.5))
  return 0
````

### Print Star

````arx
```
title: Print star example
summary: Emits star characters using an external output function.
```
fn print_star(n: i32) -> none:
  ```
  title: print_star
  summary: Prints stars in a loop by calling putchard.
  ```
  for i in (0:n:1):
    putchard(42);  # ascii 42 = '*'
  return none

fn main() -> i32:
  ```
  title: main
  summary: Runs the print_star demo with a fixed size and exits with status 0.
  ```
  print_star(10)
  return 0
````

Note: Arx entrypoint parameters currently follow the native C `main` ABI. A
single `main(n: i32)` receives `argc`, not the numeric value from `argv[1]`.
When using `--run`, prefer `main() -> i32` and `return 0` for a stable success
exit code.

You can compile any example with:

```bash
arx examples/sum.x --show-llvm-ir
```

Or compile and run in one command:

```bash
arx --run examples/print-star.x
```

Alias form is also available:

```bash
arx run examples/print-star.x
```

## Packages and Imports

When your project sets `[build].src_dir`, files under that directory are loaded
as dotted package modules.

Example layout:

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

Example project manifest:

```toml
[project]
name = "geometry"
version = "0.1.0"

[environment]
kind = "conda"
name = "geometry"

[build]
out_dir = "build"
```

Use `__init__.x` as the package root. Arx uses `src/` as the default source root
when `[build].src_dir` is omitted. Inside a nested module such as
`geometry.shapes.area`, use relative `from` imports for nearby modules and
parent-package modules:

````arx
```
title: Geometry shapes area
summary: Package-internal import example.
```
import radius_to_diameter from .helpers
import clamp from ..shared.math
````

Outside the package, use either direct symbol imports or a namespace alias:

````arx
```
title: Geometry consumer
summary: Public direct import example.
```
import circle_area from geometry.shapes.area
````

````arx
```
title: Geometry namespace consumer
summary: Public namespace import example.
```
import geometry.shapes.area as area

fn main() -> f64:
  ```
  title: main
  summary: Calls one function through a module namespace alias.
  ```
  return area.circle_area(10.0)
````

Current limitation: plain relative module imports such as `import .area` are not
supported yet.

## Compiled Tests

Arx now supports fatal assertion statements and a compiled test runner. Test
functions follow a simple convention:

- files: any `test_*.x` under the `tests/` directory by default
- function names: `test_*`
- signature: zero arguments
- return type: `none` (always declared explicitly as `-> none`)

Inside a `none` function you can end with a bare `return`, an explicit
`return none`, or omit the return statement entirely.

Example test module:

````arx
```
title: Example tests
summary: Demonstrates `assert` and `arx test`.
```
fn add(a: i32, b: i32) -> i32:
  return a + b

fn test_add() -> none:
  assert add(1, 2) == 3
  assert add(2, 2) == 4, "add(2, 2) should be 4"
````

Run the test suite with:

```bash
arx test
arx test tests/test_add.x --list
arx test -k add
arx test -x
arx test --keep-artifacts
arx test --exclude "tests/slow_*.x"
```

Test discovery can also be tuned from `.arxproject.toml`:

```toml
[tests]
paths = ["tests", "integration"]
exclude = ["tests/experimental_*.x"]
file_pattern = "test_*.x"
function_pattern = "test_*"
```

CLI arguments always take precedence over `[tests]` settings. Discovered tests
are displayed using the cwd-relative path of the source file (without the `.x`
suffix) joined to the function name via `::`, for example
`tests/unit/test_math::test_add`, so same-named files in different directories
stay unambiguous.

The runner compiles each selected test into its own temporary executable and
reports assertion failures from IRx's machine-readable runtime protocol. In v1,
shared top-level support is limited to imports, extern declarations, class
declarations, and helper functions; module-scope variable declarations and other
top-level executable code are rejected during collection.

## CLI Reference

```
arx [input_files] [options]
arx test [paths ...] [options]
```

| Option           | Description                                       |
| ---------------- | ------------------------------------------------- |
| `--version`      | Show the installed version                        |
| `--output-file`  | Specify the output file path                      |
| `--lib`          | Build source code as a library                    |
| `--show-ast`     | Print the AST for the input source code           |
| `--show-tokens`  | Print the tokens for the input source             |
| `--show-llvm-ir` | Print the LLVM IR for the input source            |
| `--run`          | Build and execute the compiled binary             |
| `--shell`        | Open Arx in a shell prompt (not yet implemented)  |
| `--link-mode`    | Set executable link mode: `auto`, `pie`, `no-pie` |
| `test`           | Discover, compile, and run `test_*` functions     |

## Troubleshooting

### PIE linker error in Colab or Conda

If the build fails with an error similar to:

```text
relocation R_X86_64_32 against `.rodata' can not be used when making a PIE object
```

run the compile step with:

```bash
arx average.x --link-mode no-pie
```

If you need a manual fallback:

```bash
arx --lib average.x --output-file average.o
clang -no-pie average.o -o average
```

## Language Basics

Arx's syntax is influenced by Python with significant whitespace (indentation).

### Types

Arx uses explicit type annotations for function parameters, variable
declarations, and function return types. Return type annotations are always
required, including `-> none`.

For annotation rules, see [Data Types](library/datatypes.md). For the full
catalog of built-in types and aliases, see
[Built-in Types](library/built-in-types.md).

### Functions

Functions are defined with the `fn` keyword and use `:` plus indentation for the
body:

````arx
```
title: Function definition example
summary: Shows a basic function declaration.
```
fn add(x: i32, y: i32) -> i32:
  ```
  title: add
  summary: Returns x plus y.
  ```
  return x + y
````

### Control Flow

**If/else:**

````arx
```
title: If/else example
summary: Shows conditional branching in a function.
```
fn abs(x: i32) -> i32:
  ```
  title: abs
  summary: Returns the absolute value of x.
  ```
  if x < 0:
    return 0 - x
  else:
    return x
````

**For loop:**

````arx
```
title: For loop example
summary: Shows loop syntax with a slice-like range clause.
```
fn count(n: i32) -> none:
  ```
  title: count
  summary: Iterates and prints star characters.
  ```
  for i in (1:n:1):
    putchard(42)
````

The range header uses `(start:end:step)` and is intentionally slice-like.

### Variables

Variables are declared with `var`:

````arx
```
title: Variable example
summary: Shows var binding inside a function.
```
fn example() -> i32:
  ```
  title: example
  summary: Binds a variable and computes a result.
  ```
  var a: i32 = 10
  return a + 1
````

### Extern Functions

External functions (e.g., from C) are declared with `extern`:

````arx
```
title: Extern declaration example
summary: Declares an external function symbol.
```
extern putchard(x: i32) -> i32
````

## Next Steps

- Check the [Roadmap](roadmap.md) for planned features
- Read the [Library Reference](library/index.md) for language feature details
- Review [Built-in Types](library/built-in-types.md) for the canonical type
  catalog
- Read the [Contributing Guide](contributing.md) to help develop Arx
- Browse the [API Docs](api/index.md) for the compiler internals
- Join the [Community](discord.md) on Discord
