# IRx

IRx is the semantic-analysis, LLVM-lowering, and native-runtime layer of the
ArxLang ecosystem. Its distribution is `pyirx`, while its Python import is
`irx`.

> Status: functional experimental backend. The supported subset is broad but
> does not cover every ASTx node.

## Current capabilities

- module-graph expansion, imports, scopes, symbols, and resolved sidecars
- scalar typing, numeric promotion, casts, functions, templates, and FFI
- structured control flow, assertions, and diagnostics
- class layout, inheritance, method resolution, and dispatch metadata
- buffer views, dynamic lists, arrays, tensors, DataFrames, and Series
- LLVM IR translation, object emission, native linking, and execution
- on-demand C/C++ runtime feature compilation
- native Apache Arrow arrays, `arrow::Tensor`, `arrow::Table`,
  `arrow::ChunkedArray`, and RecordBatch IPC

## Arrow support

IRx keeps Arrow C++ ownership behind opaque C ABI handles. Generated LLVM calls
IRx runtime symbols rather than reproducing Arrow layouts in IR.

The public RecordBatch Python API supports schemas, builders, nullable values,
numeric and Boolean columns, UTF-8/large UTF-8, date/time/timestamp values, IPC
file and memory streams, and PyArrow interoperability.

See [Runtime Features](runtime-features.md) and
[Native Apache Arrow Support](../apache-arrow.md).

## Boundary

IRx does not parse source languages or define a query language. ASTx owns the
node model; frontends own syntax; IRx owns semantic meaning and lowering.
