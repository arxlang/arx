# Parquet files and DataFrames

Import operations from **`stdlib.parquet`**, independently of CSV. Shared
`Schema`/`RecordBatch` and IPC remain in `stdlib.arrow`. All file operations use
the native Arrow/Parquet engine; compiled programs do not start Python.

## Read and write a DataFrame

````arx
```
title: Filter and copy Parquet rows
```
import (read_parquet, write_parquet, where) from stdlib.parquet

fn main() -> i32:
  ```
  title: Filter exact rows and finalize the destination
  ```
  var frame: dataframe[...] = read_parquet("events.parquet", columns=["name"], filters=where("id", ">", 10))
  write_parquet(frame, "selected.parquet", compression="zstd", atomic=true)
  return 0
````

Reads eagerly return an independently owned, chunked DataFrame and close the
reader. Writes borrow their input and return `none` only after checked
finalization. The full result must fit in memory; `batch_size` is not a total
memory limit. No RecordBatch conversion or DataFrame `.to_*` method is required.

Writes are non-atomic by default and do not append unless requested. Choose
atomic publication explicitly when existing output must survive a failed write;
see the [safe-write contract](#encryption-and-safe-writes) for its limits.

Option declarations and validation live in `irx.analysis.table_io`,
`irx.parquet_options`, and `packages/arx/src/arx/stdlib/parquet.x`. The
generated {@api python:irx:irx.table_io} reference supplies Python signatures;
the workflow and safety rules below apply to the native engine.

Explicit keywords override an options snapshot **even when equal to a default**.
Selections and filters replace, not append to, the corresponding settings. The
options owner is never mutated. Unknown parameters, empty selections and
unsupported values fail rather than falling back.

Without `options`, reads inspect the path, treating files as files and
directories as Hive-aware datasets; suffixes are irrelevant. Writes with
`partition_columns` select Hive dataset mode. Explicit `options` preserves its
existing dataset/Hive policy instead of enabling discovery automatically.

### Typed predicates and configuration

```arx
import (ParquetFilter, ParquetOptions, where) from stdlib.parquet

# Inside a function; minimum_id may be a runtime signed integer:
var predicate: ParquetFilter = where("id", ">=", minimum_id)
var both: ParquetFilter = predicate.and_where("active", "==", true)
var options: ParquetOptions = ParquetOptions(atomic=true, durable=true)
```

Comparisons are `==`, `!=`, `<`, `<=`, `>`, `>=`, with string, signed integer,
floating or Boolean values. `where("name", "is_null")` and `is_valid` omit the
value. `and_where` returns a separate group, preserving the original. Filter
columns need not be projected; nulls are excluded by ordinary comparisons.
Pruning is only an optimization, never a substitute for filtering rows. OR/IN,
serialized type tags and tuple-filter expressions are not this public API.

## Explicit streaming and ownership

Use `ParquetStream` for incremental reading or writing. It starts closed and has
one active mode. Reads advance with `next()`; false means EOF, not an empty
batch, and leaves the reader open. Current batch/frame snapshots require a
successful advance and survive reader closure. Schema snapshots are independent,
even before the first batch or after EOF.

Writers require an exact input schema, including metadata and nullability.
Schema snapshots describe that input; explicit normalization may change the
physical schema on disk. Multiple writes may share a buffered row group. Call
writer `close()` explicitly to check footer finalization. Successful close is
idempotent and permits reopening; a failed session allows cleanup only. Aliases
share session state. Wrong-mode calls fail before opening another file. Compiled
runtime failures use `ARX-RUNTIME-ARROW-001`, with typed catchable Arx
exceptions.

Batch and row-group sizes must be positive; batching bounds rows and normal
buffering, not total bytes in arbitrary values or retained frames.

See the
[basic roundtrip](https://github.com/arxlang/arx/blob/main/examples/arrow/parquet_roundtrip.x)
and
[nullable-data scan](https://github.com/arxlang/arx/blob/main/examples/arrow/parquet_nullable.x)
examples.

## Configured sessions

Arx exposes a scoped `ParquetOptions` builder. Its validated setters are copied
at open; later mutations do not change an active session:

```arx
import (ParquetStream, ParquetOptions, where) from stdlib.parquet

# Inside a function:
var options: ParquetOptions = ParquetOptions(batch_size=1024)
options.set_text("column", "name")
options.set_filters(where("id", ">", 10))
var source: ParquetStream = ParquetStream()
source.open_read_options("input.parquet", options)
```

Use `open_write_options(path, schema, options)` for writes. Unknown settings and
wrong-mode settings fail rather than being ignored. Python accepts an immutable
`ParquetOptions` value via `open_read(..., options=...)` or
`open_write(..., options=...)`; explicit convenience arguments override the
snapshot, including explicit defaults. Python `None` means no override. Arx
streaming uses the explicit `open_*_options` methods for advanced settings.

Projection and row-group selection preserve requested order; row groups are
file-only. Arx `set_text("column", ...)` and `set_int("row_group", ...)` add
selections, while eager keyword selections replace the captured selection.
Python uses checked tuples for selections and predicates. Neither surface is a
general query language. Invalid codecs, settings, or mode combinations fail
explicitly.

## Types and temporal policy

RecordBatch I/O supports:

- signed/unsigned integers of 8/16/32/64 bits, `f32`, `f64`, Boolean;
- UTF-8/large UTF-8, binary/large binary/fixed-size binary;
- decimal128/decimal256, null-typed fields;
- `date32`, `timestamp[ms/us/ns]` including timezones, `time32[ms]`,
  `time64[us/ns]`;
- recursively nested lists, large/fixed lists, structs and maps;
- Arrow dictionaries with string or binary values;
- native registered extensions with supported storage (tested with UUID/JSON);
- opaque application/Python extension storage with exact Arrow extension
  metadata. Native code does not execute Python extension callbacks. Python
  consumers can reconstruct an extension after registering its implementation.

Nulls, type parameters, field order, child names, timezones and user metadata
are retained. Dictionary codebooks/codes can be reorganized across batches; do
not treat dictionary indices as stable application identifiers. Names must be
nonempty, unique among siblings, valid UTF-8 and NUL-free. `ARROW:schema` is
reserved. Zero-column schemas and unsupported types fail explicitly.

The writer uses Parquet 2.6 and embedded Arrow schemas. Nested child names are
preserved rather than replaced with `element`. Other Parquet consumers may
ignore Arrow metadata. UTF-8 values containing NUL survive C Data/file I/O, but
the Arx scalar string getter cannot represent them.

Strict mode rejects `date64`, `timestamp[s]` and `time32[s]` on write.
`normalize=true` explicitly converts them to `date32`, `timestamp[ms]` and
`time32[ms]`, including nested fields. Safe casts reject overflow and
truncation: for example, a `date64` value not aligned to a whole day fails. The
reader reports the physical normalized type, not an invented original type.
Extension storage is never implicitly normalized.

### Explicit logical reconstruction

`reconstruct=true` on a **file or dataset writer** supports numeric dictionaries
(including decimals) and fixed-size lists with null parents. IRx writes ordinary
value columns/variable lists plus the reserved `IRX:logical_schema:v1` IPC
schema metadata. IRx readers validate that metadata against the physical schema
and restore the logical types automatically, including nested fields and
projected scans. Dictionary codebooks are rebuilt per batch; safe index casts
reject capacity overflow. Ordered dictionary reconstruction is rejected because
its codebook ordering cannot be preserved. Codes are not stable identifiers.

Dataset common metadata carries the logical schema across fragments, including
projection and atomic append. Reconstruction does not relax append schema
checks; schema evolution that changes logical-schema metadata is rejected.

Other readers see the documented physical types, not the reconstructed schema.
Use IPC when arbitrary consumers must see the exact original Arrow types. Strict
writes without this option still reject numeric dictionaries and null fixed-list
parents. Unions and list views are not supported; errors are explicit. Both
internal schema metadata keys are reserved. The scalar `BatchBuilder`/getter API
is not a recursive value API; use C Data imports and `RecordBatch.from_arrow` /
`to_arrow` for rich values.

## Datasets, evolution and filesystems

Set `dataset=true` for a directory scan and `hive=true` for `name=value`
partitions. Every fragment schema is inspected. Default mode requires matching
physical schemas. `unify=true` unions compatible fields and materializes missing
values as null. Fields missing from any fragment must be declared nullable;
conflicting physical types fail, without implicit widening. Union schemas retain
the first-seen user metadata rather than merging conflicting metadata. Expected
schemas remain assertions against the final projected scan schema.

Dataset writes require `dataset=true`, `hive=true`, and `partition_columns`.
Each input batch is written as bounded, independently finalized fragments with
fresh names. At least one non-partition column is required. `_common_metadata`
records the full schema, preserving original partition types and allowing empty
datasets. Ordinary writes require `append=true` for an existing destination and
an exact stored schema. They may leave completed fragments after a later error.

For transactional output use `atomic=true` on a local POSIX filesystem. IRx
creates immutable generations in a hidden sibling `.<name>.irx-versions`
directory and atomically switches the public dataset symlink on successful
close. IRx readers pin one generation at open, so existing readers retain a
consistent view during replacement. Only new destinations or managed snapshot
symlinks are accepted, not existing ordinary directories. Subsequent writes to a
snapshot must also use `atomic=true`.

Snapshot append retains old fragments and adds new ones. With `append=true`,
`atomic=true`, `unify=true`, incoming schemas can add or omit **nullable**
fields; shared fields must have identical types, nullability and metadata. There
is no implicit widening or required-field synthesis. Read evolved datasets with
`unify=true`. Existing immutable fragments are hardlinked, not rewritten.

Old generations are deliberately retained for active readers. There is no
automatic garbage collector: remove unreachable generations only after all
readers have closed. Never edit a published generation or its hardlinked files.
External readers can follow the public symlink, but only IRx readers implement
generation pinning. This is a local commit protocol, not an object-store table
format or distributed transaction.

Decimal128/256 and floating-point partition keys preserve their declared types.
Decimal paths are parsed with checked Arrow decimal conversion rather than
floating-point intermediates. Floating keys must be finite and cannot be
negative zero: equality grouping cannot preserve those values exactly.

Hive names cannot contain `/`, backslash, `=` or `%`. The string value
`__HIVE_DEFAULT_PARTITION__` is reserved for nulls. Other strings are
URI-escaped. Recorded schemas preserve partition types, column order and
metadata.

Paths and URIs use Arrow's filesystem implementations. Local paths and `file://`
are tested; cloud schemes work only when the installed Arrow build and its
credential providers support them. Unsupported backends fail, never fall back to
a local filename. Live cloud-provider integration is not covered by local tests.
Use credential providers, not credentials embedded in paths or source code.

## Encryption and safe writes

File and dataset encryption use Parquet AES footer-key encryption. Each dataset
fragment gets fresh encryption properties; the schema footer is encrypted too.
Python accepts `ParquetOptions(encryption_key=key_bytes)` with a 16/24/32-byte
key. Arx accepts `options.encryption_key_hex(runtime_key)` with 32/48/64
hexadecimal digits. Use runtime-provided secrets; never commit real keys in
examples or source. The same key is needed to read encrypted data. Missing/wrong
keys fail. Native option copies use Arrow's secure string storage; caller-owned
Python/Arx values remain the caller's responsibility. KMS integration, rotation
and per-column keys are outside this interface.

`atomic=true` writes a securely created sibling temporary file and replaces the
destination only after successful finalization. Abandoning a Python context or
releasing an unfinished writer does not commit it. Single-file `append=true`
streams the existing file into a new temporary output and then adds new batches;
it never concatenates Parquet files. Both operations currently require a **local
POSIX filesystem**. Local writers hold a nonblocking advisory lock for their
entire session, including the old-data read in append. A second cooperating
writer fails with a busy error before truncation. Locks are released on close,
abort, failure or process death. Hidden lock files are intentionally persistent;
do not delete them while writers may exist. Coordination is by canonical path,
not hardlink identity, and does not exclude non-IRx writers.

`durable=true` requires atomic replacement or file rewrite append. It fsyncs
completed data and directories before/after publication. A failure **after**
publication (for example the final directory fsync) can report an error while
the new data is already visible; its durability is then uncertain. Abrupt
process death can leave unpublished temporaries/generations. Durability still
depends on the local filesystem/device honoring fsync.

Without atomic mode, later I/O failures can leave partial output. Options/schema
validation precedes truncation, but data-dependent failures cannot all be
detected at open time. Missing codecs fail instead of falling back. Batching
bounds normal buffering, not bytes consumed by arbitrarily large values or file
metadata.

## DataFrame conversion

Use the shared
[checked conversion contract](collections.md#checked-dataframe-conversion) and
[parameterized schema rules](collections.md#parameterized-static-dataframe-schemas).
A static cast is an exact assertion, never implicit physical conversion or
projection. Runtime-schema frames preserve supported rich Arrow data without
inferring static column types. Format normalization/reconstruction rules above
still apply when those frames are written to Parquet.

## Python example

```python
from irx.table_io import read_parquet, write_parquet, where
from irx.record_batch import ParquetOptions

frame = read_parquet("input.parquet", columns=["name"],
                     filters=where("id", ">", 10))
write_parquet(frame, "output.parquet", compression="zstd",
              options=ParquetOptions(atomic=True))
```

These helpers return/accept `pyarrow.Table`, accept `PathLike` paths and
`pyarrow.Schema` assertions, and use the native C Stream bridge. No Python
format engine is substituted. For streaming, `irx.record_batch.ParquetStream`
remains available. Its iteration releases a batch on advancement. Use
`next_batch()` and explicit `release()` when retaining the native batch longer;
exported `to_arrow()` values own independent references. Low-level
`open_parquet` factories remain available. Import does not build native code.
CSV/IPC use the base ctypes library; Parquet loads a separate on-demand plugin
linked to that same base instance. `IRX_RECORD_BATCH_LIBRARY` overrides retain
the legacy all-in-one ABI contract.

IRx registers `parquet` separately from `record_batch`. The base feature links
Arrow and Compute for nullable kernels. Parquet additionally links matching
Parquet, Dataset and Acero libraries. Arx resolves the canonical bundled
modules, but lowers only resolved reachable declarations (whole referenced
classes, including destructors). CSV-only programs no longer activate or link
Parquet.
