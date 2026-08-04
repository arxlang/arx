# AIX

AIX is an experimental AI-oriented symbolic language frontend in the ArxLang
ecosystem.

- PyPI distribution: `airx`
- Python import: `aix`
- CLI command: `aix`
- Source extension: `.aix`

> Status: MVP. The lexer, parser, CLI inspection modes, and IRx backend handoff
> work for the documented subset. The symbolic grammar is not stable.

## Install and inspect

```bash
pip install airx
aix --help
aix --show-tokens program.aix
aix --show-ast program.aix
aix --show-llvm-ir program.aix
aix --run program.aix
```

## MVP syntax

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
- `κ⟦...⟧` metadata parsing (ignored after parsing in the MVP)
- Unicode identifiers, scalar literals, arithmetic, and comparisons

Reserved APL-inspired operators such as `⍴`, `⍳`, `¨`, `↑`, `↓`, `⍋`, and `⍒`
are tokenized but rejected until semantics and backend mappings exist.

## Current boundaries

AIX maps supported constructs directly to ASTx and relies on IRx for semantics
and LLVM. It does not yet expose Arx imports, classes, templates, Tensors,
DataFrames, RecordBatches, or other Arrow-backed language types. Native Arrow
support remains available in the shared IRx backend for future AIX syntax.

See `packages/aix/docs/` for the grammar and lexical reference.

License: Apache-2.0.
