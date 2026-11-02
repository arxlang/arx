# Built-in Types

Choose explicit scalar types for arithmetic and annotated collection types for
stored data. Accepted type spellings live in
`packages/arx/src/arx/lexer/syntax.json`; a lexical name alone does not
establish executable support. See the [capability matrix](capability-matrix.md)
for that boundary and [type annotations](datatypes.md) for placement.

## Scalars and conversions

Use fixed-width integers or floats when width matters, `bool` for conditions,
and `str` for UTF-8 text. `char` is a low-level `i8` representation, not a
Unicode grapheme. `none` is both the unit type and its sole value; a `-> none`
function may use bare `return`, `return none`, or fall through.

`cast(value, Type)` requests a supported conversion. `isinstance(value, Type)`
checks the semantic type, including finite union aliases; `type(value)` returns
its name. These do not introduce dynamic Python objects or runtime tagged
unions. See the executable
[datatype tests](https://github.com/arxlang/arx/blob/main/packages/arx/tests/arx/test_datatypes.x)
and
[preview arithmetic contract](specification.md#fixed-width-integer-overflow).

Strings have distinct static, borrowed, and owned lifetimes; consult the
[string ownership contract](../irx/runtime-ownership.md#enforced-string-contract)
before returning or storing borrowed text. Native strings cannot represent
embedded NUL safely.

## Parsing text

```arx
fn distance(record: str) -> i64:
  var clean: str = record.strip()
  return int(clean[1:])
```

For whitespace-delimited input, iterate over `text.split()`. The returned
strings and list own their storage, including after the source file is closed or
its text replaced. Advanced splitting can preserve empty fields with
`text.split(sep=",", maxsplit=2)`; `strip(chars="xy")` removes a set of code
points, not the substring `"xy"`. Explicit empty separators fail.

`len(text)` and indexing count Unicode code points, not bytes or grapheme
clusters; no normalization occurs. Slices clip nonnegative bounds, but negative
indices/bounds and non-unit steps are unsupported. `ord(text)` requires exactly
one code point. `int(text, base=10)` returns checked `i64`, with bases 2–36;
unlike Python it does not recognize base prefixes or digit separators, and
digits are ASCII only. Numeric casts still use `cast`, not `int`. Whitespace is
locale-independent and shared by splitting, stripping and integer parsing; its
exact set is specified in the native text source contract. Invalid text/options
and overflow raise recoverable errors rather than returning partial data. Text
literals and text-file reads reject embedded NUL; arbitrary octets use `bytes`
and binary File methods instead.

## Byte values

`bytes([0, 255, 13, 10])` creates an immutable, length-aware octet buffer.
`bytes()` is empty; `bytes(existing)` makes an independent copy. `len(data)`
counts bytes and nonnegative indexing returns `u8`; indexing outside the buffer
raises `IndexError`. NUL and invalid UTF-8 are ordinary bytes. This is not an
Arrow `binary` column and does not require Arrow.

Construction checks every integer in 0–255 without wrapping; Boolean, float,
nullable, and text inputs are rejected. Sized integer sequences are accepted;
single-pass iterators require an explicit `max_items` bound. An invalid value or
exceeded bound publishes no partial buffer, but consumed input is not rewound.
Unlike Python, scalar zero-fill construction, text encoding, and byte slices are
not implemented.

Content is immutable, but a local binding can be replaced. Buffers use the owned
list lifecycle: parameters borrow; fresh results and returned local owners
transfer ownership. Implicit local aliases are rejected: use `bytes(existing)`
for a copy. Byte buffers in class/struct fields, nested containers, globals,
extern signatures, and generator-owned storage are not supported. Independent
[binary reads](file-io.md#bounded-binary-workflow) can outlive their File.

## Collections and nullable values

[Collections and Apache Arrow](collections.md) owns the list, tensor, DataFrame,
and Series storage rules. In particular, runtime-schema DataFrames support
locals and returns, while runtime-shaped tensors remain parameter-only. Temporal
and rich Arrow column schemas do not imply general temporal or nested scalar
operations.

[Nullable expressions](collections.md#nullable-scalars-and-series-expressions)
carry explicit validity, propagate nulls, and use checked arithmetic. They are
not interchangeable with non-nullable scalar arithmetic or Boolean conditions.

## File references

[`File` and `open`](file-io.md) create shared class references to one text or
binary stream; lowercase `file` denotes the same type. References can be
aliased, passed, returned, and stored in supported class fields. Closing through
any alias closes the shared stream. Only the hidden native handle is uniquely
owned.
