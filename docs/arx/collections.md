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

Dynamic lists are move-only: owned locals and non-transferred temporaries are
released on normal and exceptional lexical exits and replacement; returning an
owned list moves it to the caller. A list moved into a pending return cannot be
read or reassigned through that binding in `finally`; a separate fresh owned
return value is allowed. Parameters borrow storage and cannot append or return
that borrow. Literal-list views are non-owning and cannot escape into dynamic
owners or call arguments. See the
[enforced list contract](../irx/runtime-ownership.md#enforced-scalar-dynamic-list-contract)
for the ownership boundary. `range` currently materializes a list, not a lazy
iterator.

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

- columns support signed/unsigned numeric, Boolean and string values
- nullable columns use `T | none`; date/time/timestamp columns can be populated
  through literal constructors or checked RecordBatch conversions
- the constructor accepts list-literal columns with equal row counts; it does
  not add implicit signed-to-unsigned coercion
- names and types must match the declared static schema
- statically known columns use `rows.name` or `rows["name"]`
- `nrows()` and `ncols()` return `i64`
- `dataframe[...]` supports runtime-schema locals, parameters and returns,
  preserving rich Arrow types/metadata through RecordBatch casts; its columns
  cannot be accessed statically by name or silently narrowed

Use `read_csv` / `write_csv` from `stdlib.csv` and `read_parquet` /
`write_parquet` from `stdlib.parquet` for file I/O. Reads return independently
owned runtime-schema frames; writes borrow frames and check finalization. No
format-specific DataFrame methods or `to_*` aliases are added. `CSVStream` and
`ParquetStream` in those modules support explicit streaming via `frame()` and
`write(frame)`.

`Schema`, `BatchBuilder`, `RecordBatch` and IPC remain in `stdlib.arrow`. File
workflows and format-specific safety limits live in [CSV](csv.md) and
[Parquet](parquet.md); exact casts follow the shared conversion contract below.

`IPCReader.next()` advances one batch; `batch()` and `schema()` return
independent snapshots. `open_file` selects IPC file format, `open_stream`
selects streaming format at a path, and `connect` exchanges IPC streaming bytes
over TCP. Writers reject schema mismatches, including metadata and nullability.
Check `is_null` before typed getters. Objects close on their last scoped
reference; explicit `close()` is idempotent. See the
[interoperability workflow and ownership contract](../apache-arrow.md#compiled-arx-interoperability-stdlib.arrow).

## Checked DataFrame conversion

`cast(frame, dataframe[id:i64])` and `cast(batch, dataframe[id:i64])` assert
exact names, order, physical types, and every chunk's reachable nullability.
They do not project, coerce, fill nulls, or infer compile-time types. Metadata
and independent ownership are preserved; `cast(frame, RecordBatch)` bridges back
to batch APIs. Runtime-schema frames preserve rich Arrow data without permitting
unchecked static column access.

Fixed-row-count casts, owned globals, generator locals, aggregate-owned fields,
and arbitrary DataFrame FFI are unsupported. See
[parameterized schemas](#parameterized-static-dataframe-schemas) for nested
nullability and exact physical parameters. File-format restrictions still apply
independently of what an in-memory frame can hold.

## Runtime boundary

IRx activates native Arrow features only when lowering requires them. Generated
LLVM calls opaque C ABI functions; Arrow C++ object layouts and ownership do not
leak into LLVM structs or Arx syntax.

See [Native Apache Arrow Support](../apache-arrow.md) for arrays, Arrow C Data,
RecordBatch IPC, and current interoperability details.

## Nullable scalars and Series expressions

`nullable[T]` stores a fixed-width numeric or Boolean scalar plus a validity
bit. A nullable column is spelled `series[T | none]`. Indexing a nullable column
returns `nullable[T]`; indexing a non-nullable column returns `T`. Indices are
zero-based; negative or out-of-range indices fail at runtime.

````arx
```
title: Nullable column expressions
```
fn main() -> i32:
  var frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3]})
  var doubled: series[i32 | none] = frame.x + frame.x
  var missing: nullable[i32] = doubled[1]
  assert is_null(missing)
  assert fill_null(doubled[2], 0) == 6
  var filled: series[i32] = fill_null(doubled, 7)
  assert filled[1] == 7
  var empty: nullable[i32] = none
  assert is_null(empty)
  return 0
````

Supported operators are `+`, `-`, `*`, `/`, `==`, `!=`, `<`, `<=`, `>` and `>=`.
Numeric operands use IRx common-type promotion. Column casts are checked; values
that cannot be represented by the promoted type fail explicitly. Series/scalar
operations broadcast the scalar. Series/Series operations require equal lengths.
Integer arithmetic is checked: overflow and division by zero fail instead of
wrapping. Null operands produce null outputs, including comparisons. Boolean
`&&`/`and` and `||`/`or` propagate nulls strictly, not with Kleene semantics.
These operations are eager, not short-circuiting.

`is_null` returns `bool` for a nullable scalar or a non-nullable Boolean Series
mask. `fill_null(value, replacement)` eagerly evaluates a matching non-null
scalar replacement and returns a non-nullable scalar or Series. Nullable scalars
cannot implicitly become non-nullable values or conditions. Nullable scalar
globals support numeric/Boolean literal or `none` initializers. Direct `none` is
accepted in nullable declarations, assignments, returns, and function
arguments/defaults. It never implicitly fills a non-nullable value.

These scalar operations currently cover `i8`–`i64`, `u8`–`u64`, `f32`, `f64` and
`bool`. String, temporal, decimal and nested Series retain their data and schema
but cannot yet be indexed into language scalars or used in these operators.
Unary `+` and checked `-` support signed numeric values; Boolean `!`/`not`
invert validity-preserving masks. Unsigned negation requires an explicit cast.
`column[start:stop:step]` follows Python's bound clipping and negative-stride
rules; omitted bounds are allowed and a zero step fails. Slicing, `is_null` and
`series_count` also work on rich column storage.

`series_sum`, `series_min`, `series_max`, `series_mean`, `series_any` and
`series_all` skip nulls and return nullable scalars: empty/all-null input has a
null result. `series_count` returns the non-null count as `i64`. Integer sums
use checked `i64`/`u64` accumulators; floating sums and means return `f64`.
Boolean reductions require Boolean columns.

`column[index] = value` updates a mutable numeric/Boolean Series binding with
bounds, type and nullability checks. Aliases of that handle observe updates; the
originating DataFrame and previously computed/sliced Series do not. Construction
completes before publication, so failed updates leave the old column intact.
Concurrent access to a mutated handle is unsupported. Updates are statements,
not value-producing assignment expressions.

Returned Series own independent references; temporary columns and aliases are
released by normal scope-lifetime cleanup.

## Parameterized static DataFrame schemas

Checked RecordBatch casts additionally accept:

- `decimal128[precision, scale]` and `decimal256[precision, scale]`.
- `timestamp["unit"]`, `timestamp["unit", "timezone"]`, and `time["unit"]`, with
  units `s`, `ms`, `us` or `ns`.
- `binary`, `binary[positive_size]`, `large_binary`, and `large_string`.
- `arrow_list[T]`, `large_list[T]`, and `fixed_list[T, positive_size]`.
- `dictionary[index_type, value_type]` (unordered).
- `arrow_map[key_type, value_type]` and `arrow_struct[name:T, ...]`.

For example,
`dataframe[amount:decimal128[12, 3] | none, items:arrow_list[nullable[i32]] | none]`
declares nullable decimal and list columns. Nested children are non-nullable
unless wrapped in `nullable[T]`; this wrapper models child nullability even for
types that cannot be language scalars. Map keys cannot be nullable.

Rich schemas work in aliases, parameters, returns and checked RecordBatch casts.
Casts check names, order, exact physical parameters and nested nullability;
non-nullable top-level columns also check actual batch null counts. They do not
rescale decimals, change time units, or decode dictionaries implicitly. Input
schema and field metadata are preserved.

Unparameterized `time` uses time64 microseconds; `timestamp`/`datetime` use
timezone-naive timestamp microseconds. Their text literal constructors accept
whole seconds without timezone or fractional components. Use parameterized
storage or checked Arrow imports for other units or zones.

Rich DataFrame literals use the declared schema rather than inference. Decimal
cells use exact strings or integers (not binary floats); binary cells use UTF-8
strings, with fixed widths checked in bytes. Parameterized temporal cells use
integer storage units, without timezone conversion. Lists use nested lists;
structs use positional lists matching declared field order; maps use lists of
`[key, value]` pairs. Dictionaries encode literal values with checked index
capacity. Nested nullability, widths, precision, scale and shape are validated
during semantic analysis. Lowering embeds validated Arrow IPC bytes, not a
Python interpreter or handwritten serialization format. Standalone rich scalar
variables remain unsupported.
