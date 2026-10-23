# Arx Lexical Syntax

The authoritative token spellings, aliases, and editor-tooling inventory live in
`packages/arx/src/arx/lexer/syntax.json`. This guide covers writing source and
important restrictions, not a duplicate token catalog. Parser and semantic
support is summarized in the [capability matrix](capability-matrix.md).

## Source files and whitespace

- recognized extensions: `.x` and `.arx`
- indentation is significant
- the canonical indentation unit is 2 spaces
- tabs outside quoted literal contents are rejected; use spaces
- newlines delimit logical lines
- blank lines do not create indentation transitions

Files must be valid UTF-8 and no larger than 4 MiB of UTF-8 bytes. Token start
locations use one-based lines and Unicode code-point columns. The lexer also
limits delimiter nesting to 256, numeric tokens to 4,096 characters, and non-EOF
tokens to 250,000. These are compiler-version resource limits, not a frozen
language compatibility promise.

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

## Reserved forms

Lexical reservation does not promise parsing or lowering. In particular, general
`const`, `then`, and operator declarations remain unavailable even though their
spellings are recognized.

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

### Collection annotations

See [type annotations](datatypes.md#collection-annotations). Literal ellipsis
has different support boundaries for runtime-shaped tensors and runtime-schema
DataFrames; it is not uniformly parameter-only.

## Consistency rule

Changes to lexical syntax update the manifest first, then tokenization, parser,
tests, and derived editor consumers. Update this short guide only for changed
workflows or restrictions.

`File`, `open`, and dunder method names remain identifiers, not new keywords.
[Class lifecycle hooks](classes.md#lifecycle-hooks) do not add Arx `with`
statements. [Named calls](functions.md#keyword-arguments) use resolved
signatures, not lexical privilege based on the callee's spelling.
