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

```
fn sum(a, b):
  return a + b
```

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

```
fn sum(a, b):
  return a + b;
```

### Average

```
fn average(x, y):
  return (x + y) * 0.5;
```

### Fibonacci

```
fn fib(x):
  if x < 3:
    return 1
  else:
    return fib(x-1)+fib(x-2)
```

### Constant

```
fn get_constant(x):
  return x;
```

### Print Star

```
fn print_star(n):
  for i = 1, i < n, 1.0 in
    putchard(42);  # ascii 42 = '*'
```

You can compile any example with:

```bash
arx examples/sum.x --show-llvm-ir
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
| `--shell`        | Open Arx in a shell prompt (not yet implemented) |

## Language Basics

Arx's syntax is influenced by Python with significant whitespace (indentation).

### Functions

Functions are defined with the `fn` keyword and use `:` plus indentation for the
body:

```
fn add(x, y):
  return x + y
```

### Control Flow

**If/else:**

```
fn abs(x):
  if x < 0:
    return 0 - x
  else:
    return x
```

**For loop:**

```
fn count(n):
  for i = 1, i < n, 1.0 in
    putchard(42)
```

### Variables

Variables are declared with `var`:

```
fn example():
  var a = 10 in
    a + 1
```

### Extern Functions

External functions (e.g., from C) are declared with `extern`:

```
extern putchard(x)
```

## Next Steps

- Check the [Roadmap](roadmap.md) for planned features
- Read the [Library Reference](library/index.md) for language feature details
- Read the [Contributing Guide](contributing.md) to help develop Arx
- Browse the [API Docs](api/index.md) for the compiler internals
- Join the [Community](discord.md) on Discord
