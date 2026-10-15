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
  return cast(rows.nrows(), i32)
````

The corresponding native runtime sources and linker inputs are included only
when the compilation unit uses those features.

## Next steps

- [Compiler CLI](compiler-cli.md)
- [Language syntax](syntax.md)
- [Language reference](index.md#language-reference)
- [Projects and imports](projects.md)
- [Compiled tests](testing.md)
- [Apache Arrow runtime](../apache-arrow.md)

## Try Arrow-core descriptors

From a development checkout, run:

```bash
arx --run examples/schema_descriptors.x
```

The example constructs `schema`, `field`, and `datatype` values using native
Arrow C++ without an Arrow import. It exercises descriptor inspection, not a
query engine or general nested arrays. See the
[descriptor reference](../arrow-type-schemas.md) for supported operations.

## Try primitive nullable values

```bash
arx --run examples/nullable_scalars.x
```

`T | none`, `is_null`, `is_valid`, and `expect_valid` are builtins; no Arrow
import is needed. The example demonstrates independent validity, nullable
function defaults and returns, and lossless payload widening. See
[Primitive nullable scalars](built-in-types.md#primitive-nullable-scalars) for
supported payloads and the current operator/container limits.

For native arrays without an Arrow import, run:

```bash
arx --run examples/columnar_arrays.x
```

For reusable builders, explicit chunk iteration, half-float arrays and nullable
shared owners, run:

```bash
arx --run examples/columnar_builders.x
```

These operations are ambient builtins, not an Arrow-namespaced library. See the
[builder and chunk reference](built-in-types.md#reusable-builders-and-chunked-arrays)
for ownership, bounds and current support limits.

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

## Try the checked ownership boundaries

```bash
arx --run examples/dataframe_adapters.x
arx --run examples/columnar_interchange.x
arx --run examples/extension_values.x
arx --run examples/nullable_strings.x
arx --run examples/nullable_collections.x
```

These examples cover explicit legacy adapters, packed validity buffers, owned C
Data interchange, extension storage, nullable string/class-field copies, and
optional list/tensor owners. They use builtin names without importing Arrow.
Nested nullable collection elements and managed by-value struct destruction
remain unfinished.
