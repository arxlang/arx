# ArxLang

ArxLang is an experimental compiler ecosystem for statically typed,
data-oriented programming. Arx source is parsed into ASTx, analyzed and lowered
by IRx, and compiled to native code through LLVM.

Apache Arrow is a native part of the runtime architecture. IRx uses Arrow C++
for arrays, tensors, tables, column views, and RecordBatch IPC instead of
encoding those containers directly in LLVM IR.

> **Project status:** the ecosystem is functional but pre-production. The
> supported surface is tested, while APIs and language semantics may still
> change between releases.

- Documentation: <https://arxlang.org>
- Issue tracker: <https://github.com/arxlang/arx/issues>
- License: Apache-2.0

## Ecosystem

| Directory         | Distribution / import | Responsibility                                       | Current state                                             |
| ----------------- | --------------------- | ---------------------------------------------------- | --------------------------------------------------------- |
| `packages/arx`    | `arxlang` / `arx`     | Arx lexer, parser, CLI, and language frontend        | Prototype compiler with native build/run support          |
| `packages/astx`   | `astx` / `astx`       | Language-agnostic AST node model                     | Functional and broadly modeled; still evolving            |
| `packages/irx`    | `pyirx` / `irx`       | Semantic analysis, LLVM lowering, and native runtime | Functional experimental backend with Arrow C++ support    |
| `packages/arxpy`  | `arxpy` / `arxpy`     | Python-facing Arx compiler API                       | API foundation: diagnostics and error hierarchy only      |
| `packages/arxjit` | `arxjit` / `arxjit`   | Numba-style Python decorator path                    | Frontend foundations; calls still use the Python fallback |
| `packages/aix`    | `airx` / `aix`        | Toy symbolic-language experiment                     | For fun; no stability or product commitment               |

See the [ecosystem status](https://arxlang.org/ecosystem.html) for the exact
implemented and deferred scope of every package.

## Native Apache Arrow support

IRx provides an on-demand native runtime backed by Arrow C++:

- primitive Arrow arrays with Arrow C Data import/export
- homogeneous N-dimensional `arrow::Tensor` values
- Arx DataFrames backed by `arrow::Table`
- Series views backed by `arrow::ChunkedArray`
- RecordBatch construction and Arrow IPC file/buffer streaming
- interoperability tests against PyArrow

The RecordBatch layer currently supports signed and unsigned integers,
`float32`, `float64`, booleans, UTF-8 and large UTF-8 strings, dates,
timestamps, times, and nullable fields. The higher-level Arx DataFrame surface
is deliberately narrower: fixed-width numeric and Boolean columns only.

Read [Apache Arrow in ArxLang](https://arxlang.org/apache-arrow.html) for the
architecture, supported types, and current limitations.

## Arx example

````arx
```
title: Native Arrow-backed collections
```

fn main() -> i32:
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  print(rows.nrows())
  return grid[1, 0]
````

```bash
arx --show-llvm-ir program.x
arx --run program.x
```

## Installation

Install the language compiler from PyPI:

```bash
pip install arxlang
```

Native executable generation requires a working LLVM/Clang-compatible toolchain.
Arrow-backed features also require a C++ compiler; IRx obtains Arrow C++ build
metadata from its installed `pyarrow` and `arx-arrowcpp-sources` dependencies.

For development:

```bash
git clone https://github.com/arxlang/arx.git
cd arx
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

Common checks:

```bash
makim all.ci
makim docs.build
```

The root Poetry environment wires every package to its local source directory.
Published package dependencies continue to use the released distribution names
and lockstep versions.

## Documentation map

- [Getting started](https://arxlang.org/getting-started.html)
- [Ecosystem status](https://arxlang.org/ecosystem.html)
- [Apache Arrow support](https://arxlang.org/apache-arrow.html)
- [Arx language and compiler](https://arxlang.org/arx/)
- [ASTx](https://arxlang.org/astx/)
- [IRx](https://arxlang.org/irx/)
- [Roadmap](https://arxlang.org/roadmap.html)
