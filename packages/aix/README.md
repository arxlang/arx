# AIX

AIX is a toy symbolic-language experiment built for fun on top of ASTx and IRx.
It is not a primary ArxLang product or a stability commitment.

- PyPI distribution: `airx`
- Python import: `aix`
- CLI command: `aix`
- Source extension: `.aix`

> Status: toy project. The lexer, limited parser, CLI inspection modes, and IRx
> handoff work for the documented subset. The grammar can change freely.

## Install and inspect

```bash
pip install airx
aix --help
aix --show-tokens program.aix
aix --show-ast program.aix
aix --show-llvm-ir program.aix
aix --run program.aix
```

## Toy syntax

```aix
∴ fib ⟦ n:ℕ ⟧ → ℕ
  ⊢ n ≤ 1 ⇒ n
  ⊢ fib⟦n - 1⟧ + fib⟦n - 2⟧
∎

∴ main ⟦⟧ → ∅
  ⟣ fib⟦10⟧
∎
```

Implemented forms:

- `∴` function and constant definitions
- `⟦...⟧` parameters and calls
- `→` return types
- `⊢ expr` return and `⊢ condition ⇒ expr` conditional return
- `⌁ name:T ≔ expr` local bindings
- `⟣ expr` output through the existing print node
- `∎` blocks and compact `{...}` / `;` layout
- `κ⟦...⟧` metadata parsing (ignored after parsing)
- Unicode identifiers, scalar literals, arithmetic, and comparisons

Reserved APL-inspired operators such as `⍴`, `⍳`, `¨`, `↑`, `↓`, `⍋`, and `⍒`
are tokenized but rejected until semantics and backend mappings exist.

## Scope

AIX maps its small supported subset to ASTx and relies on IRx for semantics and
LLVM. It does not expose Arx imports, classes, templates, Tensors, DataFrames,
RecordBatches, or other Arrow-backed language types. There is no committed
feature roadmap.

Canonical documentation, including the grammar and lexical reference, is at
<https://arxlang.org/aix/>.

License: Apache-2.0.
