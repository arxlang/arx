# Parquet files and DataFrames

`Parquet` in `stdlib.arrow` is a scoped, native Arrow file owner. It reads all
columns and row groups incrementally and writes buffered row groups. There is no
Python subprocess or whole-file Table load in compiled programs. As with
[CSV](csv.md), a C++ toolchain and PyArrow's matching native libraries are
required.

## Arx API

- `Parquet()` creates a closed owner.
- `file.open_read(path, batch_size=65536)` opens a local seekable file using its
  decoded Arrow schema. `batch_size` is a positive `i64` row limit, not a byte
  size or a guarantee that batches match row groups.
- `file.open_read_as(path, schema, batch_size=65536)` additionally checks exact
  column names, order, types, nullability and metadata. Unlike CSV's explicit
  schema, this is an **assertion**, not a conversion request.
- `file.next()` advances a batch in read mode; `false` means EOF, not an empty
  batch. `file.batch()` returns an independently owned current batch.
- `file.open_write(path, schema, compression="snappy", row_group_size=1048576)`
  validates schema/options before creating or truncating a file. The positive
  `i64` row-group limit may split a batch or combine several input batches.
- `file.write(batch)` requires write mode and an exact schema, including
  metadata/nullability. Non-nullable fields cannot contain actual nulls.
- `file.schema()` returns an independent schema snapshot in either open mode,
  including before the first batch and for a valid zero-row file.
- `file.close()` finalizes the footer in write mode and reports errors.
  Successful close is idempotent and permits reopening in either mode.

An instance has only one active session. Close before opening another file or
changing mode. Reading from a writer, writing to a reader, or accessing data
while closed produces an error. Aliases observe the same session state; batch
and schema snapshots survive reader advance/closure. EOF leaves read mode open.
After a read/write/finalization failure, only cleanup is allowed; use a new
instance. Use **two instances and distinct paths** when copying a file.

See
[the self-contained roundtrip example](../../examples/arrow/parquet_roundtrip.x),
which creates input, processes every batch through a checked DataFrame, writes
output and verifies the row count. Run from a writable directory:

```bash
arx examples/arrow/parquet_roundtrip.x --output-file parquet-roundtrip
./parquet-roundtrip
```

It creates `parquet-input.parquet` and `parquet-output.parquet`.

## Types and format restrictions

Supported flat RecordBatch fields are signed/unsigned integers of all four
widths, `f32`, `f64`, Boolean, UTF-8/large UTF-8, `date32`,
`timestamp[ms/us/ns]` (including timezones), `time32[ms]`, and `time64[us/ns]`.
Nulls and user schema/field metadata are preserved on Arrow-backed roundtrips.
Names must be nonempty, unique, valid UTF-8 and NUL-free; zero-column schemas
are rejected. Embedded NUL in string **values** survives native/C Data I/O,
although the Arx scalar string getter cannot represent it.

The writer uses Parquet 2.6 with embedded Arrow schema metadata, without INT96
or timestamp coercion/truncation. `ARROW:schema` is reserved; user collisions
are rejected. Other consumers may ignore embedded Arrow metadata and expose
different types.

`date64`, `timestamp[s]` and `time32[s]` writes are rejected because Arrow
normalizes their types in Parquet, even with schema storage enabled. Convert
explicitly to a supported type first, or use IPC for an exact representation.
External files expose their actual decoded Arrow types, not a reconstruction of
unavailable original types.

Nested, binary, decimal, Arrow dictionary-array, extension and null-typed fields
are not supported by this API. Errors identify the offending column/type.
Parquet's dictionary **encoding** of supported columns is allowed. Additional
logical types are follow-up work, not silently cast or skipped.

Write compression is `"snappy"`, `"uncompressed"` or `"zstd"`; missing codecs
fail rather than fall back. Readers can decode codecs available in the installed
Arrow build. There is no projection/filter pushdown, dataset/directory API,
remote filesystem, append, encryption or atomic replacement. Memory use follows
batch/row-group buffering, but large values and footer metadata prevent a strict
byte-memory bound.

Validation precedes truncation, but later I/O failures can leave a partial,
unreadable file without a complete footer. Explicit close is essential;
destructor cleanup does not promise a successful write. Compiled failures use
`ARX-RUNTIME-ARROW-001` rather than catchable Arx exceptions.

## Checked DataFrame conversion

Use the existing `cast(batch, dataframe[...])` and `cast(frame, RecordBatch)`.
As with CSV, conversion requires exact names/order/types, a nonempty static
schema of signed `i8/i16/i32/i64`, `f32/f64` or `bool`, and **zero actual
nulls** in each batch. A nullable input field with no actual nulls is accepted,
but the resulting DataFrame is non-nullable. Configure output from the converted
batch's schema or a matching explicit schema, not the original nullable footer
schema. Arbitrary input metadata is not preserved through a statically declared
DataFrame. Nullable, unsigned, string and temporal DataFrames remain follow-up
work; keep such data as RecordBatches. See
[conversion ownership](csv.md#checked-dataframe-conversion).

## Python API

```python
from irx.record_batch import Parquet

with Parquet() as source, Parquet() as target:
    source.open_read("input.parquet", batch_size=65536)
    schema = source.schema()
    try:
        target.open_write("output.parquet", schema, compression="zstd")
    finally:
        schema.release()
    for batch in source:
        target.write_batch(batch)
```

Python uses `next_batch()` (returning a batch or `None`) and `write_batch()`.
Iteration releases each yielded batch on advancement; use `next_batch()` with
explicit `release()` if a batch must outlive advancement/reader closure. Schema
snapshots support flat fields and retain metadata/timezones.
`open_read(..., schema=...)` asserts an exact schema. Sizes reject booleans and
values outside positive signed 64-bit range before ctypes conversion.

The lower-level `RecordBatchStreamReader.open_parquet` and
`RecordBatchStreamWriter.open_parquet` factories remain available. Importing the
API does not build native code. A configured old library lacking Parquet symbols
reports a rebuild/unset message only when those symbols are needed. The
RecordBatch runtime now links PyArrow's `libparquet` as well as `libarrow`,
including for CSV/IPC users; scalar/array/tensor linker flags are unchanged.
