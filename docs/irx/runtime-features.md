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
| `libm`         | math symbols and the platform math linker flag       |
| `assertions`   | fatal assertion helper and machine-readable reports  |
| `errors`       | fatal checked-runtime diagnostics and stable records |
| `buffer`       | buffer-owner and view lifetime helpers               |
| `list`         | minimal dynamic list creation, growth, and indexing  |
| `array`        | one-dimensional Apache Arrow array runtime           |
| `tensor`       | homogeneous N-dimensional Arrow Tensor runtime       |
| `dataframe`    | Arrow Table and ChunkedArray runtime                 |
| `record_batch` | Arrow RecordBatch and IPC streaming bridge           |

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
- fixed-width numeric and Boolean column construction
- static column-index resolution during semantic analysis
- row and column count queries
- explicit retain/release operations

This native layer supports the current Arx `dataframe[...]`, `dataframe({...})`,
and `series[T]` surface. It does not provide query planning or Arrow Compute
kernels.

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
