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

The direct Python API builds a fingerprinted native shared library on first use.
To pre-warm that cache explicitly:

```bash
python -c "from irx.builder.runtime.record_batch import ensure_record_batch_shared_library; ensure_record_batch_shared_library()"
```

Generated IRx programs use the runtime-feature system instead; their required
native artifacts are collected during the normal build/link flow.

## Deliberate boundaries

Native Arrow support does not yet imply a complete Arrow product surface. The
current implementation does not provide:

- an Arx query language or Arrow Compute kernel API
- dedicated RecordBatch syntax (use `stdlib.arrow` classes instead)
- general nested scalar access, dictionary, decimal, or arbitrary extension
  types
- mutable Tensor storage or a NumPy-compatible tensor algebra API
- automatic zero-copy guarantees for every import/export path

These limits keep ownership, semantics, and compiler lowering explicit while the
public APIs mature.

## Compiled Arx interoperability (`stdlib.arrow`)

`stdlib.arrow` exposes runtime-schema RecordBatches without changing the
language grammar or converting them to statically typed DataFrames. It reuses
the `irx_rb_*` implementation; the small `irx_rb_api_*` facade checks statuses
before reading output slots and supplies scoped class-owned handles. The
frontend only binds ASTx opaque types and native capabilities for the reserved
bundled module. IRx performs normal class, call, FFI, ownership analysis and
lowering. Importing unrelated standard-library modules does not activate the
RecordBatch runtime.

### Build requirements and demonstrations

Use the normal Arx development environment, including Clang, a **C++20**
compiler, PyArrow and `arx-arrowcpp-sources`. Native sources are compiled on
demand through the existing runtime feature registry. The executable must be
able to load the Arrow shared library used at link time; it does not start
Python to serialize or deserialize data. The Python peer needs PyArrow; the
demonstration runner also uses the compiler to build the Arx programs.

From the repository root:

```bash
python examples/arrow/run.py --directory .tmp/arrow-demo
# Or choose --scenario files, --scenario c, or --scenario tcp.
```

The runner uses temporary build/output paths chosen by `--directory` and
**ephemeral loopback ports**. Its examples are also integration-test inputs:

- `examples/arrow/write_file.x` creates integer, floating-point and Boolean
  columns in compiled Arx and writes `arx.arrow`. Python uses `pa.ipc.open_file`
  and checks the schema and every value.
- `examples/arrow/read_file.x` reads `python.arrow`, created by Python with
  `pa.ipc.new_file`, and checks the full schema and every value. A separate test
  supplies a mismatched schema and requires failure.
- `examples/arrow/tcp.x` sends or receives **two distinct RecordBatches**. The
  runner builds real Arx launchers and exchanges standard IPC streaming bytes
  with a Python process over TCP in both directions.
- `examples/arrow/types.x` exercises every scalar append/get family, schema
  inspection, nullable values, empty batches, builder reuse and repeated close.
- `examples/arrow/component.x` builds a shared native component. Python invokes
  `component__produce_stream` / `component__produce_array`, then imports their
  outputs using PyArrow's `_import_from_c` APIs. The producing Arx locals have
  already been destroyed. The reverse functions consume PyArrow-exported data.
  This is compiled Arx, not the `irx.record_batch` Python wrapper.

### Public API

````arx
```
title: Write a RecordBatch
```
import (Schema, BatchBuilder, RecordBatch, IPCWriter) from stdlib.arrow

fn main() -> i32:
  var schema: Schema = Schema()
  schema.add("id", 3)
  schema.add("score", 9)
  schema.add("active", 10)
  var builder: BatchBuilder = BatchBuilder(schema)
  builder.append_i64(0, 42)
  builder.append_f64(1, 1.5)
  builder.append_bool(2, true)
  var batch: RecordBatch = builder.finish()
  var writer: IPCWriter = IPCWriter(schema)
  writer.open_file("example.arrow")
  writer.write(batch)
  writer.close()
  return 0
````

`Schema.add(name, type_id, nullable=false)` uses the stable `IrxColumnType` IDs:

| IDs   | Arrow types                          | Arx append/get suffix                             |
| ----- | ------------------------------------ | ------------------------------------------------- |
| 0–3   | int8, int16, int32, int64            | `i8`, `i16`, `i32`, `i64`                         |
| 4–7   | uint8, uint16, uint32, uint64        | Preserve/forward; no unsigned Arx scalar accessor |
| 8–10  | float32, float64, Boolean            | `f32`, `f64`, `bool`                              |
| 11–12 | UTF-8, large UTF-8                   | `utf8`                                            |
| 13–14 | date32 (days), date64 (milliseconds) | `date` (`i64` count)                              |
| 15–18 | timestamp s, ms, us, ns              | `timestamp` (`i64` count)                         |
| 19–22 | time32 s/ms, time64 us/ns            | `time` (`i64` count)                              |

Types, units, timezones, field nullability and schema/field metadata are
retained on imported batches, schema snapshots and IPC/C exports. Imported
supported list/struct layouts can be forwarded intact, but the Arx scalar
methods do not provide nested traversal or construction. IDs 23/24 are
inspection results, not primitive arguments to `Schema.add`.

| Class                  | Operations                                                                                                     |
| ---------------------- | -------------------------------------------------------------------------------------------------------------- |
| `Schema()`             | `add`, `nfields`, `name(col)`, `type(col)`, `type_name(col)`, `nullable(col)`, `equals(other)`                 |
| `BatchBuilder(schema)` | `append_<suffix>(col, value)`, `append_null(col)`, `finish()`                                                  |
| `RecordBatch()`        | Empty output holder; `nrows`, `ncols`, `schema`, `is_null(col,row)`, `get_<suffix>(col,row)`                   |
| `IPCReader()`          | `open_file(path)`, `open_stream(path)`, `connect(host,port,timeout_ms=30000)`, `next()`, `batch()`, `schema()` |
| `IPCWriter(schema)`    | `open_file(path)`, `open_stream(path)`, `connect(host,port,timeout_ms=30000)`, `write(batch)`                  |

All five classes have idempotent `close()` and automatic destruction at their
last class reference. `finish()` resets the builder's column buffers for reuse;
it does not destroy the builder. `next()` returns false only at end of stream,
not for an empty batch. `batch()` returns an independent batch snapshot and is
valid only after a successful `next()`. A reader's schema can be inspected
before reading any batches. `equals` and `write` compare metadata as well as
types and nullability. Close readers/writers before reopening them.

Use `open_file` for the Arrow random-access **file format**, and `open_stream`
for **streaming format stored at a path**. Both support multiple batches.
Zero-field builders produce zero rows; imported zero-column batches retain their
original row count. For nullable data, test `is_null` before a getter. Typed
getters reject nulls and wrong types rather than inventing default values. Arx
`str` cannot represent embedded NUL: getters reject such text explicitly; IPC
and C sharing still preserve string values without conversion. Field names and
timestamp timezone strings containing NUL can round-trip through IPC, but C
schema export rejects them rather than silently truncating them.

Arx operations use `ARX-RUNTIME-ARROW-001` on failure and terminate the process,
consistent with the current File API. No source location is invented for native
failures (line/column are zero). Native embedding callers needing
**recoverable** errors should use the status-returning `irx_rb_*` ABI, inspect
`irx_record_batch_errmsg()` immediately, and never read output slots on error.

### Same-process C Data and C Stream

The native header `irx_record_batch.h` provides schema/batch export and move
import, batch-to-stream export, and reader-to-stream export/import. It reuses
`irx_arrow_c_abi.h`. Arrow C++ supplies the standard `get_schema`, `get_next`,
`get_last_error` and `release` callbacks. No Arrow C++ layouts appear in LLVM.
The pre-existing array C Data copy/move APIs remain available unchanged.

Arx additionally provides:

- `batch.export_c(array_address, schema_address) -> i32`
- `batch.export_stream(stream_address) -> i32`
- `batch.import_c(array_address, schema_address)`
- `reader.import_stream(stream_address)`

These addresses are **trusted, same-process pointers** encoded as `i64` for the
current 64-bit native targets. They are not serialized handles. Allocate
zero-initialized standard structs in the host, keep their outer storage alive,
and check export status before importing into PyArrow. Arbitrary addresses are
unsafe. `native_handle()` is a borrowed opaque FFI escape hatch, not a
transferable owner; never destroy it, wrap it in a second owning object, or use
it after the class closes. Normal Arx code does not need this method.

Exports retain Arrow buffers independently of the producing handle. Importing
moves C ownership; after any attempted import, call a release callback only if
it is still non-null. Import failures may already have consumed inputs. Native
`irx_rb_c_{array,schema,stream}_release` helpers guard repeated release attempts
on **still-allocated outer structs**, not on freed pointers. Raw opaque-handle
release functions still free once and must not be called twice.

`irx_rb_stream_reader_export` transfers the remaining iteration to the C stream;
the original reader becomes exhausted and may be closed. Schema and array
outputs outlive the stream. An array with `release == NULL` denotes end of
stream; an empty batch has a live release callback. Stream callbacks are not
thread-safe: serialize calls. Keep the producer shared library loaded until all
exported objects have been released.

RecordBatch C exports/imports share or adopt buffers without serialization;
schema descriptors and wrapper objects allocate. IPC serializes data, socket
reads allocate per-message buffers, and the existing buffer-input API copies its
input. Existing array copy APIs also copy. These are **not universal zero-copy
guarantees**. See the standard
[C Data](https://arrow.apache.org/docs/format/CDataInterface.html) and
[C Stream](https://arrow.apache.org/docs/format/CStreamInterface.html)
contracts.

### Across machines

The Python peer listens and Arx connects, in either data direction. To move the
loopback demonstration across hosts, run the Python listener on the receiving
host (bind to its chosen interface), and compile the generated Arx launcher with
that host's **numeric IPv4 or IPv6 address** and agreed port instead of
loopback. Use `send` when Python reads with `pa.ipc.open_stream(socket_file)`,
or `receive` when Python writes with `pa.ipc.new_stream(socket_file, schema)`.
Close the Arrow writer before closing the socket so it emits the end marker. The
runner's `tcp()` contains the complete Python peer and launcher implementation.

Transport is separate from serialization (`irx_arrow_transport.*`). Native
`irx_rb_fd_reader_open` / `irx_rb_fd_writer_open` duplicate a borrowed POSIX
file descriptor, allowing host-supplied files/pipes as streaming endpoints.
Closing these streams does not close the caller's descriptor; offsets are
shared. For pipe writes, the host must arrange its SIGPIPE policy. TCP writes
suppress SIGPIPE and handle partial writes, interrupted calls and connection
failures.

TCP is blocking, POSIX-only, numeric-address-only, with a positive connect and
per-I/O timeout. It buffers messages/batches rather than an entire unbounded
stream. This is **not an untrusted network service**: there is no
authentication, TLS, batch-size quota, hostname resolution, listener API in Arx,
or Flight. Use trusted peers and network controls. A slow peer can extend total
transfer time by making progress; the timeout is not a whole-transfer deadline.

Interop stream readers require an explicit Arrow end marker, even though some
Arrow implementations accept transport EOF in its place. This detects a
connection cut exactly between batches as well as truncated messages. Both
PyArrow's normal writer close and the Arx writer emit this marker.

A future Flight adapter can feed the same opaque batches/readers without
changing the public data representation; Flight authentication and RPC are not
part of this transport.

### Compatibility and limitations

| Capability                                                                | Status                                                                   |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Standalone Arx ↔ PyArrow IPC files and streams                           | Implemented, multiple/empty batches                                      |
| Nullable numeric/Boolean, UTF-8 and temporal batches                      | Runtime-schema API; checked typed methods                                |
| Full field/schema metadata and timestamp timezone preservation            | IPC and C sharing; not projected into DataFrames                         |
| Zero-column input with nonzero rows                                       | Preserved                                                                |
| C Data/C Stream, both directions                                          | Standard structs; explicit ownership transfer                            |
| TCP, both directions                                                      | POSIX blocking clients; trusted numeric-address peers                    |
| DataFrame ↔ RecordBatch conversion                                       | Not implemented; construct/use `RecordBatch` instead                     |
| Dictionary, decimal, binary, extension and other unclassified Arrow types | Rejected at import/open; no silent conversion                            |
| Unsigned and supported nested values                                      | Forwarding supported; Arx scalar access/construction limited as above    |
| Arbitrary metadata editing, timestamp timezone creation in Arx            | Not exposed; imported schemas retain them                                |
| Memory safety                                                             | Functional ownership tests and a sanitizer harness; no blanket guarantee |

The sanitizer harness is `packages/irx/tests/native/arrow_interop.cpp`. Compile
it with `irx_record_batch.cpp`, `irx_arrow_transport.cc`, the Arrow include/link
flags, and `-fsanitize=address,undefined -fno-omit-frame-pointer`. It exercises
schema snapshots, exported lifetimes, import moves, repeated guarded releases,
EOF and corrupt-input cleanup. Arrow's prebuilt shared library itself is not
sanitizer-instrumented by this command.
