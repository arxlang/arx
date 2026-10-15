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
- static/runtime-schema DataFrames and typed Series, including optional owners
- builtin Arrow-core `datatype`, `field`, and `schema` descriptors
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
- Runtime-schema DataFrames require checked projection through `to_table`;
  unchecked legacy column-name access remains unavailable.
- The standard library and general language surface remain limited.
- Arx does not define AST node types or feature lowering; those belong to ASTx
  and IRx respectively.

## Related tools

- [ArxPM](../tools/arxpm.md) manages Arx projects and environments.
- [VS Code support](../tools/vscode.md) provides syntax highlighting.
- [ArxLang Jupyter kernel](../tools/jupyter.md) compiles notebook cells.
- [Douki](../tools/douki.md) defines the YAML docstring tooling used by Arx.

Source: [github.com/arxlang/arx](https://github.com/arxlang/arx)

`datatype`, `field`, and `schema` provide native descriptor construction and
inspection without importing Arrow. See
[Logical types and schemas](../arrow-type-schemas.md) for the supported syntax
and the distinction between descriptors and array values.

Primitive nullable scalars use builtin `T | none` types and explicit `is_null`,
`is_valid`, and `expect_valid` operations. They carry independent validity
through local storage and function boundaries without an Arrow import.
[Nullable scalar support](built-in-types.md#primitive-nullable-scalars) includes
primitive null-propagating operators and predicate narrowing.
[Primitive arrays](built-in-types.md#first-class-arrays) support typed
construction, nullable extraction, reusable builders, explicit chunking and
immutable transformations. Nullable shared array/descriptor owners are
supported, alongside the variable-width and nested value paths below.

Typed `record_batch` and `table` values now expose primitive nullable columns,
checked projection and immutable structural transformations as ambient builtins.
Constructors take an explicit row count, then arrays (batch) or chunked arrays
(table); no Arrow import is needed. See
[built-in types](built-in-types.md#record-batches-and-tables) and
`examples/columnar_tables.x`. Nullable primitive casts, compound validity
proofs, optional unique builders and nullable instance fields are also
supported. Logical values, checked buffer/C Data constructors and explicit
legacy DataFrame/Series adapters are described below.

Logical columnar values are also native builtins: `scalar[T]`, typed arrays,
reusable builders, chunks, batches and tables need no Arrow import. See
[built-in types](built-in-types.md#logical-scalars-and-nested-values) for
strings, binary, temporal, decimal and nested construction, checked nullable
extraction, `array_from_buffer`, and explicit `take_rows` selection. Checked
buffer/C Data constructors and explicit legacy DataFrame/Series adapters are
also supported.

Arrow-core values also provide explicit DataFrame/Series adapters, checked C
Data owners and packed-buffer constructors, and identity-preserving extension
storage. Nullable `str` and owned class string fields duplicate borrowed text
instead of retaining dangling pointers. These are builtin facilities; see the
[builtin reference](built-in-types.md#checked-c-data-and-buffer-construction).
Optional list and tensor owners carry independent validity and release their
payloads on scope exit; lists stay unique and tensor copies retain shared
buffers. Nested nullable elements, managed by-value structs and cross-frame
fatal cleanup remain open.
