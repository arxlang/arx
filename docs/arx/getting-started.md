# Getting Started with Arx

This guide installs the Arx compiler and compiles a small program. See the
[compiler CLI](compiler-cli.md) for inspection and output modes.

## Requirements

- Python 3.10 or newer
- `pip` for a published installation, or Mamba/Conda and Poetry for a source
  checkout
- LLVM/Clang-compatible tools for object and executable generation
- a C++ compiler when a program activates native Apache Arrow features

Token, ASTx, and most LLVM translation workflows do not invoke the system
linker. Building or running an executable does.

## Install from PyPI

```bash
pip install arxlang
arx --version
```

The `arxlang` distribution installs the `arx` Python package and the `arx`
command. Its IRx dependency provides the analysis, LLVM, and native runtime
layers.

## Install a development checkout

```bash
git clone https://github.com/arxlang/arx.git
cd arx
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

The repository is a monorepo containing Arx, ASTx, IRx, ArxPy, ArxJIT, and the
low-profile AIX experiment.

## Compile a program

Create `hello.x`:

````arx
```
title: Hello module
summary: Compiles a small typed Arx program.
```

fn add(a: i32, b: i32) -> i32:
  ```
  title: add
  summary: Adds two values.
  ```
  return a + b

fn main() -> i32:
  ```
  title: main
  summary: Prints one result and returns success.
  ```
  print(add(20, 22))
  return 0
````

Inspect the compiler stages:

```bash
arx --show-tokens hello.x
arx --show-ast hello.x
arx --show-llvm-ir hello.x
```

Build and run:

```bash
arx hello.x --output-file hello
./hello

# Equivalent one-step forms
arx --run hello.x
arx run hello.x
```

An executable normally defines `main() -> i32` and returns `0` on success. A
single `main(n: i32)` parameter follows the native C `main` ABI and receives
`argc`.

## Compile an Arrow-backed value

Arx tensors, DataFrames, and Series activate IRx's native Apache Arrow C++
runtime:

````arx
```
title: Arrow-backed collections
summary: Uses a Tensor, DataFrame, and Series.
```

fn main() -> i32:
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  var scores: series[f64] = rows.score
  assert grid[1, 0] == 3
  assert rows.nrows() == 3
  assert scores[2] == 1.0
  return 0
````

The corresponding native runtime sources and linker inputs are included only
when the compilation unit uses those features.

## Exchange Arrow data with Python

`stdlib.arrow` adds runtime-schema RecordBatches, IPC file/stream readers and
writers, and TCP clients. No new language syntax or Python serialization is
needed in the Arx producer. C++20 and the installed Arrow libraries are required
at build/link time. From a checkout, run all compiled interoperability examples:

```bash
python examples/arrow/run.py --directory .tmp/arrow-demo
```

See the [Arrow interoperability guide](../apache-arrow.md) for schema types,
nullable values, C Data/C Stream ownership and network limitations.

## Next steps

- [Compiler CLI](compiler-cli.md)
- [Language syntax](syntax.md)
- [Language reference](index.md#language-reference)
- [Projects and imports](projects.md)
- [Compiled tests](testing.md)
- [Apache Arrow runtime](../apache-arrow.md)

## Workflow guides

- [Text files](file-io.md): shared references, checked UTF-8, and explicit
  close. Run `examples/file-io.x` in a scratch directory; it creates or
  truncates its output file.
- [Classes](classes.md): identity, construction, and final-reference cleanup.
- [CSV](csv.md) and [Parquet](parquet.md): eager DataFrames or explicit bounded
  streams, exact schema checks, and safe output publication.
- [Nullable collections](collections.md#nullable-scalars-and-series-expressions):
  validity, checked arithmetic, and mutation ownership.
- [Native packages](native-packages.md): explicit external C ABI dependencies.

The complete programs above are compiled and run from this page by
`packages/arx/tests/python/test_documentation.py`.
