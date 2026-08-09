# Arx Programming Language

Arx is the programming language and source frontend in the ArxLang ecosystem.
The `arxlang` distribution provides the `arx` Python package and the `arx`
command-line compiler.

Arx owns source syntax, lexing, parsing, project-aware imports, compiler CLI
behavior, and compiled tests. The parser emits ASTx nodes. IRx then performs
semantic analysis, LLVM lowering, native runtime activation, and artifact
generation.

```text
Arx source
  -> Arx lexer and parser
  -> ASTx nodes
  -> IRx semantic analysis
  -> LLVM IR
  -> object file or executable
```

> **Status:** Arx is a functional prototype. Implemented behavior is tested, but
> the language and compiler interfaces are not production-stable.

## Start here

- [Install the compiler and compile a program](getting-started.md)
- [Use the compiler CLI](compiler-cli.md)
- [Read the lexical syntax specification](syntax.md)
- [Configure projects and imports](projects.md)
- [Write and run compiled tests](testing.md)

## Language reference

- [Modules and imports](modules.md)
- [Functions](functions.md)
- [Classes](classes.md)
- [Data types](datatypes.md)
- [Built-in types](built-in-types.md)
- [Collections and Apache Arrow](collections.md)
- [Control flow](control-flow.md)
- [Douki docstrings](docstrings.md)

## Implemented areas

The current frontend supports:

- typed functions, defaults, extern declarations, and function templates
- mutable variables, finite union aliases, casts, and type queries
- `if`/`else`, `while`, count-style `for`, and list-valued `for ... in`
- absolute, relative, grouped, namespace, standard-library, and installed
  package imports
- classes, inheritance, fields, methods, modifiers, and default construction
- lists and builtin `range`
- fixed-shape numeric tensors and runtime-shaped tensor parameters
- static-schema DataFrames and typed Series
- assertions and the compiled `arx test` runner
- token, ASTx, LLVM IR, object, executable, and run modes

## Apache Arrow types

Arx exposes typed collection syntax backed by IRx's native Arrow C++ runtime:

| Arx type                  | Runtime representation |
| ------------------------- | ---------------------- |
| `tensor[T, D0, ...]`      | `arrow::Tensor`        |
| `dataframe[name: T, ...]` | `arrow::Table`         |
| `series[T]`               | `arrow::ChunkedArray`  |

See [Collections and Apache Arrow](collections.md) for language rules and
[Native Apache Arrow Support](../apache-arrow.md) for the runtime boundary and
current interoperability features.

## Current limits

- Tensor elements are currently fixed-width signed integers or floats.
- Tensors are readonly, and runtime-shaped parameters cannot be indexed
  dynamically.
- DataFrame columns currently use fixed-width numeric or Boolean values.
- Runtime-schema DataFrame parameters do not expose columns by name.
- The standard library and general language surface remain limited.
- Arx does not define AST node types or feature lowering; those belong to ASTx
  and IRx respectively.

## Related tools

- [ArxPM](../tools/arxpm.md) manages Arx projects and environments.
- [VS Code support](../tools/vscode.md) provides syntax highlighting.
- [ArxLang Jupyter kernel](../tools/jupyter.md) compiles notebook cells.
- [Douki](../tools/douki.md) defines the YAML docstring tooling used by Arx.

Source: [github.com/arxlang/arx](https://github.com/arxlang/arx)
