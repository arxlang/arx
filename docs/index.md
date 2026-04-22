# ArxLang

Arx is a multi-purpose compiler that aims to provide native array and ndarray
abstractions backed internally by IRx runtime support. It uses the power of
[LLVM](https://llvm.org/) to provide multi-architecture machine target code
generation.

The language syntax is influenced by Python, C++, and YAML, featuring
significant whitespace, static typing (planned), and a focus on data-oriented
computing.

## Quick Example

````arx
```
title: Quick average example
summary: Demonstrates a function with module and function docstrings.
```
fn average(x: f32, y: f32) -> f32:
  ```
  title: average
  summary: Returns the arithmetic mean of x and y.
  ```
  return (x + y) * 0.5
````

```bash
arx --show-llvm-ir examples/average.x
```

See the [Getting Started](getting-started.md) guide for installation and more
examples. For language details, see the [Library Reference](library/index.md).

## Architecture Boundary

Arx is the surface-language front end. It owns source syntax, lexing, parsing,
CLI flow, tests, examples, and docs. IRx owns the AST model (`irx.astx`),
semantic analysis, lowering, and backend code generation. When a new feature
needs AST or lowering support, that support should be added in IRx first and
then consumed from Arx.

## Key Features

- **LLVM-powered** -- compiles to native machine code via LLVM
- **Python-like syntax** -- indentation-based blocks, familiar keywords
- **Native arrays and ndarrays** -- builtin shaped array abstractions with
  first-class indexing and compiler-known shapes
- **Multiple output modes** -- inspect tokens, AST, LLVM IR, or compile to
  object files

## Project Status

Arx is currently a prototype built on the
[Kaleidoscope](https://llvm.org/docs/tutorial/) tutorial compiler. It supports
functions, control flow (`if`/`else`, `for`), variables, and extern
declarations. See the [Roadmap](roadmap.md) for what's planned next.

## Arx Enhancement Proposals

Any change to the language syntax should be done using an Enhancement Proposal
via the [arx-proposals](https://github.com/arxlang/arx-proposals) repository.
