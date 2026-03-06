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

## CLI Reference

```
arx [input_files] [options]
```

| Option           | Description                                      |
| ---------------- | ------------------------------------------------ |
| `--version`      | Show the installed version                       |
| `--output-file`  | Specify the output file path                     |
| `--lib`          | Build source code as a library                   |
| `--show-ast`     | Print the AST for the input source code          |
| `--show-tokens`  | Print the tokens for the input source            |
| `--show-llvm-ir` | Print the LLVM IR for the input source           |
| `--run`          | Build and execute the compiled binary            |
| `--shell`        | Open Arx in a shell prompt (not yet implemented) |

## Language Basics

Arx's syntax is influenced by Python with significant whitespace (indentation).

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
fn example():
  ```
  title: example
  summary: Binds a variable and computes a result.
  ```
  var a = 10 in
    a + 1
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
- Read the [Contributing Guide](contributing.md) to help develop Arx
- Browse the [API Docs](api/index.md) for the compiler internals
- Join the [Community](discord.md) on Discord
