# Arx language compiler

`arxlang` is the main language frontend in the ArxLang ecosystem. It provides
the `arx` Python package and `arx` command for lexing, parsing, inspecting, and
compiling `.x` source files.

Arx emits ASTx nodes and delegates semantic analysis, LLVM lowering, native
runtime features, and linking to IRx.

> Status: functional prototype. Supported behavior is tested, but the language
> and APIs are not yet production-stable.

## Native Apache Arrow collections

Arx exposes data-oriented types backed by IRx's native Arrow C++ runtime:

- `tensor[T, D0, ...]` uses `arrow::Tensor`
- `dataframe[name: T, ...]` uses `arrow::Table`
- `series[T]` uses `arrow::ChunkedArray`

```arx
fn main() -> i32:
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  return cast(rows.nrows(), i32)
```

Current Tensor elements are fixed-width signed integers and floats. Current
DataFrame columns are fixed-width numeric values or `bool`. Runtime-shaped
Tensor and runtime-schema DataFrame types are parameter-only, and their dynamic
index/column access remains deferred.

## Install

```bash
pip install arxlang
arx --version
```

Building executables requires LLVM/Clang-compatible tools. Arrow-backed features
also require a C++ compiler.

## CLI

```bash
arx --show-tokens program.x
arx --show-ast program.x
arx --show-llvm-ir program.x
arx program.x --output-file program
arx --run program.x
arx test
```

Use `--link-mode auto`, `pie`, or `no-pie` when a platform requires an explicit
linking mode.

## Implemented language areas

- explicit scalar, collection, class, and finite-union annotations
- functions, trailing defaults, externs, and templates
- mutable variables, assignments, casts, `isinstance`, and `type`
- `if`/`else`, `while`, count loops, and list-valued `for ... in`
- absolute, relative, grouped, namespace, installed-package, and stdlib imports
- classes, inheritance, fields, methods, modifiers, and default construction
- lists, builtin `range`, Tensors, DataFrames, and Series
- Douki module/class/function/method docstrings
- fatal assertions and compiled tests

## Boundaries

Arx owns source syntax and CLI behavior. It does not define new AST node types
or implement feature lowering locally: those responsibilities belong to ASTx and
IRx respectively.

Documentation: <https://arxlang.org>

License: Apache-2.0.
