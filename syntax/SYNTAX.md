# Arx Syntax Specification (Lexical)

Status: draft `0.1.0`

This document defines Arx lexical/token-level behavior for editor tooling.

Normative source: `syntax/arx.syntax.json`

Non-goal: full parsing or AST semantics.

## 1) Source of Truth

- `arx.syntax.json` is canonical.
- Any derived editor grammar or tokenizer should be generated from, or manually
  validated against, that file.
- If this Markdown and the JSON disagree, the JSON wins.

## 2) Whitespace and Newlines

- Indentation is significant.
- Canonical indentation unit is 2 spaces.
- Newlines are significant boundaries for indentation handling.
- Blank lines reset indentation tracking for that line.
- Tabs policy is not finalized.
- TODO(ARX-LEX-WS-001): decide whether tabs are forbidden or normalized.

### Example

```arx
fn abs(x):
  if x < 0:
    return 0 - x
  else:
    return x
```

## 3) Comments

- Line comments start with `#` and continue to end of line.
- Block comments are not specified.

### Example

```arx
fn print_star(n):
  putchard(42)  # ascii '*'
```

### Edge Cases

- `#` inside future string syntax is undefined until strings are specified.
- TODO(ARX-LEX-COMMENT-002): decide whether `//` should become a comment
  delimiter.

## 4) Strings and Escapes

Current status: not yet specified for Arx lexical v0.1.0.

- No official quote delimiters.
- No official escape sequences.
- No triple-quoted or raw string prefixes.
- No string interpolation syntax.

TODO(ARX-LEX-STRINGS-001): define `"..."` / `'...'` behavior and escapes.
TODO(ARX-LEX-STRINGS-002): define raw strings and interpolation policy.

### Highlighter Guidance (current)

- Treat quote characters as plain punctuation/operators.
- Avoid speculative string scopes unless a tool explicitly opts into
  future-preview rules.

## 5) Numbers

Supported lexical number classes:

- Decimal integers (e.g., `0`, `42`)
- Decimal floats with one dot (e.g., `3.14`, `.5`, `5.`)

Not currently specified:

- Non-decimal bases (`0x`, `0b`, `0o`)
- Exponent forms (`1e9`)
- Numeric separators (`1_000`)
- Type suffixes (`42u32`, `1.0f32`)

### Edge Cases

- `1.2.3` is invalid (multiple decimal points).
- `.` alone is invalid as a numeric literal.

## 6) Identifiers and Unicode Policy

Identifier shape:

- Start: Unicode letter or `_`
- Continue: Unicode alphanumeric or `_`

Reference regex for tooling:

```regex
(?:[_\p{L}])(?:[_\p{L}\p{N}])*
```

Policy status:

- Current behavior tracks host-runtime Unicode character categories.
- TODO(ARX-LEX-IDENT-001): lock policy to either XID\_\* classes or ASCII-only.

## 7) Keywords

Reserved keywords:

- `const`
- `else`
- `extern`
- `fn`
- `for`
- `if`
- `in`
- `return`
- `then`
- `var`

Contextual keywords:

- none (empty list in `arx.syntax.json`)

### Edge Cases

- `fnx`, `if_else`, `returnValue` are identifiers, not keywords.
- Case-sensitive matching: `Fn` and `IF` are identifiers.

## 8) Operators and Punctuation

Current operator/punctuation set for lexical highlighting:

- Assignment/comparison/arithmetic: `=`, `<`, `>`, `+`, `-`, `*`, `/`
- Structural punctuation: `:`, `,`, `;`

Brackets:

- `()`
- `[]`
- `{}`

Notes:

- Multi-character operators are not finalized.
- TODO(ARX-LEX-OPS-001): decide on `==`, `!=`, `<=`, `>=`, `->`.

## 9) Canonical Lexical Examples

### Keywords vs identifiers

```arx
fn fnx(x):
  var if_else = x in
    return if_else
```

### Numeric forms

```arx
fn demo():
  var a = 42 in
    var b = 3.14 in
      var c = .5 in
        var d = 5. in
          a + b + c + d
```

### Comments

```arx
extern putchard(x)  # imported symbol
```

## 10) Lightweight Consistency Checks (Repo-Agnostic)

1. Canonical check:

   - Parse `syntax/arx.syntax.json`.
   - Verify required keys exist (`keywords`, `comment`, `strings`, `numbers`,
     `identifiers`, `whitespace`, `brackets`).

2. Derived artifacts check:

   - If/when an editor grammar exists, assert it was generated from or validated
     against the JSON manifest.
   - Fail CI if keyword arrays differ.

3. Drift check:

   - Add a simple script that loads JSON and scans corpus snippets (if present)
     to ensure each declared keyword/operator appears in at least one sample.

4. Change discipline:
   - Require PRs touching syntax tooling to update `arx.syntax.json` first, then
     derived files.
