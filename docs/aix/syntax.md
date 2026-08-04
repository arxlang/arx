# AIX MVP Syntax

AIX uses explicit symbolic block terminators. Indentation improves readability
but does not define block structure.

## Definitions

```aix
∴ identity ⟦ value:ℕ ⟧ → ℕ
  ⊢ value
∎
```

- `∴` begins a function or constant definition.
- `⟦...⟧` contains typed parameters and is also used for calls.
- `→` introduces a function return type.
- `∎` terminates a pretty-layout block.
- `{...}` terminates a compact inline block; `;` separates statements.

## Statements

```aix
∴ main ⟦⟧ → ∅
  ⌁ answer:ℕ ≔ 42
  ⟣ answer
∎
```

- `⌁ name:T ≔ value` declares a local binding.
- `name ≔ value` assigns an existing local binding.
- `⟣ expression` emits a value through the print node.
- `⊢ expression` returns a value.
- `⊢ condition ⇒ expression` conditionally returns an expression.

The conditional-return form is an `if` with no `else`, not a general conditional
statement.

## Calls and operators

Calls use semantic brackets, for example `fib⟦10⟧`. Parentheses only group an
expression. Supported operators are `∨`, `∧`, equality/comparison operators,
`+`, `-`, `*`, `×`, `/`, `%`, and right-associative `^`; unary `-` and `¬` are
also supported.

## Scalar types

The MVP recognizes symbolic names including:

| Symbol | Meaning                                                 |
| ------ | ------------------------------------------------------- |
| `ℕ`    | natural/integer value                                   |
| `ℤ`    | integer value                                           |
| `ℝ`    | real value                                              |
| `ℂ`    | Reserved complex type; currently rejected by the parser |
| `𝔹`    | Boolean value                                           |
| `∅`    | unit / no meaningful value                              |

The ASCII scalar spellings `i8`, `i16`, `i32`, `i64`, `u8`, `u16`, `u32`, `u64`,
`f32`, `f64`, `bool`/`boolean`, and `str`/`string` are also accepted. Only
mappings exercised by the MVP backend should be treated as stable.

Literals include integers, decimal floats, strings, `⊤`/`true`, `⊥`/`false`, and
`∅`.

## Metadata and comments

`κ⟦...⟧` introduces a metadata block. Metadata is parsed but ignored after
parsing in the current implementation. Line comments start with `⍝`.

## Reserved operators

APL-inspired operators such as `⍴`, `⍳`, `¨`, `∘`, `↑`, `↓`, `⍋`, `⍒`, `∊`, and
`∪` are tokens reserved for future designs. Using one in a parsed expression
raises an explicit unsupported-feature error.

Index brackets `⟬...⟭`, field access, `λ`, tuple brackets `⟨...⟩`, and ranges
are also reserved without parser/backend semantics.

## Current limits

Imports, classes, templates, exceptions, comprehensive control flow, and
Arrow-backed collection types do not yet have an AIX surface.
