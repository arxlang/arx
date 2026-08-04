# Arx Lexical Syntax Specification

Status: draft `0.2.0`

This page documents token-level behavior used by the lexer and editor tooling.
The normative source is `packages/arx/src/arx/lexer/syntax.json`. Parser and
semantic rules live in the [language reference](library/index.md).

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
[Docstrings](library/docstrings.md).

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
= < > + - * / . : , ; @ | ! ( ) [ ] { }
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
- arithmetic: `+`, `-`, `*`, `/`
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

The literal `...` is accepted only in the runtime-layout parameter forms
described by the type reference.

## Builtin lexical names

Builtin type names include numeric aliases, `bool`, `none`, text and temporal
types, plus `list`, `tensor`, `dataframe`, and `series`. Builtin callable names
include `cast`, `dataframe`, `isinstance`, `print`, `range`, and `type`.

These names are recorded for syntax tooling. Parser resolution still decides
whether a name is a type, constructor, ambient builtin, local binding, or
ordinary identifier in context.

## Consistency rule

Changes to lexical syntax must update `syntax.json` first, then the lexer,
tests, this document, examples, and any derived editor grammars.
