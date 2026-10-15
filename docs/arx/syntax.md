# Arx Lexical Syntax Specification

Status: draft `0.2.0`

This page documents token-level behavior used by the lexer and editor tooling.
The normative source is `packages/arx/src/arx/lexer/syntax.json`. Parser and
semantic rules live in the [language reference](index.md#language-reference).

## Source files and whitespace

- recognized extensions: `.x` and `.arx`
- indentation is significant
- the canonical indentation unit is 2 spaces
- the syntax manifest forbids tabs; current lexer diagnostics do not enforce
  that rule consistently, so source must use spaces
- newlines delimit logical lines
- blank lines do not create indentation transitions

```arx
fn absolute(value: i32) -> i32:
  if value < 0:
    return 0 - value
  else:
    return value
```

## Comments and docstrings

`#` starts a line comment. Block comments are not supported.

Triple backticks delimit Douki YAML docstrings and produce a dedicated
`docstring` token:

````text
```
title: Module documentation
summary: Optional description.
```
````

Docstring placement and schema validation are parser concerns documented in
[Docstrings](docstrings.md).

## Identifiers

Identifiers start with a Unicode letter or `_` and continue with Unicode
alphanumeric characters or `_`.

Reference pattern for Unicode-aware tooling:

```regex
(?:[_\p{L}])(?:[_\p{L}\p{N}])*
```

The exact Unicode categories currently follow the Python runtime. Matching is
case-sensitive.

## Keywords

Reserved lexical keywords:

```text
assert class const else extern fn for if import in return then var while
```

Contextual keywords:

```text
as binary from operator type unary
```

Literal keywords:

```text
true false none
```

Lexical reservation does not by itself promise a complete parser or lowering for
every word. In particular, `const`, `then`, and operator-declaration words
remain reserved while their general language forms are incomplete.

## Numeric literals

Supported forms:

- decimal integers: `0`, `42`
- decimal floats with one dot: `3.14`, `.5`, `5.`

Not supported:

- hexadecimal, binary, or octal prefixes
- exponent notation such as `1e9`
- separators such as `1_000`
- literal suffixes such as `42u32`

Multiple dots are invalid, and `.` by itself is punctuation rather than a
number.

## Strings and characters

Double quotes create string literals. Single quotes create character literals.
The lexer recognizes these escapes:

| Escape | Value           |
| ------ | --------------- |
| `\\`   | backslash       |
| `\n`   | newline         |
| `\r`   | carriage return |
| `\t`   | tab             |
| `\"`   | double quote    |
| `\'`   | single quote    |

Raw strings, triple-quoted strings, and interpolation are not supported. Triple
backticks are reserved for Douki docstrings, not ordinary string values.

## Operators and punctuation

Single-character tokens:

```text
= < > + - * / % . : , ; @ | ! ( ) [ ] { }
```

Multi-character operators:

```text
== != <= >= -> && || ++ --
```

Word-form logical operators:

```text
and or
```

Current groups:

- assignment: `=`
- comparison: `<`, `>`, `<=`, `>=`, `==`, `!=`
- arithmetic: `+`, `-`, `*`, `/`, `%`
- logical: `&&`, `||`, `and`, `or`, `!`
- type union: `|`
- punctuation: `@`, `:`, `,`, `;`, `.`

`++` and `--` are lexed as unary operators. Availability in a particular
semantic context depends on the parser and IRx type rules.

## Structural forms

### Declaration modifiers

```arx
@[public, static, constant]
version: i32 = 1
```

Recognized modifiers are `public`, `private`, `protected`, `static`, `constant`,
`mutable`, `abstract`, and `extern`.

### Templates

```arx
@<T: i32 | f64>
fn identity(value: T) -> T:
  return value
```

Explicit template calls use angle brackets: `identity<f64>(1.5)`.

### Imports

Grouped imports use parentheses, require `from`, and allow a trailing comma:

```arx
import (
  sin,
  cos,
  tan as tangent,
) from math
```

### Collection type forms

```text
list[T]
tensor[T, D0, D1]
tensor[T, ...]
dataframe[name: T, ...]
dataframe[...]
series[T]
```

The literal `...` denotes runtime-shaped tensor parameters or runtime-schema
DataFrame owners. DataFrame locals, returns and instance fields also accept
runtime schemas; tensor restrictions are unchanged.

## Builtin lexical names

Builtin type names include numeric aliases, `bool`, `none`, text and temporal
types, plus `list`, `tensor`, `dataframe`, `series`, `datatype`, `field`, and
`schema`. Builtin callable names include `cast`, `dataframe`, `isinstance`,
`print`, `range`, `type`, descriptor inspection operations, and the nullable
operations `is_null`, `is_valid`, and `expect_valid`.

Primitive nullable annotations use `T | none` in locals, parameters and return
types. Bare `return` has no expression; `return none` explicitly returns a null
value (or the existing void sentinel in a `none` function). See the
[nullable reference](built-in-types.md#primitive-nullable-scalars) for the
implemented payloads and semantic limits.

These names are recorded for syntax tooling. Parser resolution still decides
whether a name is a type, constructor, ambient builtin, local binding, or
ordinary identifier in context.

## Consistency rule

Changes to lexical syntax must update `syntax.json` first, then the lexer,
tests, this document, examples, and any derived editor grammars.

### Native array values and nullable operators

`array[i32](1, 2)` and `array[i32 | none](1, none)` construct immutable
primitive arrays. Annotations use the same bracketed syntax. `array_at`,
`array_slice`, `array_copy`, `array_concat`, `array_equal`, `array_length`,
`array_null_count` and `array_offset` are ambient builtin names. Unsigned scalar
aliases are `u8`, `u16`, `u32`, `u64` and `uint8`, `uint16`, `uint32`, `uint64`.

`%` has the same precedence as multiplication and division. Primitive nullable
arithmetic/comparisons propagate null, Boolean operators use short-circuit
Kleene logic, and direct validity predicates narrow guarded scalar reads. See
the [builtin reference](built-in-types.md#first-class-primitive-arrays) for
supported types, ownership, bounds and remaining limitations.

### Primitive builder and chunk syntax

`array_builder[T]()` constructs a unique reusable builder;
`chunked_array[T](array1, array2, ...)` constructs an immutable chunk sequence.
Both support the same primitive logical types and `T | none` element syntax as
`array[T]`, including `f16`. Queries such as `builder_append`, `builder_finish`,
`chunk_count`, `chunk_at` and `combine_chunks` are ambient builtins. Chunk
iteration uses an explicit index loop rather than an implicitly selected unit.
`array[T] | none` and `chunked_array[T] | none` describe nullable **owners**,
not nullable elements; both forms can be combined when needed.

Typed `record_batch` and `table` values now expose primitive nullable columns,
checked projection and immutable structural transformations as ambient builtins.
Constructors take an explicit row count, then arrays (batch) or chunked arrays
(table); no Arrow import is needed. See
[built-in types](built-in-types.md#record-batches-and-tables) and
`examples/columnar_tables.x`. Nullable primitive casts, compound validity
proofs, optional unique builders and nullable instance fields are also
supported. Logical values, checked buffer/C Data constructors and explicit
legacy DataFrame/Series adapters are described below.

Logical columnar values are also native builtins: `scalar[T]`, typed arrays,
reusable builders, chunks, batches and tables need no Arrow import. See
[built-in types](built-in-types.md#logical-scalars-and-nested-values) for
strings, binary, temporal, decimal and nested construction, checked nullable
extraction, `array_from_buffer`, and explicit `take_rows` selection. Checked
buffer/C Data constructors and explicit legacy DataFrame/Series adapters are
also supported.

Optional dynamic list and fixed-shape tensor **owners** use existing union
syntax: `list[i32] | none` and `tensor[i32, 2] | none`. Proven-present mutable
list locals accept `.append(value)` without discarding their validity proof.
Lists remain unique; tensor copies retain shared buffers. See
[optional collection owners](built-in-types.md#optional-list-and-tensor-owners)
and `examples/nullable_collections.x`. Nullable elements and recursive managed
language aggregates remain unsupported.
