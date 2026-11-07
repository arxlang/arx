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
sum_values: fn() -> i32:
  values: list[i32] = [0, 1, 2 + 1]
  values.append(4)
  assert len(values) == 4
  total: i32 = 0
  for value in values:
    total = total + value
  return total
```

Dynamic lists are move-only: owned locals and non-transferred temporaries are
released on normal and exceptional lexical exits and replacement; returning an
owned list moves it to the caller. A list moved into a pending return cannot be
read or reassigned through that binding in `finally`; a separate fresh owned
return value is allowed. Parameters borrow storage and cannot append or return
that borrow. Borrowed lists keep their exact element type: passing `list[i32]`
to a `list[i64]` parameter does not convert the existing storage.

While a `for ... in` loop borrows a list, replacing that owner binding anywhere
in the body is a compile-time ownership error (`IRX-S013`), including nested
branches and exception clauses. Move the replacement after the loop or build a
different list inside it; distinct shadowed bindings remain independent. Unlike
Python, Arx does not retain the original list object across rebinding. In-place
`append` remains allowed on owned locals, but iteration keeps its initial
length, so appended elements are not visited. Returning the owner from the loop
still moves it to the caller.

Bracket expressions evaluate once, left to right, and produce owned lists; only
an explicit fixed-shape tensor target selects tensor storage. An explicit list
target types fresh literal elements first. Otherwise all elements must have a
common lossless domain, independent of order. Empty lists need a target, for
example `values: list[i64] = []`. Nested owned lists remain unsupported.

`len(values)` returns `i64`; narrowing it requires a checked `cast`. String
insertion copies the bytes, and indexing or iterating a string list produces
independent strings that survive list replacement. Failed construction drops
initialized elements without replacing an existing destination. See the
[enforced list contract](../irx/runtime-ownership.md#enforced-scalar-dynamic-list-contract).
`range` still materializes a list, not a lazy iterator. Rank-one numeric tensors
and typed Series also support `len`.

## Read-only numeric consumers

`sequence[T]` is a **parameter-only borrow**, not a new owning container. Like
Python's `collections.abc.Sequence`, it offers ordered iteration, integer
indexing, and `len -> i64`. Unlike Python sequences, negative indices, slicing,
Boolean elements, and implicit element conversions are not supported. Numeric
elements are signed/unsigned 8-64-bit integers or `f32`/`f64`.

```arx
@<T: i32 | i64 | f64>
first: fn(values: sequence[T]) -> T:
  return values[0]
```

Pass a matching `list[T]` (including `range`), rank-one static/runtime tensor,
or typed numeric Series directly. No flattening or conversion to `f64` occurs;
large integers remain exact. Nullable Series require `sequence[nullable[T]]`:
explicitly fill or filter nulls for a nonnullable consumer. NaN and infinity
remain floating values; algorithms needing finite input must check them. See the
executable `examples/numeric-sequences.x` for inferred/explicit calls, nested
template types, and nullable input.

Adapters live through the call or iteration, including exceptional exits. Lists
borrow their owner; tensors pin their owner and preserve strides; Series retain
independent zero-copy chunk snapshots so subsequent alias replacement does not
invalidate the view. Sequence descriptors cannot be returned, stored, captured
by a generator, reassigned, or used to mutate the source. Materialize an owned
result instead:

```arx
owned: list[i64] = list(values, max_items=1000)
```

`list(input, max_items=N)` copies nonnullable numeric values once. Sized inputs
may omit the bound; exceeding a supplied nonnegative bound raises `ValueError`
without publishing a truncated list. Allocation sizes remain overflow-checked.
Nullable storage is deliberately not supported in owned lists; fill/filter
first.

IRx single-pass generators are **not** sequences and require `max_items`.
Materialization probes at most `N + 1` items to detect excess, releasing partial
output and owned temporary frames on failure. Consumption is not rolled back.
Named iterators are borrowed from their lexical owner and remain advanced after
failure. Arx source-level generator declarations are still unsupported; this
iterator workflow is available to ASTx/IRx hosts, not new Arx `yield` syntax.

## Tensors

Fixed-shape tensors use one or more integer dimensions:

```arx
pick: fn(grid: tensor[i32, 2, 2]) -> i32:
  return grid[1, 0]

main: fn() -> i32:
  grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  return pick(grid)
```

Rules:

- supported elements: signed/unsigned 8-64-bit integers, `f32`, and `f64`
- literals must be rectangular and match the declared shape
- indexing supplies one index per static dimension
- variables, fields, and returns require at least one static dimension
- Tensor storage is readonly in the current implementation

`tensor[T, ...]` accepts runtime shape/stride metadata at a function or extern
parameter boundary:

```arx
accept: fn(values: tensor[i32, ...]) -> none:
  return none
```

Indexing uses runtime rank, shape, strides, and offset. All indices must be
nonnegative and in bounds, including dynamic indices into static-shaped tensors.
Rank mismatch and invalid metadata fail before reading; byte-offset arithmetic
is overflow-checked. Rank-one tensors also support `len` and ordered iteration.

## DataFrames and Series

```arx
main: fn() -> i32:
  rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  scores: series[f64] = rows.score
  ids: series[i32] = rows["id"]
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
[interoperability workflow and ownership contract](../apache-arrow.md#compiled-arx-interoperability-stdlib-arrow).

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
main: fn() -> i32:
  frame: dataframe[x:i32 | none] = dataframe({x:[1, none, 3]})
  doubled: series[i32 | none] = frame.x + frame.x
  missing: nullable[i32] = doubled[1]
  assert is_null(missing)
  assert fill_null(doubled[2], 0) == 6
  filled: series[i32] = fill_null(doubled, 7)
  assert filled[1] == 7
  empty: nullable[i32] = none
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
Word `not` binds below comparisons, as in `not frame.x == 3`; see the
[Boolean evaluation contract](specification.md#boolean-evaluation). Remainder
`%` is scalar-only and is rejected for nullable values and Series.
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
