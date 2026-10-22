# CSV files and DataFrames

`stdlib.arrow` provides native Arrow CSV streaming. There is no Python
subprocess, custom CSV parser, or whole-file load hidden behind these APIs. A
C++ toolchain is required, as for the existing Arrow APIs.

## Arx API

- `CSV().open_read(path, delimiter=",", header=true, block_size=1048576)` infers
  a schema from the first block and freezes it for subsequent batches.
- `reader.open_read_as(path, schema, delimiter=",", header=true, block_size=1048576)`
  uses an explicit `Schema`. Names, order, count, physical types and
  non-nullable fields are checked; no columns are silently dropped.
- `reader.next()` advances one batch. `false` means EOF, not an empty batch.
  `reader.batch()` and `reader.schema()` return independent snapshots.
- `CSV().open_write(path, schema, delimiter=",", header=true)` creates or
  truncates a file after validating options/schema. `write(batch)` requires an
  exact schema, including nullability and metadata. `close()` reports final
  write errors. Successful close is idempotent; close before reopening.

`CSV()` starts closed and has one active read or write session, like
[`Parquet`](parquet.md). `schema()` works in either open mode. Wrong-mode or
closed data access is an error; aliases observe the same state. Read/write
failures invalidate the session, and cleanup does not hide the original error.
Use two instances and distinct paths for copying. `block_size` is a positive
signed 32-bit **byte** count, unlike Parquet's row-based `batch_size`.

### Migrating the split API

`CSVReader` and `CSVWriter` remain supported compatibility classes, with their
existing constructors, `open_file`/`open_file_as` methods and handle accessors.
For new code, use `CSV`:

- `CSVReader().open_file(...)` becomes `CSV().open_read(...)`.
- `reader.open_file_as(...)` becomes `file.open_read_as(...)`.
- `CSVWriter(schema)` becomes `CSV()`, and `writer.open_file(path, ...)` becomes
  `file.open_write(path, schema, ...)`.

Existing CSV parsing and scalar-type support are unchanged. In particular, CSV
explicit schemas control text parsing, whereas Parquet expected schemas only
assert the types already encoded in the file.

CSV RecordBatches support signed/unsigned integer widths, `f32`, `f64`, Boolean,
UTF-8/large UTF-8, dates, timestamps and time units. Nested and other
unsupported Arrow types produce errors. CSV itself does not encode schema
metadata: use an explicit schema to preserve widths and temporal units on a
roundtrip.

## Checked DataFrame conversion

````arx
```
title: CSV batch conversion
```
import (CSV, RecordBatch) from stdlib.arrow

fn main() -> i32:
  var reader: CSV = CSV()
  reader.open_read("input.csv")
  while reader.next():
    var batch: RecordBatch = reader.batch()
    var frame: dataframe[id: i64] = cast(batch, dataframe[id: i64])
    batch.close()
    var copy: RecordBatch = cast(frame, RecordBatch)
    print(copy.nrows())
  reader.close()
  return 0
````

Both conversions produce independent owners. DataFrames and Series are scoped
references: aliases, parameters, returned values and local replacements retain
what they need; normal exits, loop exits and returns release local ownership.
The input need not remain open. No Arrow C++ layout is exposed in LLVM.

Conversion requires a nonempty static schema of **`i8`, `i16`, `i32`, `i64`,
`f32`, `f64`, or `bool`**, with exact column names, order and physical types.
Every batch must have **zero actual null values**. A nullable Arrow field is
accepted when this batch has no nulls; the resulting DataFrame is non-nullable.
There is no implicit narrowing, reordering, null filling or pointer cast.
Initialize an output CSV writer from the converted batch's schema or a matching
non-nullable explicit schema, not the original inferred nullable schema.

Strings, unsigned values, temporals and nullable columns can remain in a
RecordBatch. Conversion errors name the offending column and suggest keeping
that representation or using a matching explicit CSV schema. Nullable/string/
temporal DataFrames are follow-up work. Fixed-row-count conversion targets,
owned globals, aggregate fields/containers, generators and general public FFI
passing of DataFrames/Series are not supported. Arrow locals require
initializers.

See [`examples/arrow/csv_roundtrip.x`](../../examples/arrow/csv_roundtrip.x) for
CSV writing, explicit schemas and processing **every** batch. Run it from the
repository root with
`arx examples/arrow/csv_roundtrip.x --output-file csv-roundtrip`, then
`./csv-roundtrip`. It reads the bundled `examples/arrow/input.csv` and creates
`output.csv`; never use the same file for input and output.

## Text and failure contract

- UTF-8, LF output records; quoted multiline fields and doubled quotes work.
- Delimiters are exactly one ASCII byte, excluding NUL, double quote, CR and LF.
  Tab is supported. Reader block size must be a positive signed 32-bit integer;
  very large records may require increasing it.
- Only **unquoted empty fields** are null. Quoted `""` is an empty string; `NA`
  and `NULL` are literal strings. Blank one-column rows are null rows, not
  skipped records. Malformed multi-column widths fail.
- Headers must be nonempty and unique. Headerless typed reads use schema names;
  inferred headerless names are `f0`, `f1`, etc. Typed header-only input
  succeeds; completely empty files fail. Inferred null/binary columns require an
  explicit supported schema or corrected input.
- No remote URLs, compression, append, encoding detection or malformed-row
  skipping. A later batch can fail after earlier batches have been written.
  Output is **partial on failure**, not transactional.
- Compiled failures use `ARX-RUNTIME-ARROW-001`; they are not catchable Arx
  exceptions. CSV row numbers are not fabricated as Arx source locations.

## Python API

```python
from irx.record_batch import (
    IrxColumnType, RecordBatchSchema,
    CSV,
)

schema = RecordBatchSchema().add_field("id", IrxColumnType.INT64, False)
with CSV() as reader, CSV() as writer:
    reader.open_read("input.csv", schema=schema)
    writer.open_write("output.csv", schema)
    for batch in reader:
        writer.write_batch(batch)
schema.release()
```

The opening methods accept the same delimiter/header options and reading accepts
`block_size`. Omit `schema` to infer. Existing Python iterator ownership
applies: iteration releases each yielded batch when advancing; use
`next_batch()` and explicit `release()` when a batch must outlive advancement or
reader closure. An old native-library override without CSV symbols reports a
rebuild/unset message instead of silently changing implementation.

The lower-level `RecordBatchStreamReader.open_csv` and
`RecordBatchStreamWriter.open_csv` factories remain compatible. Python
`schema()` returns an independent flat-schema snapshot; release it explicitly.
