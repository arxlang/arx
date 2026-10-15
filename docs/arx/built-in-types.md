# Built-in Types

Arx has a small set of built-in types that can be used in variable annotations,
function parameters, and function return types. This page is the reference for
their canonical spellings, accepted aliases, and current surface syntax.

## Overview

| Canonical type               | Accepted aliases | Category   | Example                                               | Notes                                    |
| ---------------------------- | ---------------- | ---------- | ----------------------------------------------------- | ---------------------------------------- |
| `i8`                         | `int8`           | integer    | `var a: i8 = 8`                                       | 8-bit integer                            |
| `i16`                        | `int16`          | integer    | `var b: i16 = 16`                                     | 16-bit integer                           |
| `i32`                        | `int32`          | integer    | `var c: i32 = 32`                                     | 32-bit integer                           |
| `i64`                        | `int64`          | integer    | `var d: i64 = 64`                                     | 64-bit integer                           |
| `f16`                        | `float16`        | float      | `var x: f16 = 1.5`                                    | 16-bit float                             |
| `f32`                        | `float32`        | float      | `var y: f32 = 3.25`                                   | 32-bit float                             |
| `f64`                        | `float64`        | float      | `var z: f64 = 9.5`                                    | 64-bit float                             |
| `bool`                       | `boolean`        | boolean    | `var ok: bool = true`                                 | Uses `true` and `false` literals         |
| `none`                       | —                | unit       | `fn log() -> none:`                                   | Also the single value of the `none` type |
| `str`                        | `string`         | text       | `var s: str = "hi"`                                   | UTF-8 string                             |
| `char`                       | —                | text       | `var ch: char = 'A'`                                  | Currently mapped to `i8`                 |
| `datetime`                   | —                | temporal   | `datetime("2026-03-05T12:30:59")`                     | Constructor-style literal form           |
| `timestamp`                  | —                | temporal   | `timestamp("2026-03-05T12:30:59Z")`                   | Constructor-style literal form           |
| `date`                       | —                | temporal   | `var d: date`                                         | Recognized as a built-in type name       |
| `time`                       | —                | temporal   | `var t: time`                                         | Recognized as a built-in type name       |
| `list[T]`                    | —                | collection | `var ids: list[i32] = [1, 2, 3]`                      | Generic collection type                  |
| `tensor[T, N]`               | —                | collection | `var ids: tensor[i32, 4] = [1, 2, 3, 4]`              | Fixed-shape 1D numeric tensor            |
| `tensor[T, d0, d1, ..., dN]` | —                | collection | `var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]`      | Fixed-shape multidimensional tensor      |
| `tensor[T, ...]`             | —                | collection | `fn sink(values: tensor[i32, ...]) -> none:`          | Runtime-shaped tensor parameter          |
| `dataframe[name: T, ...]`    | —                | collection | `var rows: dataframe[id: i32] = dataframe({id: [1]})` | Static-schema DataFrame                  |
| `dataframe[...]`             | —                | collection | `fn sink(rows: dataframe[...]) -> none:`              | Runtime-schema DataFrame owner           |
| `series[T]`                  | —                | collection | `var ids: series[i32] = rows["id"]`                   | Typed DataFrame column                   |

## Numeric Types

Arx accepts both short canonical names and longer aliases in type annotations:

- integers: `i8`, `i16`, `i32`, `i64`
- integer aliases: `int8`, `int16`, `int32`, `int64`
- floats: `f16`, `f32`, `f64`
- float aliases: `float16`, `float32`, `float64`

```arx
fn numeric_demo(a: int32, b: float32) -> f64:
  var count: i64 = 64
  return cast(a, f64) + cast(b, f64)
```

## `none`

`none` is the built-in unit type and also the single value of that type. Use it
for functions that do not return a meaningful result.

```arx
fn log_message() -> none:
  print("ok")
  return

fn done() -> none:
  return none

var marker: none = none
```

For `-> none` functions:

- the return type annotation is still mandatory
- bare `return` returns `none`
- reaching the end of the function also implicitly returns `none`

## Text Types

Use `str` for strings and `char` for single-byte character values.

```arx
fn text_demo() -> none:
  var greeting: str = "hello"
  var initial: char = 'A'
  return none
```

`char` currently maps to `i8`, so it should be treated as a low-level character
representation rather than a separate rich text type.

## Temporal Types

Arx currently documents constructor-style surface syntax for `datetime` and
`timestamp` values.

```arx
fn time_demo() -> none:
  var dt: datetime = datetime("2026-03-05T12:30:59")
  var ts: timestamp = timestamp("2026-03-05T12:30:59.123456789")
  return none
```

The parser also recognizes `date` and `time` as built-in type names in
annotations.

## Collections, tensors, and dataframes

Arx exposes the following public collection type families:

- `list[T]` for generic collection values
- `tensor[T, N]` for fixed-shape 1D numeric tensors
- `tensor[T, d0, d1, ..., dN]` for fixed-shape multidimensional tensors
- `tensor[T, ...]` for runtime-shaped tensor parameters
- `dataframe[name: T, ...]` for static-schema named-column DataFrames
- `dataframe[...]` for runtime-schema DataFrame owners
- `series[T]` for typed DataFrame columns

In the fixed-shape form, `...` is documentation prose for additional integer
dimensions. The literal `...` marker is reserved for runtime-shaped tensor
parameters and runtime-schema DataFrame owners.

The naming is intentional: Arx uses `Tensor` for homogeneous N-dimensional data,
aligning with common data-science terminology and IRx's Arrow C++ backed
runtime. `DataFrame` is the heterogeneous named-column abstraction backed by
Arrow C++ `Table`, and `Series` is the one-dimensional typed column view backed
by Arrow C++ `ChunkedArray`.

```arx
fn tensor_demo() -> none:
  var names: list[str] = ["a", "b"]
  var ids: tensor[i32, 4] = [1, 2, 3, 4]
  var grid: tensor[i32, 2, 2] = [[1, 2], [3, 4]]
  print(names[0])
  print(ids[2])
  print(grid[1, 0])
  return none
```

Current tensor rules in this phase:

- element types are fixed-width numeric types (`i8`, `i16`, `i32`, `i64`, `f32`,
  or `f64`)
- variable, field, and return tensor annotations must declare at least one
  static shape dimension
- `tensor[T, ...]` is accepted only in parameter annotations; it means the
  element type is static and the shape/layout is runtime metadata
- literals must be rectangular and match the declared static shape
- indexing uses one index per declared static dimension
- indexing runtime-shaped tensor parameters is rejected until dynamic tensor
  indexing is supported by IRx
- current lowering is read-only and is focused on literal/default-initialized
  shaped tensors

Current DataFrame rules in this phase:

- column types include primitive numeric/Boolean values, `str`, nullable values,
  and executable logical `scalar[T]` values (including nested types)
- static-schema values use `dataframe[name: T, ...]` annotations and the
  column-oriented `dataframe({...})` constructor
- constructor columns must be list literals, use declared column names, and have
  equal row counts
- columns can be accessed as `rows.score` or `rows["score"]`
- `rows.nrows()` and `rows.ncols()` return row and column counts as `i64`
- column access and metadata methods currently work on DataFrame identifiers and
  literals whose schema is known while parsing, not on arbitrary
  DataFrame-returning expressions
- `dataframe[...]` is an owned runtime-schema value in locals, calls, returns
  and instance fields; checked column access uses
  `column_as(to_table(rows), index, field[name: T])` rather than unchecked
  legacy field access

```arx
fn dataframe_demo() -> i32:
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  var scores: series[f64] = rows.score
  var ids: series[i32] = rows["id"]
  return cast(rows.nrows(), i32)
```

## Type-aware builtins

Use the built-in `cast(value, type)` helper to convert values between supported
types.

```arx
fn cast_demo(a: i32) -> str:
  return cast(a, str)
```

Use `isinstance(value, type)` to compare the static semantic type of a value
with a concrete type, type alias, or finite union type.

```arx
type Number = i32 | i64

fn check(value: i32) -> bool:
  return isinstance(value, Number)
```

Use `type(value)` to produce the value's semantic type name as `str`.

```arx
type Count = i32

fn type_name(value: Count) -> str:
  return type(value)
```

## See Also

- [Data Types](datatypes.md) for annotation rules and placement
- [Collections and Apache Arrow](collections.md) for runtime storage and current
  collection limits
- [Functions](functions.md) for function signatures and returns

## Arrow-core descriptors

`datatype`, `field`, and `schema` are builtin, shared immutable values. They
need an initializer and can be passed to and returned from functions. No Arrow
import or namespace is required:

```arx
fn describe() -> schema:
  return schema[id: i64, label: string | none]
```

Use `datatype[i64]`, `field[id: i64]`, and `schema[id: i64]` to construct them;
`schema_field`, `field_name`, `field_type`, `field_nullable`, and
`descriptor_equal` inspect them.
[Logical types and schemas](../arrow-type-schemas.md) documents all literal
parameters and query contracts. The 45 logical descriptor families do not imply
executable arrays or scalar values for every Arrow type.

## Primitive nullable scalars

`T | none` is a builtin nullable value, not a library wrapper. The Arx source
payload types are `bool`, signed `i8`–`i64`, unsigned `u8`–`u64`, and
`f16`–`f64`, including their long aliases. Unsigned initializers follow existing
lossless conversion rules; use an explicit `cast` when conversion is required.

````arx
```
title: Explicit nullable validity
```
fn widen(value: i32 | none = none) -> i64 | none:
  ```
  title: Preserve nulls while widening valid values.
  ```
  return value

fn main() -> i32:
  ```
  title: Inspect validity before requesting a payload.
  ```
  var count: i32 | none = none
  assert is_null(count)
  count = 0
  assert is_valid(count)
  assert expect_valid(widen(count)) == 0
  return 0
````

- `is_null(value)` and `is_valid(value)` return non-nullable `bool` values. They
  require a typed nullable operand, not a bare `none` or ordinary scalar.
- `expect_valid(value)` returns the payload type. A null operand causes a fatal
  `ARX-RUNTIME-NULL-001` diagnostic before any payload extraction; current
  function owners are cleaned up. This is not recoverable error handling or
  stack unwinding.
- A payload or explicit `none` can initialize or update a nullable value.
  Nullable arguments, defaults, copies and returns preserve validity. Existing
  whole-domain lossless numeric widening rules also apply to nullable payloads.
- Nullable-to-non-nullable assignment requires proven validity or an explicit
  `expect_valid`. Source nullable locals require an explicit initializer.
  `return none` returns a missing value; bare `return` remains a void return,
  and a void call is not a null value.
- Zero and `false` are valid payloads, not null sentinels. IRx stores validity
  separately in a language-owned LLVM `{i1, payload}` aggregate. It does not
  expose Arrow C++ layouts or allocate an Arrow scalar object for these locals.

Arithmetic (`+`, `-`, `*`, `/`, `%`), unary signs, and comparisons propagate
null. Integer division/remainder check zero divisors and signed overflow only
when both operands are valid. `!`, `and`/`&&`, and `or`/`||` use three-valued
logic: false AND unknown is false; true OR unknown is true; otherwise unknown
propagates. Decisive valid left operands short-circuit the right expression. A
nullable Boolean is not implicitly a branch condition.

Direct `is_valid(x)` and `!is_null(x)` true branches, and `is_null(x)` false
branches, refine a local or argument to its payload type. Assignment invalidates
the proof; joins intersect surviving facts and loop backedges discard inherited
facts. `while is_valid(x)` re-establishes its proof on every iteration. Guarded
right operands such as `is_valid(x) and x > 0` are supported. Pure compound
AND/OR/negation conditions combine guaranteed facts: a true conjunction proves
both sides, while a true disjunction retains only facts shared by both paths.
Opaque calls and mutation expressions do not establish compound proofs.

`cast(value, T | none)` preserves validity while explicitly converting primitive
payloads. A null payload is never converted. `cast(none, T | none)` constructs
an absent primitive value. Use `expect_valid` to remove nullability before
casting to a non-nullable type. Narrowing follows existing primitive cast rules,
not a new checked Arrow Compute cast policy.

`str | none`, `dataframe[...] | none`, and `series[T] | none` support guarded
access, copies, returns and managed instance fields. Present empty text or empty
containers are distinct from absence. Strings clone owned storage; columnar
containers retain independent handles. These owner operations do not imply
nullable arithmetic on strings or containers. General nullable language
collection elements, managed by-value struct fields and C FFI nullable
signatures remain unsupported and fail before lowering.

## First-class arrays

Arrow arrays are ambient builtins: no Arrow import or namespace is required.
`array[T]` excludes null elements; `array[T | none]` admits them. Both are
immutable shared owners with explicit retain/release semantics on copies and
returns. Construction is `array[T](value, ...)`, including empty arrays.
Primitive elements are Boolean, signed/unsigned 8/16/32/64-bit integers, and
16/32/64-bit floats. The logical scalar section below describes variable-width,
temporal, decimal and recursive elements. Narrow or signed-to-unsigned inputs
require explicit casts; `array[i8](300)` is rejected rather than truncated.

The closed builtin operations are:

- `array_length(a)`, `array_null_count(a)`, `array_offset(a)` return `i64`.
- `array_at(a, index)` always returns a nullable scalar, even for a nonnullable
  array. Native status and validity are checked before reading the payload.
- `array_slice(a, offset, length)` returns a zero-copy view with independent
  ownership; negative or out-of-range bounds fail rather than clamp.
- `array_concat(a, b)` materializes one array; operands must have matching
  logical element and nullability types.
- `array_copy(a)` explicitly rebuilds buffers and resets the offset to zero.
- `array_equal(a, b)` returns `bool`, using Arrow value equality including null
  positions; matching static array types are required. Generic scalar operators
  such as `a == b` and `++a` are rejected for columnar owners; opaque handles
  are never interpreted as strings or numeric scalar storage.

Null counts follow element validity: union and run-end values inspect logical
children rather than a nonexistent parent bitmap. Dictionary validity belongs to
its index; a valid index can reference a null dictionary value.

Boolean values retain Arrow's bit packing. Sliced values and validity bitmaps
honor nonzero offsets. Scalar iteration is explicit: loop over indices and call
`array_at`; no implicit row/batch/column iteration is selected.

See [`examples/columnar_arrays.x`](../../examples/columnar_arrays.x) for
executable construction, nullable access, slicing, copying, concatenation and
owner returns. `array_from_buffer(tensor)` copies a rank-one numeric buffer into
an independent nonnullable array. It accepts positive/negative strides and empty
views, rejects byte-packed Boolean/half storage and bitmap-bearing views, and
checks dimensions and arithmetic overflow before reading. IRx hosts can also
supply typed `BufferViewType` values. The caller of the low-level native ABI
must supply readable buffer storage; the view has no allocation-size field. Raw
external C Data pointers stay native; the owned `c_data` boundary described
below exposes checked source-level import/export.

## Reusable builders and chunked arrays

`array_builder[T]()` creates a unique mutable typed builder. Assignment cannot
alias an existing builder; functions may borrow it. `builder_append(b, value)`
accepts its declared element type, including explicit `none` only for a nullable
builder. `builder_reserve(b, additional)` reserves additional capacity; negative
values and size overflow fail. `builder_length(b)` returns `i64`.
`builder_finish(b)` publishes an immutable array and resets the builder for
reuse **only after success**. Allocation or nullability failure leaves the
builder's existing values available for retry at the native ABI boundary. Arx
source currently reports native errors through its fatal diagnostic path.

`chunked_array[T](a, b, ...)` borrows arrays of exactly the declared logical and
nullability type; it creates an independent shared owner. Empty sequences and
empty chunks are valid. `chunk_count(c)` returns `i64`; `chunk_at(c, index)`
returns an independently owned array view. Use an explicit index loop for chunk
iteration. There is no single physical offset for a chunked array.

`array_length`, `array_null_count`, `array_at`, `array_slice`, `array_concat`,
`array_copy`, and `array_equal` also accept matching chunked arrays. Scalar
access crosses chunk boundaries without reading null payloads. Chunked
concatenation preserves chunks; copy rebuilds buffers while preserving chunk
boundaries. Equality compares values independent of chunk boundaries.
`combine_chunks(c)` explicitly materializes one contiguous array, including an
empty typed array for zero chunks. There is no implicit rechunking.

Half-float arrays use Arrow's IEEE binary16 storage. The native scalar boundary
converts numerically through double, not by reinterpreting half bits as an
integer. Half-float tensor/buffer-view exposure is not enabled by this support.

See [`examples/columnar_builders.x`](../../examples/columnar_builders.x).
`chunked_array` is currently distinct from the legacy DataFrame `series` type;
no implicit conversion or complete Series API is claimed.

## Nullable resource owners

`scalar[T] | none`, `array[T] | none`, `chunked_array[T] | none`,
`ClassName | none`, `datatype | none`, `field | none`, and `schema | none`
support local storage, reassignment, default arguments, borrowing, copying,
returns and checked extraction. An empty valid array still has an owner and is
**not** `none`. The backend reserves a null owner pointer for absence; it never
calls native retain on that pointer. Release accepts an empty slot, so cleanup
remains safe on both paths. Primitive scalar nullable values retain their
independent validity/payload representation.

Use `expect_valid` or a direct predicate refinement before querying the owner.
Borrowed extraction does not invalidate its parent, and copying or returning a
shared extraction retains independent ownership. `array_builder[T] | none` also
supports absence, borrowing, replacement and moved local returns, but retains
unique ownership: copying a borrowed builder is rejected.

Nullable primitives and supported opaque owners can be instance fields. Defaults
are absent, assignment releases a replaced owner, and class destruction cleans
up remaining owners. Mutable field predicates do not refine subsequent reads;
use `expect_valid` on the field. Static nullable fields are rejected. IRx also
supports by-value primitive nullable struct fields; this does not introduce Arx
`struct` syntax or managed struct destruction. Nullable C-string `str | none`
uses a null pointer for absence: a present empty string is distinct from `none`.
Local and instance-field strings own heap storage. Copying static or borrowed
text duplicates its bytes; returns and replacements never retain dangling
pointers. `scalar[string] | none` remains the Arrow text alternative, including
embedded NUL through its byte operations. Unmanaged language list/tuple elements
still cannot store dynamic strings without element destruction; use
`array[string]` for owned columnar text.

## Record batches and tables

`record_batch[fields]` owns equal-length array columns; `table[fields]` owns
chunked columns. Both are ambient builtins, accept schema/field metadata, and
support the executable primitive and logical array element types described here,
including nullable, nested and half-float values. Constructors require the row
count first:

````arx
```
title: Native typed tabular values
```
fn main() -> i32:
  ```
  title: Keep column types and validity explicit.
  ```
  var batch: record_batch[a: i32 | none] = record_batch[a: i32 | none](2, array[i32 | none](1, none))
  var data: table[a: i32 | none] = to_table(batch)
  assert num_rows(data) == 2
  assert is_null(array_at(column(data, "a"), 1))
  var dynamic: table = runtime_schema(data)
  var checked: chunked_array[i32 | none] = column_as(dynamic, 0, field[a: i32 | none])
  assert array_length(checked) == 2
  return 0
````

The explicit count permits nonzero rows with no columns: `record_batch[](5)`.
Shape mismatches, negative counts and out-of-range slices fail through the
checked native diagnostic boundary, not by reading an invalid output slot.

| Operation                                       | Contract                                                                                            |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `num_rows(value)`, `num_columns(value)`         | Checked dimensions for batches and tables.                                                          |
| `container_schema(value)`                       | Independently owned schema descriptor, retaining metadata.                                          |
| `column(value, "name")`                         | Resolve a literal name in a static schema; return an array for batches or chunked array for tables. |
| `runtime_schema(value)`                         | Retain an owner while explicitly erasing static schema facts.                                       |
| `column_as(value, index, field[...])`           | Check field name, type, nullability and metadata at runtime before returning a typed column.        |
| `take_rows(value, indices)`                     | Select/reorder/repeat rows using nonnullable `array[i64]`; bounds are strict.                       |
| `slice_rows(value, offset, length)`             | Strict bounded row slice; does not silently clamp.                                                  |
| `select_columns(value, "b", "a")`               | Project/reorder unique static fields; selecting no fields preserves row count.                      |
| `rename_columns(value, "new_a", "new_b")`       | Supply one unique name per field; preserve metadata.                                                |
| `add_column(value, field[new: T], column)`      | Append a column with checked type, nullability and row count.                                       |
| `replace_column(value, field[name: T], column)` | Replace the named field and column; type changes are explicit in the new field.                     |
| `remove_column(value, "name")`                  | Remove one static field without changing row count.                                                 |
| `to_table(batch)`, `to_record_batch(table)`     | Explicit conversion; table-to-batch may materialize chunks.                                         |
| `table_combine_chunks(table)`                   | Explicitly coalesce table chunks.                                                                   |

Transforms are immutable: child views and returned containers remain usable
after parent release or replacement. `table[...] | none` and
`record_batch[...] | none` support optional shared ownership. Iteration remains
explicit through row slices, columns, chunks or scalar indices; there is no
implicit iteration axis.

`table` is **not** a new spelling for legacy `dataframe`, nor is `chunked_array`
a new spelling for `series`. Existing DataFrame/Series syntax is unchanged;
`to_dataframe(table)` and `to_table(dataframe)` retain independent owners
without copying buffers. These adapters deliberately erase static schema facts,
not runtime field metadata; use `column_as` to recover checked typed columns.
`to_series(chunked_array)` and `to_chunked(series)` preserve the element type.
Logical columns and noncontiguous row selection are available through the typed
batch/table APIs. Table selection shares immutable row slices; batch selection
materializes columns. Neither uses an implicit Compute kernel or changes schema
metadata.

See `examples/columnar_tables.x` and `examples/columnar_table_owners.x` for
executable transformation and lifetime examples.

## Logical scalars and nested values

`scalar[T]` is an immutable, shared Arrow scalar owner. It is distinct from the
ordinary numeric scalar representation and from the current C-string `str`. Use
`scalar[T] | none` for absence, not `scalar[T | none]`. Constructors and queries
are ambient builtins, with no Arrow namespace or import.

- Atomic scalars accept text: `scalar[date32]("2024-01-02")`,
  `scalar[decimal128(precision=12, scale=2)]("12.34")`. Decimal construction
  rejects precision overflow or rescaling that would lose digits.
- String/binary families accept text or nonnullable `array[u8]` data. Use bytes
  for embedded NUL or arbitrary binary data. `scalar_bytes(value)` returns an
  independently owned byte array without truncation. `scalar_text(value)`
  returns an owned `str` representation and rejects embedded NUL that `str`
  cannot hold.
- Intervals use signed integer components: months; days/milliseconds; or
  months/days/nanoseconds. Component overflow is checked.
- List, large-list, list-view, large-list-view and fixed-list scalars accept an
  array matching the declared child field. Fixed-list size is checked.
  `scalar_values(value)` returns an independently owned child array.
- Struct scalars take one scalar per field, in declaration order; nullable
  children may be `none`. `scalar_field(value, "name")` returns a nullable owned
  child, using a statically checked field name. Maps take an entries array with
  the declared key/value struct type.
- Dictionary scalars take a typed index scalar and a value array. Sparse/dense
  union scalars take a literal field name and that field's scalar. Run-end
  encoded scalars wrap their value scalar. These remain typed logical values,
  not strings containing serialized objects.
- `scalar_equal(a, b)` requires identical logical types and uses Arrow equality.
  Generic arithmetic on opaque scalars is rejected; primitive `array_at`
  continues to return native nullable numeric/Boolean values.

For non-primitive arrays, `array_at` returns `scalar[T] | none`. String/binary
array literals and builder appends accept ordinary `str` inputs directly; other
non-primitive inputs use explicit scalar constructors. All supported logical
elements work in chunks and typed batch/table columns. `array_copy` recursively
detaches nested/dictionary buffers; chunked copy preserves chunk boundaries.
Generic builders retain immutable scalar inputs and build a separate snapshot,
clearing their state only after successful publication. This favors correctness
and retry safety over a specialized high-throughput nested builder.

Examples: [`logical_scalar_owners.x`](../../examples/logical_scalar_owners.x),
[`nested_columnar_values.x`](../../examples/nested_columnar_values.x), and
[`logical_value_families.x`](../../examples/logical_value_families.x). Extension
scalars wrap a scalar of their declared storage type. `scalar_storage(value)`
returns independently owned storage for extension or run-end encoded scalars.
Arrow-registered canonical codecs validate storage and metadata. Unregistered
non-`arrow.*` names use an opaque storage codec that preserves the exact name,
serialized metadata (including binary bytes), and storage type. This does not
invent domain-specific arithmetic. Unknown reserved `arrow.*` codecs fail
explicitly rather than erase identity. Null arrays use
`array[null | none](none, ...)`; there is no present `scalar[null]` constructor.

## Checked C Data and buffer construction

These are ambient builtins, not `arrow.*` imports:

- `export_c_data(array)` returns a shared immutable `c_data` carrier. Its native
  C ABI supports producer imports and consumer exports; raw C pointers and Arrow
  C++ layouts are never exposed in Arx.
- `array_from_c_data(owner, field[value: T | none])` checks the exact logical
  type and required validity, then returns an independently owned array. The
  carrier preserves complete field metadata; an array value itself carries its
  datatype and validity, not a top-level field name.
- `array_with_validity(array, bitmap, bit_offset)` applies packed validity bits
  from nonnullable `array[u8]`. It can remove validity but never revive a null.
- `array_from_buffers(field[value: T | none], data, bitmap, length, offset)`
  copies bounded `array[u8]` buffers for fixed-width or packed Boolean storage.
  An empty bitmap means all-valid. Offset is measured in elements, including
  bits for Boolean data; the validity offset is also in bits. Invalid extents,
  overflow, nullability mismatches and unsupported layouts fail explicitly.

A native C Data move preserves producer callbacks on preflight/owner-reservation
failure. Once import starts, both callbacks are consumed exactly once on success
or failure. External producers must supply readable, standard-compliant storage;
this is not a safe decoder for arbitrary addresses. Streams belong to M7.

See [`columnar_interchange.x`](../../examples/columnar_interchange.x),
[`dataframe_adapters.x`](../../examples/dataframe_adapters.x),
[`extension_values.x`](../../examples/extension_values.x), and
[`nullable_strings.x`](../../examples/nullable_strings.x).

## Optional list and tensor owners

`list[T] | none` and fixed-shape `tensor[T, ...] | none` are builtin optional
owners. They carry an explicit validity bit beside the ordinary collection
payload: a present empty list is not `none`. `is_valid`, `is_null`, guarded
identifier refinement and `expect_valid` work without importing Arrow.

- Dynamic lists remain unique: a fresh returned list can initialize an optional
  owner, but copying or self-assigning a list owner is rejected. Appending
  through a proven-present mutable local preserves its validity proof. Borrowed
  parameters and static list literals cannot be grown.
- Tensor copies and borrowed returns retain independent shared buffer owners.
  Replacing a source with `none` does not invalidate a retained copy.
- Local owners, returns and mutable class instance fields release present
  payloads exactly once, including replacement with `none`. Generated IRx
  generator captures also retain and release optional tensor/buffer-view owners.
  Arx source generator syntax is not introduced by this support.
- Failed list growth cleans up owners in the active generated function before
  reporting a runtime error. Cross-frame fatal unwinding is not yet supported.

This does not enable nullable list **elements**, recursive managed language
collections, static managed fields or managed by-value struct destruction. See
[`nullable_collections.x`](../../examples/nullable_collections.x).
