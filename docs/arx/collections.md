# Collections and Apache Arrow

Arx exposes four built-in collection families with deliberately different
semantics:

| Surface type     | Purpose                                            | Runtime representation                 |
| ---------------- | -------------------------------------------------- | -------------------------------------- |
| `list[T]`        | General ordered values and builtin `range` results | IRx dynamic-list runtime               |
| `tensor[T, ...]` | Homogeneous N-dimensional numeric data             | Apache Arrow C++ `arrow::Tensor`       |
| `dataframe[...]` | Heterogeneous named columns                        | Apache Arrow C++ `arrow::Table`        |
| `series[T]`      | One typed DataFrame column                         | Apache Arrow C++ `arrow::ChunkedArray` |

`list` is not an Arrow container. Tensor, DataFrame, and Series storage is
provided by IRx's native Arrow C++ runtime.

## Lists

```arx
fn sum_values() -> i32:
  var values: list[i32] = range(0, 4)
  var total: i32 = 0
  for value in values:
    total = total + value
  return total
```

The current dynamic-list runtime supports creation, append/growth, length, and
indexed access. Produced storage is process-lifetime until explicit list release
semantics are added.

## Tensors

Fixed-shape tensors use one or more integer dimensions:

```arx
fn pick(grid: tensor[i32, 2, 2]) -> i32:
  return grid[1, 0]

fn main() -> i32:
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  return pick(grid)
```

Rules:

- supported elements: `i8`, `i16`, `i32`, `i64`, `f32`, and `f64`
- literals must be rectangular and match the declared shape
- indexing supplies one index per static dimension
- variables, fields, and returns require at least one static dimension
- Tensor storage is readonly in the current implementation

`tensor[T, ...]` accepts runtime shape/stride metadata at a function or extern
parameter boundary:

```arx
fn accept(values: tensor[i32, ...]) -> none:
  return none
```

Passing the value through is supported. Dynamic indexing is not yet available,
so indexed access requires a static-shape annotation.

## DataFrames and Series

```arx
fn main() -> i32:
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  var scores: series[f64] = rows.score
  var ids: series[i32] = rows["id"]
  print(rows.ncols())
  return cast(rows.nrows(), i32)
```

Rules:

- columns are fixed-width numeric or Boolean
- the constructor accepts list-literal columns with equal row counts
- names and types must match the declared static schema
- statically known columns use `rows.name` or `rows["name"]`
- `nrows()` and `ncols()` return `i64`
- `dataframe[...]` is accepted as a runtime-schema parameter type, but its
  columns cannot yet be accessed by name

For nullable, UTF-8, date, timestamp and time columns, import `Schema`,
`BatchBuilder`, `RecordBatch`, `IPCReader` and `IPCWriter` from `stdlib.arrow`.
These ordinary classes retain runtime Arrow schemas without weakening static
DataFrame types. Conversion is explicit: `cast(batch, dataframe[id: i64])` and
`cast(frame, RecordBatch)` validate exact types and reject actual nulls. `CSV`
and `Parquet` use the same batch API with explicit read/write sessions. See
[CSV files and DataFrames](csv.md) and
[Parquet files and DataFrames](parquet.md) for format-specific restrictions and
examples. Legacy `CSVReader`/`CSVWriter` remain available for compatibility.

`IPCReader.next()` advances one batch; `batch()` and `schema()` return
independent snapshots. `open_file` selects IPC file format, `open_stream`
selects streaming format at a path, and `connect` exchanges IPC streaming bytes
over TCP. Writers reject schema mismatches, including metadata and nullability.
Check `is_null` before typed getters. Objects close on their last scoped
reference; explicit `close()` is idempotent. See the
[complete API and tested examples](../apache-arrow.md#compiled-arx-interoperability-stdlib.arrow).

## Runtime boundary

IRx activates native Arrow features only when lowering requires them. Generated
LLVM calls opaque C ABI functions; Arrow C++ object layouts and ownership do not
leak into LLVM structs or Arx syntax.

See [Native Apache Arrow Support](../apache-arrow.md) for arrays, Arrow C Data,
RecordBatch IPC, and current interoperability details.
