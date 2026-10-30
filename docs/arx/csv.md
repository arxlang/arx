# CSV files and DataFrames

Import CSV operations from **`stdlib.csv`**. Shared Arrow schemas, batches and
IPC remain in `stdlib.arrow`; CSV is backed by Arrow C++, not a Python process
or a second parser. The native Arrow libraries and a C++ toolchain are required.

## Read and write a DataFrame

````arx
```
title: Copy a CSV file
```
import (read_csv, write_csv) from stdlib.csv

fn main() -> i32:
  ```
  title: Read every row and finalize the output
  ```
  var frame: dataframe[...] = read_csv("input.csv")
  write_csv(frame, "output.csv")
  return 0
````

These eager functions close their internal session before returning. Reads
return an independent, chunked DataFrame; writes borrow the frame without
consuming or mutating it. Temporary inputs such as
`write_csv(read_csv("input.csv"), "output.csv")` are supported. The result must
fit in memory: `block_size` controls parsing blocks, not total memory. Writers
return `none` only after checked finalization. There are no DataFrame `.to_*`
methods or `to_*` aliases. Never copy a file onto itself using streaming
sessions.

### Parsing policy

An omitted schema is inferred from the first block, then frozen. For headerless
input, supply a schema or explicit names; `names` requires `header=false` and no
schema. Projections must be nonempty and unique and preserve requested order.
`null_values` replaces token recognition; an empty list disables it. These
choices affect interpretation, not just performance.

The eager option schema lives in `irx.analysis.table_io`; defaults and
validation are implemented by the native CSV options code. Python signatures are
in the generated {@api python:irx:irx.table_io} reference. Stream declarations
and contracts live in `packages/arx/src/arx/stdlib/csv.x`.

Arx name/column/token arguments are literal lists, not arbitrary iterable
objects. Unknown options and unsupported types fail explicitly. Delimiter, quote
and escape bytes must not conflict; NUL, CR and LF are not valid dialect
characters. Output quoting uses Arrow's fixed double-quote convention; this is
not a complete Python `csv` dialect engine.

CSV projection happens **after full input validation and conversion**. A bad
unselected field still fails. Explicit schemas check header names/order/count
and nullability; they control parsing rather than merely asserting types.

## Checked DataFrame conversion

```arx
import Schema from stdlib.arrow
import read_csv from stdlib.csv

# Inside a function:
var schema: Schema = Schema()
schema.add("id", "int64", nullable=false)
var loaded: dataframe[...] = read_csv("ids.csv", schema=schema)
var ids: dataframe[id:i64] = cast(loaded, dataframe[id:i64])
```

Runtime schemas do not infer compile-time column types. The cast above asserts
an exact schema; it does not project or coerce data. See the shared
[checked DataFrame conversion contract](collections.md#checked-dataframe-conversion)
for nullability, chunk validation, metadata, and ownership restrictions.

CSV supports integer widths, floating point, Boolean, UTF-8/large UTF-8, dates,
timestamps and time units. Nested/other unsupported types fail; use Parquet or
IPC for those. CSV does not encode type/schema metadata. Supply an explicit
schema to preserve widths and temporal units on a roundtrip.

## Explicit streaming

Use `CSVStream` for incremental processing instead of loading the entire file
into a DataFrame. It supports either read or write mode.

```arx
import CSVStream from stdlib.csv

# Inside a function:
var source: CSVStream = CSVStream()
source.open_read("large.csv")
while source.next():
  var chunk: dataframe[...] = source.frame()
  print(chunk.nrows())
source.close()
```

`CSVStream()` starts closed and has one read or write mode.
`open_read_as(path, schema, ...)` supplies an explicit schema;
`open_write(path, schema, ...)` configures output. These session factories
expose delimiter/header and read block size. The additional dialect controls
above belong to the eager functions.

`next()` advances; false means EOF, not an empty batch. `frame()` snapshots the
current batch without advancing and survives reader closure. It fails before a
successful `next()` or after EOF. `write(frame)` and `write(batch)` require an
exact schema. `batch()` and `schema()` remain available for Arrow
interoperability. Call writer `close()` explicitly to observe finalization
errors; automatic cleanup alone is not proof of success. Wrong-mode access
fails, aliases share session state, and failed sessions cannot be reused.

The
[streaming roundtrip example](https://github.com/arxlang/arx/blob/main/examples/arrow/csv_roundtrip.x)
processes every batch. The
[table example](https://github.com/arxlang/arx/blob/main/examples/arrow/csv_parquet_tables.x)
converts CSV to Parquet using only the module-level functions.

## Text and failure contract

- UTF-8 and quoted multiline fields are supported. By default only unquoted
  empty fields are null. Quoted `""` remains an empty string; `NA` and `NULL`
  remain text unless configured in `null_values`.
- Custom `na_rep` requires matching read `null_values`. Non-null unquoted data
  equal to a null marker is ambiguous; a lossless roundtrip is not guaranteed.
- Blank one-column rows remain null rows unless explicitly skipped. Malformed
  record widths fail; `skiprows` does not enable malformed-row skipping.
- Headers must be nonempty and unique. Typed header-only input succeeds;
  completely empty files fail. Inferred null/binary columns need an explicit
  supported schema or corrected input.
- CSV has no remote URLs, compression/encoding discovery, append or atomic
  writes. Validation precedes truncation, but later data/I/O failures can leave
  partial output. A failed eager read never returns a partial table.
- Compiled failures use `ARX-RUNTIME-ARROW-001`, with typed catchable Arx
  exceptions. CSV row positions are not invented as Arx source locations.

## Python integration

```python
from irx.table_io import read_csv, write_csv

frame = read_csv("input.tsv", delimiter="\t", columns=["id", "name"])
write_csv(frame, "output.csv")
```

These functions return/accept `pyarrow.Table`, accept string or `PathLike`
paths, and use IRx native sessions/C Stream interchange, not Python format
engines. Use `pyarrow.Schema` for `schema`. Selectors accept checked sequences.
Imports do not compile native code; CSV-only use does not load Parquet, Dataset
or Acero. Stale native-library overrides produce a rebuild/unset error.

For streaming, `irx.record_batch.CSVStream` and the lower-level
`RecordBatchStreamReader.open_csv` / `RecordBatchStreamWriter.open_csv` remain
available. Iteration releases its batch on advancement; `batch.to_arrow()`
exports independent Arrow references. Release manually retained batch/schema
snapshots explicitly.
