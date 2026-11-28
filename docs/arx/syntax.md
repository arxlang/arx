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

Lexical reservation does not promise parsing or lowering. In particular, `then`
and operator declarations remain unavailable even though their spellings are
recognized.

## Numeric literals

Supported forms:

- decimal integers: `0`, `42`
- decimal floats with one dot: `3.14`, `.5`, `5.`
- scientific floats with `e` or `E` and an optional exponent sign: `1e3`,
  `1.5e-3`, `.5E+2`, `5.e2`

Scientific notation always produces a floating literal, even without a decimal
point. Exponents require at least one digit; `1e`, `1e+`, and `1e-` are lexical
errors. Floating literals retain their exact decimal value until semantic
analysis selects the contextual type (or `f32` without a context). Overflow in
that type is rejected; underflow uses normal rounding, including signed zero.

Not supported:

- hexadecimal, binary, or octal prefixes
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

## Comparisons

Comparisons can be chained, as in `1 < x < 10`. Arx evaluates operands from left
to right, evaluates each middle operand once, and stops after the first false
comparison. Use parentheses to group comparisons explicitly, as in
`(x < 10) == flag`.

## Structural forms

### Declarations and modifiers

Declarations put the name first. Omitted modifiers use context-specific
defaults; writing the default explicitly has the same meaning:

```text
count: i32 = 1
explicit_count: var :: i32 = 1
limit: const :: i32 = 10
inferred_count: auto = 1
```

`var` permits reassignment. `const` requires initialization and prevents binding
reassignment, compound assignment, and increment/decrement. It does not freeze a
referenced object, change ownership, or require compile-time evaluation. Locals
initialize on each call. Module declarations still obey the
[module storage restrictions](modules.md).

Use `&T` for a read-only alias and `&&T` for an exclusive alias to a local
numeric or Boolean variable. Initialize the alias with `&place` or `&&place`,
matching its access mode and the exact type of the source. With `auto`, the
initializer determines both the type and the access mode.

```arx
fn edit() -> i32:
  counter: i32 = 0
  other: i32 = 5
  editor: &&i32 = &&counter
  editor = 42
  editor += 1
  editor = &&other
  editor = 0
  return editor
```

The alias name reads its current target directly. Assigning an ordinary value to
an exclusive alias writes to its target. Assigning an explicit borrow retargets
a mutable alias with the same access mode and type. A borrow ends when its alias
leaves scope or successfully retargets. A nested block can retarget an outer
alias to storage that lives at least as long as the alias. At a branch join or
loop exit, direct access must be compatible with every target the alias may
still hold. If evaluating the new target raises, the alias keeps its old target.

Several read-only aliases may borrow the same variable. The owner remains
readable while read-only aliases are active. An exclusive alias is the only way
to read or write its target while the borrow is active. A `const` alias keeps
its target and, if exclusive, still permits writes through the alias. See
[list element borrows](collections.md#lists) for aliases of indexed list
storage.

Use `and` and `or` for logical AND and OR. Prefix `&&` forms an exclusive
borrow.

`auto` infers one fixed type from an initializer; it is not dynamic typing.
Uncontextualized numeric literals use the existing numeric defaults. Inference
is available for initialized variables, literal-initialized fields, and
count-loop initializers, not parameters, returns, aliases, or nested type
arguments. Untyped `none` and ambiguous empty containers need an explicit type.
Dataframe and tensor literals still need the type context required by their
constructors; resolved typed function results can be inferred without losing
their schema or shape.

A variable/parameter modifier group is whitespace-separated and ends with `::`.
Duplicate, conflicting, unsupported, and target-inappropriate modifiers are
errors. Fields also support their existing visibility/storage policies through
inline groups. Only classes retain modifier annotation prefixes. See
[classes](classes.md).

Functions remain keyword-first: `fn name(...) -> [modifiers ::] T:`. The
optional group controls the callable declaration, not the return type. Module
functions accept `public` (the default) or `private`; method-only policies are
described in [classes](classes.md). Argument binding modifiers remain separate,
for example `fn distance(record: const :: str) -> private :: i64:`. Externs keep
`extern name(...) -> [public|private ::] T` without a body.

Callable signatures may wrap parameters, modifier groups, the return type, and
the closing body colon across lines. Continuation indentation does not change
block indentation, which remains relative to the `fn` declaration. This is
signature layout support, not general multiline expression support.

**Migration:** leading `var name: T` declarations were removed; use `name: T` or
`name: var :: T`. Field modifiers move into inline groups, replacing
`constant`/`mutable` with `const`/`var`. Method annotations move after `->`, for
example `fn make() -> public static :: Counter:`. Class annotations and template
prefixes stay unchanged. The mistaken `name: fn(...)` form is not supported.
Read-only references, immutable objects, compile-time evaluation, rebindable
function values, and closures are not introduced by these changes.

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
