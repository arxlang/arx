# Ecosystem Status

This page describes the current monorepo packages and related ArxLang tools.
Core compiler packages are pre-production unless stated otherwise. AIX is
included for completeness but is a toy project, not a promoted product.

## Status summary

| Project | Package identity              | Role                                         | Maturity                         |
| ------- | ----------------------------- | -------------------------------------------- | -------------------------------- |
| Arx     | `arxlang` / `arx` / `arx` CLI | Main language frontend and compiler CLI      | Functional prototype             |
| ASTx    | `astx` / `astx`               | Shared AST model                             | Functional, evolving library     |
| IRx     | `pyirx` / `irx`               | Analysis, lowering, LLVM, and native runtime | Functional experimental backend  |
| ArxPy   | `arxpy` / `arxpy`             | Python API for compiling and running Arx     | API foundation only              |
| ArxJIT  | `arxjit` / `arxjit`           | JIT decorator for a Python subset            | Frontend foundations only        |
| AIX     | `airx` / `aix` / `aix` CLI    | Toy symbolic-language experiment             | For fun; no stability commitment |

Distribution names, Python imports, and CLIs are listed separately where they
are not identical.

## Related repositories

These tools are maintained outside the main Arx monorepo:

| Project                              | Role                          | Current state                                                                                          |
| ------------------------------------ | ----------------------------- | ------------------------------------------------------------------------------------------------------ |
| [ArxPM](tools/arxpm.md)              | project and workspace manager | implements project, environment, build, packaging, and publishing workflows; compatibility is evolving |
| [VS Code extension](tools/vscode.md) | editor support                | syntax highlighting and language configuration; no language server                                     |
| [Jupyter kernel](tools/jupyter.md)   | notebook support              | wrapper kernel implementation; compiler command integration still requires alignment                   |
| [Douki](tools/douki.md)              | YAML docstring tooling        | standalone validation, synchronization, and migration tool used by Arx documentation conventions       |

See the [tooling overview](tools/index.md) for the boundary between these
projects and the compiler.

## Arx

Arx owns `.x` source syntax, lexing, parsing, project discovery, CLI behavior,
tests, bundled builtins, and the pure-Arx `stdlib` namespace.

Implemented today:

- typed functions, defaults, extern declarations, and function templates
- mutable variables, finite union aliases, casts, and type queries
- `if`/`else`, `while`, count-style `for`, and list-valued `for ... in`
- absolute, relative, grouped, namespace, stdlib, and installed-package imports
- classes, inheritance, fields, methods, access modifiers, and default
  construction
- lists and builtin `range`
- fixed-shape numeric tensors plus runtime-shaped tensor parameters
- static-schema DataFrames and typed Series
- fatal assertions and the compiled `arx test` runner
- token, AST, LLVM IR, object, executable, and run modes

Important limits:

- tensors are currently readonly and use fixed-width numeric element types
- runtime-shaped tensor parameters cannot yet be indexed dynamically
- DataFrame columns are currently fixed-width numeric or Boolean
- runtime-schema DataFrame parameters cannot expose columns by name
- the language and standard library remain intentionally small

## ASTx

ASTx is the shared, language-agnostic node model. It provides source locations,
expressions, statements, type nodes, functions, modules, control flow, classes,
templates, collections, tensors, DataFrames, buffer views, FFI types, and tree
visualization.

ASTx does **not** lex or parse source, perform IRx semantic analysis, or promise
that every modeled node has an IRx lowering. Node availability and backend
support are separate questions.

## IRx

IRx consumes ASTx nodes and owns semantic analysis, resolved sidecar metadata,
LLVM lowering, native artifact compilation, linking, execution helpers, and
runtime-feature activation.

Implemented areas include numeric promotion and casts, functions, imports,
structured control flow, templates, class layout and dispatch, diagnostics, FFI
contracts, buffers, lists, arrays, tensors, DataFrames, assertions, and the
native Apache Arrow runtime.

IRx also exposes a Python RecordBatch API backed by a native Arrow C++ bridge.
It supports schemas, builders, nullable values, scalar inspection, Arrow IPC
file/buffer streams, and PyArrow interoperability for numeric, Boolean, UTF-8,
large UTF-8, date, timestamp, and time columns.

IRx is not a source-language parser, a general query engine, or a complete
implementation of every ASTx node.

## ArxPy

ArxPy is intended to become the stable Python-facing compiler API. The current
package provides:

- immutable structured diagnostics and severity values
- adapters for IRx diagnostics and Arx parser failures
- `ArxError`, `ParseError`, `CompileError`, and `ExecutionError`

It does not yet provide public parse, compile, run, or artifact-management
functions. Applications needing compilation must currently use the Arx CLI or
lower-level Arx/IRx APIs.

## ArxJIT

ArxJIT is the planned Numba-style path from ordinary Python functions to ASTx
and IRx. The current package implements:

- the `@jit` decorator and `JitFunction` wrapper
- scalar signature types (`i32`, `i64`, `f32`, `f64`, and `bool_`)
- source extraction with structured diagnostics
- validation of the proposed pure-Python subset
- signature reconciliation and initial fail-closed ASTx lowering for scalar
  function shells and straight-line expressions

The decorator does not yet invoke lowering or compile native callable code.
Calling a decorated function executes the original Python function.

## AIX (toy project)

AIX is a small symbolic-language experiment built for fun. It has a Unicode
lexer, a limited parser, CLI inspection modes, and an IRx handoff for its toy
subset. It is not a primary ArxLang product and carries no stability or roadmap
commitment. Its [low-profile reference](aix/index.md) is retained for anyone
exploring the source tree.

## Release model

The build and publish scripts cover all six packages. Semantic release keeps the
ecosystem dependency versions aligned at release time. A newly introduced
package can temporarily show a scaffold version in the source tree until the
next lockstep release updates it.
