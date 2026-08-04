# AIX MVP syntax

AIX is a Unicode-first, indentation-insensitive frontend. Whitespace and
newlines improve readability, but `∎` or `{...}` determines function block
boundaries. The current grammar is an experimental MVP and can change.

## Definitions

`∴` begins a top-level definition. A function places typed parameters in
semantic brackets and may declare a return type:

```aix
∴ add ⟦ left:ℤ, right:ℤ ⟧ → ℤ
  ⊢ left + right
∎
```

Omitting `→ type` produces a unit-returning function. A top-level constant uses
`:` and `≔` instead of a parameter block:

```aix
∴ answer:ℕ ≔ 42 ∎
```

## Statements

| Form                  | Current meaning                                              |
| --------------------- | ------------------------------------------------------------ |
| `⊢ value`             | Return `value`                                               |
| `⊢ condition ⇒ value` | Return `value` when `condition` is true                      |
| `⌁ name:T ≔ value`    | Create a mutable typed local binding                         |
| `⌁ name ≔ value`      | Create a mutable local with literal inference when available |
| `name ≔ value`        | Assign an existing local                                     |
| `⟣ value`             | Print a value through the shared ASTx/IRx print node         |
| `expression`          | Expression statement                                         |

The conditional-return form builds an `if` with no `else`; it is not a general
conditional statement.

## Blocks and separators

Pretty form ends with `∎`:

```aix
∴ main ⟦⟧ → ∅
  ⟣ "hello"
∎
```

Compact form uses braces and optional semicolons:

```aix
∴main⟦⟧→∅{⌁x:ℕ≔41;⟣x+1}
```

## Calls and expressions

Function calls also use semantic brackets: `add⟦1, 2⟧`. Parentheses group
expressions but do not call functions.

Supported operators, from lower to higher precedence:

1. `∨`
2. `∧`
3. `=`, `==`, `≠`, `!=`, `<`, `>`, `≤`, `>=`, `≥`, `<=`, `≡`, `≅`
4. `+`, `-`
5. `*`, `×`, `/`, `%`
6. `^` (right associative)

Unary `-` and `¬` are supported. `≡` and `≅` currently lower to equality.

## Types and literals

| AIX spelling              | Current ASTx type              |
| ------------------------- | ------------------------------ |
| `ℕ`, `ℤ`                  | `Int64`                        |
| `ℝ`                       | `Float64`                      |
| `𝔹`                       | `Boolean`                      |
| `∅`                       | `NoneType`                     |
| `i8`, `i16`, `i32`, `i64` | corresponding signed integer   |
| `u8`, `u16`, `u32`, `u64` | corresponding unsigned integer |
| `f32`, `f64`              | corresponding float            |
| `bool`, `boolean`         | `Boolean`                      |
| `str`, `string`           | `String`                       |

`ℂ` is tokenized as a primitive type but intentionally rejected because the
current IRx backend has no complex-number lowering.

Literals include decimal integers and floats, single- or double-quoted strings,
`⊤`/`true`, `⊥`/`false`, and `∅`. Line comments begin with `⍝`.

Unicode identifiers are normalized to NFC by the lexer.

## Metadata

`κ⟦...⟧` introduces a balanced metadata block before a definition:

```aix
κ⟦ι: hello.v1, χ: example⟧
∴ main ⟦⟧ → ∅
  ⟣ "metadata parsed"
∎
```

The parser currently accepts and skips metadata content; it does not attach it
to ASTx or IRx output.

## Reserved, not implemented

Index brackets `⟬...⟭`, field access, `λ`, tuple brackets `⟨...⟩`, ranges, and
the APL-inspired operators documented separately are lexed or reserved but do
not have MVP parser/backend semantics.
