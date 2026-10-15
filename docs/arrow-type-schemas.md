# Logical types and schemas

Arx's data model is Arrow-native. It does not introduce an `arrow` namespace or
require `import arrow` in Arx source.

## Implemented foundation

ASTx exposes immutable `LogicalType`, `LogicalParameter`, `SchemaField`, and
`Schema` descriptors in `astx.schema` and at the package root. Descriptors cover
all 45 modeled logical families: primitive and null types; string/binary,
large-offset and view types; fixed-size binary; dates, times, timestamps,
durations and intervals; decimal32/64/128/256; recursive lists, structs, maps,
unions, dictionaries, run-end encoding, and opaque extensions.

These are **schema descriptors**, not evidence that every corresponding Arx
array value, builder, operator, or kernel can execute. `SchemaType`,
`FieldType`, and `TypeDescriptorType` now execute as shared immutable native
owners. `ScalarType`, `ArrayType`, `ChunkedArrayType`, `RecordBatchType`,
`TableType`, and `StreamType` are modeled, but their new native value paths
remain pending. Declarations using these modeled-only types are rejected by IRx
analysis rather than reaching an unsupported LLVM representation. Existing
DataFrame, Series, tensor, and primitive runtime behavior is unchanged.

IRx provides:

- `irx.analysis.schema`: validation and canonicalization, with logical field
  paths on `SchemaError` and no invented source spans.
- `irx.analysis.schema_types`: resolved C Data formats and storage widths.
  Scalar mappings live in the shared builtin primitive metadata module, without
  introducing analyzer import cycles. Boolean storage is one bit, not one byte.
  Existing primitive builders remain limited to their previously implemented
  types.
- `irx.analysis.schema_conversions`: `EXACT`, `LOSSLESS`, `EXPLICIT`, and
  `INCOMPATIBLE` classifications. Classification is not an executable cast.
- `irx.schema_interop`: host-side `schema_to_pyarrow` and `schema_from_pyarrow`
  APIs. These use the Arrow C Data schema contract, not Python execution of
  compiled Arx operations.

For example, this **Python host API** constructs a schema descriptor:

```python
from astx import LogicalKind, LogicalType, Schema, SchemaField
from irx.schema_interop import schema_from_pyarrow, schema_to_pyarrow

schema = Schema((
    SchemaField("count", LogicalType(LogicalKind.INT64), nullable=True),
), metadata=((b"producer", b"arx"),))
assert schema_from_pyarrow(schema_to_pyarrow(schema)) == schema
```

## Builtin Arx descriptors

`datatype`, `field`, and `schema` are builtin value types: no import or Arrow
namespace is required. They support initialized local bindings, assignment,
parameters, returns, and managed class fields. Values are immutable; copying a
binding retains an owner, and replacement releases the old owner. Container
wrappers (including `list[schema]`), nullable descriptor values, unmanaged
struct fields, and yielding descriptors are rejected until their ownership paths
are implemented. Descriptor locals can survive generator suspension at the IRx
level; this does not add Arx generator syntax.

````arx
```
title: Inspect a native schema
```
fn main() -> i32:
  var rows: schema = schema[count: i64 | none, text: string]
  var count: field = schema_field(rows, 0)
  assert schema_nfields(rows) == 2
  assert field_name(count) == "count"
  assert field_nullable(count)
  assert descriptor_equal(field_type(count), datatype[i64])
  return 0
````

Literal forms:

- `datatype[logical_type]`, such as
  `datatype[decimal128(precision=38, scale=2)]`
- `field[name: logical_type | none]`; omit `| none` for a nonnullable field
- `schema[name: logical_type, ...]`; `schema[]` is an empty schema
- `schema[id: i64] {producer: "arx"}` adds schema metadata;
  `field[id: i64 {source: "sensor"}]` adds field metadata
- `datatype[list[item: string | none]]` and
  `datatype[struct[id: i64, text: string]]` describe nested types, not values

Logical names are the 45 `LogicalKind` spellings; integer and float short forms
(`i64`, `u32`, `f16`, etc.) are also accepted. Named parameters precede child
fields, for example `timestamp(unit="us", timezone="UTC")`,
`fixed_list(list_size=3)[item: i32]`, and
`dense_union(type_codes=[3,127])[number: i32, text: string]`. Parameters accept
literal integers, booleans, strings or integer vectors, not runtime expressions.
Source metadata and opaque extension payloads are UTF-8; binary metadata remains
available through ASTx and native C Data interoperability.

| Builtin                                    | Result and contract                                                                |
| ------------------------------------------ | ---------------------------------------------------------------------------------- |
| `schema_nfields(s)`                        | Signed `i64` number of top-level fields                                            |
| `schema_field(s, index)`                   | Independently owned field; bounds-checked signed index                             |
| `field_name(f)`                            | Owned string copy, valid after the field is destroyed                              |
| `field_type(f)`                            | Independently owned logical type descriptor                                        |
| `field_nullable(f)`                        | Boolean field nullability                                                          |
| `type_nfields(t)` / `type_field(t, index)` | Arrow physical child fields and checked projection                                 |
| `type_bit_width(t)`                        | Fixed storage width in bits; `-1` for variable-width types                         |
| `descriptor_equal(a, b)`                   | Exact same-kind identity, including field/schema metadata                          |
| `conversion_kind(literal_a, literal_b)`    | Compile-time `i32` classification: 0 exact, 1 lossless, 2 explicit, 3 incompatible |

`conversion_kind` accepts two datatype literals or two schema literals, not
runtime descriptor variables. It classifies conversions; **it does not cast
values**. Nullability/metadata changes follow IRx's conservative conversion
rules. Reflection uses Arrow physical children; dictionary values and opaque
extension storage are fully preserved in C Data but are not additional synthetic
children returned by `type_field`.

## Identity and validation

Fields retain their order and independent nullability. Field and schema metadata
retain binary keys and values, including NUL and non-UTF-8 bytes. Metadata key
ordering is canonicalized; duplicate keys and duplicate sibling field names are
rejected. Names must be valid UTF-8 without NUL. Empty schemas are distinct from
unknown runtime schemas.

Validation checks decimal precision limits (9/18/38/76 digits) and signed 32-bit
scale, time units, fixed sizes, union code uniqueness and range, integer
dictionary indices, nonnullable map keys, and signed run-end index widths. Named
timezones use the host's IANA database via `zoneinfo`; signed `HH:MM` offsets
and naive timestamps are also accepted. Nesting is bounded at 64 levels.
Extension names and serialized bytes are retained, not interpreted as permission
to execute unregistered extension kernels.

Arrow's C Data importer normalizes some synthetic children. To prevent silent
loss, descriptor validation requires:

- maps: `entries`, `key`, and `value` names, with no `entries` metadata;
- dictionaries: bare nonnullable `indices` and `values` type children;
- extensions: one bare nonnullable `storage` child;
- run-end encoding: bare `run_ends` and nullable `values` children, no direct
  nested run-end value type.

User field or schema metadata must not contain reserved extension keys; use an
explicit extension descriptor instead. These restrictions are deliberate
diagnostics, not silently dropped metadata.

Implicit compatibility requires whole-domain representability. Integer
narrowing, unsafe signedness changes, inexact integer-to-float conversions,
nullability removal, temporal rescaling, dictionary changes, and metadata
changes require explicit conversion. Unrelated structural shapes and changes to
opaque extension identity are incompatible.

## Native schema boundary

`irx_arrow_schema_import_copy` now imports recursive **field descriptors** using
Arrow C++. It clones the C struct tree before import, without invoking producer
release callbacks or consuming producer children. Metadata and names are copied
into owned Arrow fields. Exported schemas remain valid after the runtime handle
is released. A schema can be represented as a struct-root field descriptor; the
legacy schema handle remains compatible with that representation; new code uses
dedicated type and field handles.

The legacy primitive `schema_type_id` query is unchanged: nonprimitive types
return `UNKNOWN` and can be inspected through their exported recursive schema.
New dedicated type and field handles distinguish descriptor kinds. Type handles
normalize away the outer field name, nullability and ordinary field metadata,
while preserving extension identity and nested field metadata.

ABI **1.1.0** adds 19 descriptor symbols and the field handle kind without
changing existing IDs or signatures. The `array` feature contract is **1.2.0**;
generated code checks availability and the minimum version before descriptor
operations. The ELF version node stays `IRX_ARROW_1.0` across compatible minor
additions, so existing linked consumers keep their original symbol versions.

IRx analysis attaches a resolved native operation, physical C Data tree, minimum
feature version, index conversion and ownership to each expression. Lowering
consumes those facts, emits standard ArrowSchema C globals, and invokes only the
registered native feature. It never serializes descriptors using PyArrow during
compilation, embeds Arrow C++ layouts, or reads output slots before success. The
current backend targets the host ABI; C Data metadata lengths use native
endianness.

Tests cover all 45 logical families through source parsing/analysis, native
compiled literals, dedicated type/field handles and PyArrow round trips,
including binary metadata and independent lifetimes. Allocation probes sweep
real C++ allocation failures during descriptor copy import; other operations
have focused entry-failure and invalid-output checks. Generated ownership
sanitizer programs include class-field replacement, descriptor projection, owned
names, fatal bounds errors and suspended descriptor locals.

## Remaining milestone work

M3's descriptor execution is implemented; its combined **Gate B remains open**.
Nullable scalar values, general nested container construction, variable-width
buffer operations, and comprehensive offset/bitmap validation are separate value
work, not proven by descriptor tests. Actual value casts and runtime descriptor
conversion classification are not supplied here. M2 also retains incomplete
allocator-operation sweeps and an unverified local LSan gate; see `ROADMAP.md`
at the repository root for current M1-M4 progress.
