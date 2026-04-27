# Arrow-backed DataFrames

This proposal defines the first Arx DataFrame surface and its intended IRx
runtime model. It is a design document only; implementation should land in small
follow-up changes across ASTx, IRx, Arx, tests, and docs.

## Goals

- Add a public `dataframe[...]` type for heterogeneous named columns.
- Add a public `series[T]` type for typed DataFrame columns.
- Back DataFrames with Apache Arrow C++ table storage.
- Keep the first implementation read-only and intentionally small.
- Preserve the existing roles of `tensor`, Arrow arrays, and `buffer/view`.

## Non-goals

- General-purpose dictionary or record literals.
- DataFrame mutation, append, join, group-by, sort, or lazy query planning.
- Row objects and row-wise indexing.
- String, nullable, nested, temporal, or user-defined column types in the MVP.
- New Arx-owned AST node types or Arx-local lowering behavior.

## Surface design

### Builtin type

`dataframe` is a builtin type with a static schema:

```arx
dataframe[id: i32, score: f64, active: bool]
```

Rules:

- column names are identifiers;
- column names must be unique;
- column order is preserved;
- row count is runtime metadata, not part of the type;
- schema is part of the type;
- MVP column types are fixed-width numeric types and `bool`.

The first column type set should match the fixed-width Arrow primitive support
already shared by arrays and tensors where possible:

- signed integers: `i8`, `i16`, `i32`, `i64`
- floating point: `f32`, `f64`
- boolean: `bool`

Unsigned integer aliases may be added if/when the Arx surface exposes them
consistently.

Boolean columns should be supported as Arrow boolean arrays, but they should not
be assumed to be `buffer/view` compatible because Arrow stores boolean values in
bit-packed buffers.

### Public series type

`series[T]` is also public:

```arx
series[i32]
series[f64]
series[bool]
```

A series represents one typed DataFrame column. The runtime representation
should be Arrow `ChunkedArray`, even if the first implementation only creates
single-chunk columns.

### Runtime-schema form

The runtime-schema form is:

```arx
dataframe[...]
```

For the first phase, runtime-schema DataFrames are only valid in function and
extern parameter annotations. This matches the current runtime-layout rule for
tensors and keeps declaration defaults and local type checking deterministic.

The roadmap should later expand this rule consistently for every type that uses
the same runtime-layout/schema approach, including both tensors and DataFrames.

### Builtin constructor

`dataframe` is also a builtin function. The preferred constructor syntax is:

```arx
var rows: dataframe[id: i32, score: f64] = dataframe({
  id: [1, 2, 3],
  score: [0.5, 0.8, 1.0],
})
```

The `{ ... }` argument is a constructor-only column map in the MVP. It should
not imply that Arx has gained general dictionary or record literal semantics.

Constructor rules:

- the target DataFrame type must be explicit in the MVP;
- keys must be column identifiers;
- values must be column literals;
- every declared column must be present exactly once;
- no undeclared column may be present;
- all columns must have the same length;
- each column value must match its declared type.

Future type inference may allow the constructor to infer
`dataframe[id: i32, score: f64]` from the column map, but that is not required
for the first phase.

### Column access

Both static field access and string-key access should be supported:

```arx
var scores: series[f64] = rows.score
var ids: series[i32] = rows["id"]
```

Rules:

- `rows.score` is statically validated when `rows` has a known schema;
- `rows["id"]` is statically validated when the key is a string literal and the
  schema is known;
- dynamic string lookup on `dataframe[...]` runtime-schema values is deferred.

### Basic methods

The MVP should include only simple metadata queries:

```arx
rows.nrows()
rows.ncols()
```

Both should lower to Arrow table metadata queries and return integer values.

## Arrow backing

### DataFrame storage

DataFrames should wrap Arrow C++ `arrow::Table`.

`arrow::Table` is the best long-term match because it provides:

- named columns;
- a schema;
- heterogeneous column types;
- equal row count across columns;
- immutable, shareable columnar storage;
- cheap projection and slicing semantics;
- a natural base for Arrow compute integration later.

DataFrame values should lower to opaque table handles, not to `buffer/view`. A
table is heterogeneous, may contain chunked columns, and cannot be represented
as one flat layout descriptor.

### Series storage

Series should wrap Arrow C++ `arrow::ChunkedArray`.

This matches table columns directly. The first implementation may construct each
series as a single chunk from one Arrow array, but the public model should not
depend on single-chunk storage.

For later scalar indexing, a fixed-width, non-null, single-chunk series can
borrow a `buffer/view`. General chunked indexing should remain series-specific.

### Alternatives considered

`arrow::RecordBatch` : Good for import/export and literal construction, but too
narrow as the core DataFrame value because it is single-batch/single-chunk.

`arrow::StructArray` : Useful for row-like interop, but it does not model a
DataFrame as directly as `arrow::Table`.

Arrow Dataset or scanner APIs : Useful later for lazy IO and query planning, but
too high-level for the core in-memory value.

Arrow compute / Acero : Useful later for filtering, projection, joins, group-by,
and sorting. These should build on top of the table abstraction instead of
replacing it.

## ASTx and IRx work

Core nodes and semantic support should be added in ASTx/IRx first. Arx should
only parse the surface syntax and emit the IRx/ASTx facade nodes.

Suggested ASTx additions:

- `DataFrameType`
- `SeriesType`
- `DataFrameColumn`
- `DataFrameLiteral`
- `DataFrameColumnAccess`
- `DataFrameStringColumnAccess`
- `DataFrameRowCount`
- `DataFrameColumnCount`
- `DataFrameRetain`
- `DataFrameRelease`
- `SeriesRetain`
- `SeriesRelease`

Suggested semantic metadata:

- `DATAFRAME_SCHEMA_EXTRA`
- `DATAFRAME_COLUMN_INDEX_EXTRA`
- `SERIES_ELEMENT_TYPE_EXTRA`
- `SERIES_NULLABLE_EXTRA`

Each schema entry should include:

- column name;
- column type;
- nullable flag, initially always false;
- stable column index.

## Runtime ABI sketch

The Arrow runtime should add opaque table and series handles beside the existing
schema, array, and tensor handles:

```c
typedef struct irx_arrow_table_handle irx_arrow_table_handle;
typedef struct irx_arrow_chunked_array_handle
    irx_arrow_chunked_array_handle;
```

Initial C ABI:

```c
int irx_arrow_table_new_from_arrays(
    int64_t column_count,
    const char** names,
    irx_arrow_array_handle** arrays,
    irx_arrow_table_handle** out_table);

int64_t irx_arrow_table_num_rows(
    const irx_arrow_table_handle* table);
int64_t irx_arrow_table_num_columns(
    const irx_arrow_table_handle* table);

int irx_arrow_table_column_by_name(
    const irx_arrow_table_handle* table,
    const char* name,
    irx_arrow_chunked_array_handle** out_column);
int irx_arrow_table_column_by_index(
    const irx_arrow_table_handle* table,
    int32_t index,
    irx_arrow_chunked_array_handle** out_column);

int irx_arrow_table_retain(irx_arrow_table_handle* table);
void irx_arrow_table_release(irx_arrow_table_handle* table);

int irx_arrow_chunked_array_retain(
    irx_arrow_chunked_array_handle* column);
void irx_arrow_chunked_array_release(
    irx_arrow_chunked_array_handle* column);
```

The runtime should preserve existing Arrow runtime conventions:

- integer return codes;
- `irx_arrow_last_error()`;
- explicit retain/release;
- C ABI boundary over the Arrow C++ implementation;
- reuse of the shared Arrow C++ runtime source where practical.

## Lowering model

MVP lowering should support:

1. build each constructor column as an Arrow array;
2. build an Arrow table from column names and array handles;
3. lower DataFrame values to opaque table handles;
4. lower `nrows()` and `ncols()` to table metadata calls;
5. lower `df.column` and `df["column"]` to chunked-array extraction;
6. retain/release table and series handles.

Series indexing, filtering, projections, and Arrow compute integration should be
follow-up work.

## Parser and documentation impact

Arx parser updates should include:

- `dataframe[...]` type parsing;
- `series[T]` type parsing;
- runtime-schema marker parsing for `dataframe[...]`;
- constructor-only column map parsing inside `dataframe({ ... })`;
- static schema validation for duplicate, missing, and extra columns;
- field and string-key column access;
- `syntax.json` updates for the new structural form if lexer/tooling metadata
  needs to describe it.

Docs and examples should include valid Douki module docstrings in every new `.x`
file.

## Suggested rollout

1. Add ASTx and IRx type/schema nodes.
2. Add IRx semantic validation for DataFrame and Series nodes.
3. Extend the Arrow C++ runtime with table and chunked-array handles.
4. Add lowering for constructor, row/column counts, and column extraction.
5. Add Arx parser support for the surface syntax.
6. Add docs, examples, syntax manifest updates, and parser/runtime tests.

Each phase should include targeted tests before expanding the surface area.
