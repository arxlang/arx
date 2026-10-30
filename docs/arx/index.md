---
html: true
---

# Arx Programming Language

Independent libraries can use [native package dependencies](native-packages.md)
to link C ABI backends without adding domain-specific runtime features to Arx.

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

<span id="language-reference"></span>

## Language guides

- [Modules and imports](modules.md)
- [Functions](functions.md)
- [Text file I/O](file-io.md)
- [Classes](classes.md)
- [Data types](datatypes.md)
- [Choosing built-in types](built-in-types.md)
- [Collections and Apache Arrow](collections.md)
- [CSV files and DataFrame conversion](csv.md)
- [Parquet files and DataFrame conversion](parquet.md)
- [Control flow](control-flow.md)
- [Douki docstrings](docstrings.md)

## Support and contracts

The [capability matrix](capability-matrix.md) is the single compact summary of
implemented support and exclusions. The [preview contracts](specification.md)
explain arithmetic, ownership, failure, and compatibility decisions; neither is
a stability promise.

Handwritten pages focus on workflows and safety. Python API reference is
[generated from source](../api/arx.md), not maintained as copied signatures.

## Related tools

- [ArxPM](../tools/arxpm.md) manages Arx projects and environments.
- [VS Code support](../tools/vscode.md) provides syntax highlighting.
- [ArxLang Jupyter kernel](../tools/jupyter.md) compiles notebook cells.
- [Douki](../tools/douki.md) defines the YAML docstring tooling used by Arx.

Source: [github.com/arxlang/arx](https://github.com/arxlang/arx)

For tabular computation, [collections](collections.md) covers nullable scalar
and Series expressions and parameterized static DataFrame schemas.
