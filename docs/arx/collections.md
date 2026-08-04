# Collections and Apache Arrow

Arx currently exposes four related collection families with deliberately
different semantics:

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

The lower-level IRx RecordBatch API already supports nullable, UTF-8, date,
timestamp, and time columns. Those capabilities are not yet part of the Arx
DataFrame language surface.

## Runtime boundary

IRx activates native Arrow features only when lowering requires them. Generated
LLVM calls opaque C ABI functions; Arrow C++ object layouts and ownership do not
leak into LLVM structs or Arx syntax.

See [Native Apache Arrow Support](../apache-arrow.md) for arrays, Arrow C Data,
RecordBatch IPC, and current interoperability details.
