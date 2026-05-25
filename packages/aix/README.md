# AIX

AIX is an experimental AI-oriented symbolic programming language frontend in the
Arx ecosystem.

- PyPI distribution: `airx`
- Python import: `aix`
- CLI command: `aix`
- Source extension: `.aix`

## Usage

```bash
pip install airx
aix --help
aix --show-tokens examples/fib.aix
aix --show-ast examples/fib.aix
```

## MVP syntax

```aix
∴ fib ⟦ n:ℕ ⟧ → ℕ
  ⊢ n ≤ 1 ⇒ n
  ⊢ fib⟦n - 1⟧ + fib⟦n - 2⟧
∎
```

Core forms:

- `∴` defines a function or constant.
- `⟦...⟧` is used for parameters and calls.
- `→` marks the return type.
- `⊢ expr` returns from a function.
- `⊢ cond ⇒ expr` emits an if-return branch.
- `⌁ name:T ≔ expr` creates a local binding.
- `⟣ expr` emits through the existing `print` builtin.
- `∎` ends a block; `{...}` and `;` support compact inline blocks.
- `κ⟦...⟧` metadata blocks are parsed and ignored in the MVP.
- Comments start with `⍝`.

Reserved APL-inspired operators such as `⍴`, `⍳`, `¨`, `↑`, `↓`, `⍋`, and `⍒`
are tokenized but intentionally rejected until backend support exists.
