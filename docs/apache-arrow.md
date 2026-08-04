# Native Apache Arrow Support

Apache Arrow is the storage and interoperability foundation for ArxLang's
data-oriented runtime. IRx implements the integration in native C++ and exposes
it to generated LLVM through a stable C ABI.

## Architecture

```text
Arx collection syntax or IRx API
  -> ASTx collection nodes
  -> IRx semantic analysis and lowering
  -> IRx runtime feature activation
  -> generated LLVM calls irx_arrow_* / irx_rb_* symbols
  -> native Arrow C++ arrays, tensors, tables, and RecordBatches
```

This boundary provides three useful properties:

1. LLVM IR does not reproduce Arrow container layouts or ownership rules.
2. Native runtime artifacts are compiled and linked only when a module needs
   them.
3. Arrow C Data and Arrow IPC provide interoperable boundaries instead of a
   project-specific serialization format.

IRx installs `pyarrow` and `arx-arrowcpp-sources` as runtime dependencies. They
provide PyArrow interoperability plus the Arrow C++ headers, sources, library
locations, and linker metadata used by native builds.

## Implemented layers

| Layer               | Native representation                            | Current capability                                                               |
| ------------------- | ------------------------------------------------ | -------------------------------------------------------------------------------- |
| Array runtime       | Arrow arrays behind opaque `irx_arrow_*` handles | Build, inspect, import/export, null metadata, readonly buffer views              |
| Tensor runtime      | `arrow::Tensor`                                  | Fixed-width numeric construction, shape/stride metadata, indexing, shallow views |
| DataFrame runtime   | `arrow::Table`                                   | Named fixed-width numeric/Boolean columns and row/column counts                  |
| Series runtime      | `arrow::ChunkedArray`                            | Typed column views selected from DataFrames                                      |
| RecordBatch runtime | `arrow::RecordBatch` and Arrow IPC               | Schemas, builders, nullable values, file/buffer streams, PyArrow round trips     |

## Arx tensors and DataFrames

Arx exposes the native runtime without exposing Arrow implementation types in
the language syntax:

```arx
fn first(grid: tensor[i32, 2, 2]) -> i32:
  return grid[0, 0]

fn rows() -> i32:
  var frame: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  var scores: series[f64] = frame.score
  return cast(frame.nrows(), i32)
```

Current tensor constraints:

- element types: `i8`, `i16`, `i32`, `i64`, `f32`, and `f64`
- variables, fields, and return types require a static shape
- `tensor[T, ...]` is supported for runtime-shaped parameters
- dynamic indexing of runtime-shaped parameters is not implemented
- Arrow-backed tensor storage is readonly in the current phase

Current DataFrame constraints:

- columns: fixed-width numeric types and `bool`
- constructor input: equal-length list-literal columns matching a static schema
- access: `frame.name` or `frame["name"]` when the schema is statically known
- metadata: `nrows()` and `ncols()`
- string, nullable, nested, and temporal columns are not yet exposed by the Arx
  DataFrame syntax, even though the lower-level RecordBatch API supports more
  Arrow types

## Array interoperability

The lower-level IRx array runtime supports:

- signed and unsigned 8-, 16-, 32-, and 64-bit integers
- `float32`, `float64`, and Boolean arrays
- explicit array-builder and handle lifecycles
- Arrow C Data copy import, move/adopt import, and export
- null count and validity-bitmap inspection
- readonly `irx_buffer_view` projection for byte-addressable fixed-width arrays

Boolean values are bit-packed in Arrow and therefore do not use the generic
byte-addressable buffer-view bridge.

## RecordBatch IPC and PyArrow

The Python API in `irx.record_batch` is backed by a standalone native Arrow C++
shared library. It supports:

- signed/unsigned integers, `float32`, `float64`, and `bool`
- `utf8` and `large_utf8`
- `date32`, `date64`
- second, millisecond, microsecond, and nanosecond timestamps
- `time32` and `time64` units
- nullable fields and null values
- Arrow IPC streams in files and in-memory buffers

The test suite verifies both directions of interoperability: IRx-written IPC is
read by PyArrow, and PyArrow-written IPC is read by IRx.

The direct Python API currently requires its native shared library to be built
from a source checkout before first use:

```bash
python -c "from irx.builder.runtime.record_batch import build_record_batch_shared_library; build_record_batch_shared_library()"
```

Generated IRx programs use the runtime-feature system instead; their required
native artifacts are collected during the normal build/link flow.

## Deliberate boundaries

Native Arrow support does not yet imply a complete Arrow product surface. The
current implementation does not provide:

- an Arx query language or Arrow Compute kernel API
- general RecordBatch syntax in Arx
- nested, dictionary, decimal, or arbitrary extension types
- mutable Tensor storage or a NumPy-compatible tensor algebra API
- automatic zero-copy guarantees for every import/export path

These limits keep ownership, semantics, and compiler lowering explicit while the
public APIs mature.
