# Runtime Features

IRx lowers ASTx nodes to LLVM IR, but container ownership, system libraries, and
other native capabilities belong in runtime code rather than handwritten LLVM
implementations. Runtime features declare those capabilities and activate them
per compilation unit.

## Activation model

A runtime feature can contribute:

- external symbol declarations
- C or C++ sources
- prebuilt object files or static libraries
- include paths, compiler flags, and linker flags
- metadata describing its ABI and dependencies

Lowering requests a feature-owned symbol with
`require_runtime_symbol(feature, symbol)`. That request activates the feature,
reuses its declaration within the LLVM module, and makes its native artifacts
available to the final link. Inactive features contribute nothing.

Registered features:

| Feature        | Responsibility                                       |
| -------------- | ---------------------------------------------------- |
| `libc`         | `puts`, checked allocation, formatting, and `free`   |
| `file`         | Checked single-owner POSIX UTF-8 text files          |
| `libm`         | math symbols and the platform math linker flag       |
| `assertions`   | fatal assertion helper and machine-readable reports  |
| `errors`       | fatal checked-runtime diagnostics and stable records |
| `buffer`       | buffer-owner and view lifetime helpers               |
| `list`         | minimal dynamic list creation, growth, and indexing  |
| `array`        | one-dimensional Apache Arrow array runtime           |
| `tensor`       | homogeneous N-dimensional Arrow Tensor runtime       |
| `dataframe`    | Arrow Table and ChunkedArray runtime                 |
| `record_batch` | Arrow RecordBatch and IPC/CSV streaming              |
| `parquet`      | Parquet files/datasets; depends on `record_batch`    |

The runtime layer is independent of Arx imports. Importing a source module and
activating a native feature are different compiler operations.

## Extern declarations

Public extern prototypes can name `runtime_feature` or `runtime_features`.

- a plain extern emits an LLVM declaration and relies on the platform linker
- a feature-backed extern also activates the feature's artifacts and flags
- a symbol already owned by a feature reuses the feature declaration rather than
  creating a parallel native path

This is the same mechanism used by built-in lowering; it is not a special path
only for handwritten externs.

## Native Apache Arrow backend

IRx uses a C++ wrapper with an opaque C ABI. Arrow C++ containers remain opaque
to generated LLVM. The RecordBatch bridge currently reports ABI version 1; other
native surfaces remain pre-production contracts.

```text
ASTx collection node
  -> IRx lowering
  -> irx_arrow_* or irx_rb_* C ABI call
  -> Arrow C++ container and ownership
```

`pyarrow` and `arx-arrowcpp-sources` provide Arrow C++ library, include, source,
and linker metadata. Native feature builds use that metadata rather than
vendoring a second Arrow implementation in IRx.

## Array runtime

The `array` feature provides:

- opaque schema, builder, and array handles
- signed and unsigned 8-, 16-, 32-, and 64-bit integers
- `float32`, `float64`, and Boolean storage
- explicit build, inspect, retain/release, import, and export operations
- Arrow C Data copy import, move/adopt import, and export
- nullable-array metadata and validity-bitmap inspection
- readonly projection of byte-addressable fixed-width value buffers into
  `irx_buffer_view`

Boolean arrays are valid Arrow handles but are not projected through the generic
buffer view because Arrow stores Boolean values as packed bits.

### Import and export ownership

- copy import leaves the caller's Arrow C Data ownership unchanged
- move/adopt import transfers ownership on success and leaves the input moved
  from
- export produces an independent Arrow C Data pair that the caller releases
- bridged buffer views are borrowed and readonly; callers keep the array handle
  alive

Generic buffer operations stay null-agnostic. Code that needs null semantics
must inspect the Arrow handle and validity bitmap explicitly.

## Tensor runtime

The `tensor` feature stores homogeneous N-dimensional data in `arrow::Tensor`:

- fixed-width numeric element types
- shape, stride, rank, offset, and contiguous-layout metadata
- indexing through the canonical `irx_buffer_view` descriptor
- shallow metadata-only views over shared storage
- explicit external-owner lifetime tracking

Arrow-backed Tensor storage is readonly in the current phase. Dynamic-rank
validation, broadcasting, reductions, tensor algebra, and source-language
slicing are not part of this layer.

## DataFrame and Series runtime

The `dataframe` feature provides:

- DataFrames backed by `arrow::Table`
- Series views backed by `arrow::ChunkedArray`
- numeric, Boolean, string and nullable column construction
- checked RecordBatch conversion for unsigned and supported temporal columns
- static column-index resolution during semantic analysis
- row and column count queries
- explicit retain/release operations

This native layer supports the current Arx `dataframe[...]`, `dataframe({...})`,
and `series[T]` surface. Focused checked Arrow Compute kernels implement
numeric/Boolean nullable expressions, broadcasting, null tests/filling and
bounds-checked scalar access. This is not a query planner. Runtime code keeps
Arrow objects behind opaque handles; nullable language scalars carry only a
validity bit and a fixed-width primitive value.

## RecordBatch runtime

The `record_batch` feature and `irx.record_batch` Python API provide a separate
streaming/interoperability layer:

- schema construction with nullable fields
- batch builders and scalar inspection
- signed/unsigned integers, `float32`, `float64`, and `bool`
- UTF-8 and large UTF-8 strings
- `date32`, `date64`, timestamp units, `time32`, and `time64`
- null append and inspection
- Arrow IPC stream readers/writers for files and memory buffers
- multiple batches per stream
- interoperability in both directions with PyArrow

The Python API uses a standalone ctypes-loaded shared library. Ensure a current
source/toolchain-fingerprinted build before direct use:

```bash
python -c "from irx.builder.runtime.record_batch import ensure_record_batch_shared_library; ensure_record_batch_shared_library()"
```

Generated libraries live in an ABI-scoped user cache rather than the installed
package tree. Set `IRX_NATIVE_CACHE_DIR` to select the cache root or
`IRX_RECORD_BATCH_LIBRARY` to load/build one exact path. Concurrent builders use
an OS-managed file lock that is released if its owner terminates, outputs are
replaced atomically, and the loader rejects a missing or mismatched ABI query
before binding other symbols.

This is RecordBatch IPC support, not an implementation of the Arrow C Stream
`ArrowArrayStream` interface.

## Assertions

The `assertions` feature owns `__arx_assert_fail(...)`. On failure it writes one
escaped, machine-readable line to `stderr` and exits nonzero:

```text
ARX_ASSERT_FAIL|<source>|<line>|<column>|<message>
```

Python helpers under `irx.builder.runtime.assertions` parse this protocol for
the Arx test runner.

## Dynamic list caveat

The `list` runtime supports checked append/growth, indexed access, and an
idempotent destroy helper. Semantic ownership sidecars classify scalar dynamic
lists as owned, borrowed, or static and record borrow/move/return boundaries.
Lowering destroys owned locals and non-transferred temporaries on lexical
fallthrough, return, `break`, and `continue`, while excluding storage moved to a
caller. Borrowed/static copies, append through borrowed storage, owned list
locals in generators, owning list elements, and object-field ownership remain
unsupported.

## String lifetime caveat

String literals and empty defaults are immutable static pointers. Heap strings
from concatenation, numeric formatting, and defined Arx string-returning calls
carry semantic owner/copy/move metadata. Lowering guards allocation and
formatting failure with `ARX-RUNTIME-STRING-001` or `ARX-RUNTIME-STRING-002`,
frees non-transferred temporaries and owned locals, releases the old generation
on owned replacement, and moves return cleanup to the caller. Static-to-owned
return uses a checked heap copy.

The preview intentionally rejects borrowed parameter escape, static/owned
storage-class changes, owned string fields and generator locals, redundant
identity casts of owned strings, and external string results without an explicit
ownership ABI.

## Deliberate limits

IRx currently does not provide:

- direct Arrow C++ types in generated LLVM IR
- a complete Arrow type system
- the Arrow C Stream `ArrowArrayStream` interface
- general nested, dictionary, decimal, or extension-type support
- a source-language module system inside the runtime layer
- DataFrame query semantics or a general compute-kernel API

See [Native Apache Arrow Support](../apache-arrow.md) for the cross-project view
and [Buffer View Model](buffer-view-model.md) for the low-level descriptor.

## Text file runtime

The `file` feature exposes opaque `irx_file_*` handles and caller-owned error
buffers (`IRX_FILE_ERROR_CAPACITY` bytes). Open/read/write outputs are
initialized on all paths and may be consumed only after a zero status. EOF is a
successful empty string. Read buffers transfer to the caller and use the
existing `free` string ABI. Malformed UTF-8 and interior NUL are rejected. Close
is idempotent; release consumes the wrapper even when closing fails. Handles are
synchronous, single-owner, and not thread-safe. Lowering activates `errors` when
status guards are emitted and `libc` when returned strings require cleanup;
dependencies do not depend on passive feature metadata.

See [Arx Text File I/O](../arx/file-io.md) for the intentionally restricted
parameter and lifetime surface. The native header is the C ABI contract.

## Class Lifetime Feature

The registered `class` feature packages a C99 runtime and header. It provides
checked create/retain/release/require operations, compiler-only phase progress,
and first-error aggregation. Creation initializes the output slot to null before
failure; lowering reads it only on success. An opaque token in payload slot zero
holds counts/progress and a generated concrete drop callback. Final release
consumes both allocations even if a native field release fails. Counts are
non-atomic and no public external ownership ABI is promised. See
[Class Model](class-model.md) for the supported acyclic subset.

### Parquet linkage

Parquet adapters are registered separately from the base RecordBatch runtime.
Array/tensor linker flags are unchanged; matching PyArrow libraries are used,
not system Arrow. Availability is checked when a feature is activated.

The `CSVStream` and `ParquetStream` facades use distinct nominal opaque handles
and a shared checked session lifecycle; raw reader/writer ABI entrypoints remain
additive and compatible. New sources, headers and library flags participate in
native-cache fingerprinting and wheel asset audits. See
[Parquet I/O](../arx/parquet.md) for type and DataFrame restrictions.

## Optional Parquet feature

`parquet` now declares an explicit dependency on `record_batch`; its separate
native artifacts link matching `libparquet`, `libarrow_dataset`,
`libarrow_compute` and `libarrow_acero`. The base RecordBatch feature has no
Parquet dependency. Runtime activation validates dependency availability/cycles
before activating anything (`R003`/`R004`).

Python loads the base RecordBatch library for CSV/IPC and a separately cached
Parquet plugin on demand. The plugin links the same base instance so handles and
thread-local errors are not duplicated. Explicit library overrides retain the
legacy bundled-symbol contract.

Arx opts its bundled `stdlib.arrow` into declaration reachability: analysis
still validates every declaration, while lowering retains referenced classes
(including all methods/destructors) and resolved dependencies. Other modules
remain eager by default. CSV-only programs therefore do not activate Parquet.
See [format contracts](../arx/parquet.md) for transactional datasets, durable
local writes, reconstruction and runtime-schema DataFrames.

Series runtime primitives also provide checked unary kernels, common-type
promotion, null-skipping reductions, bounded slices and failure-atomic element
updates. Slice results own independent handles; updates replace a handle's
column without modifying the originating table. Rich literal construction copies
validated IPC data into owned Arrow storage. These operations are registered
with the existing DataFrame runtime feature and do not activate Parquet.

## Tabular I/O capabilities

Hosts register actual bundled declarations with `NativeBinding.table_io` and
canonical classes with `ParsedModule.native_arrow_classes`. IRx validates the
prototype and resolves optional argument presence, canonical handle fields,
source-order evaluation, selectors and ownership into a `TableIOCall` sidecar.
Lowering consumes that plan. Matching a function/class name never grants these
privileges; arbitrary DataFrame FFI remains rejected. CSV uses `record_batch`,
while Parquet configuration and file operations activate `parquet` lazily.

The native `irx_rb_reader_read_table`, `irx_rb_writer_write_table`,
`irx_rb_table_schema`, `irx_rb_table_project` and `irx_rb_table_cast` APIs
borrow inputs. Read/project/cast outputs own independent references and are null
on failure. Release tables with `irx_arrow_table_release`, schemas with
`irx_rb_schema_release`. Reads close their internal reader before returning;
writes check finalization and release unfinished writers without committing.

`irx_arrow_table_export_stream` requires a released/zeroed `ArrowArrayStream`
output and gives it independent ownership. `irx_arrow_table_import_stream`
consumes the C Stream and drains it without combining chunks. An unconsumed
stream must be released, including failure paths. The Arrow runtime uses its own
status/error channel; check that before reading outputs, independently of the
record-batch status channel. Python `irx.table_io` installs all ctypes
signatures lazily and scopes every handle/stream. Missing symbols in explicit
native overrides require rebuilding/unsetting the override, not fallback.
