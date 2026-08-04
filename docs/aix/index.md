# AIX

AIX is an experimental AI-oriented symbolic language frontend built on ASTx and
IRx.

- distribution: `airx`
- Python import: `aix`
- CLI: `aix`
- source files: `.aix`

## Current status

The MVP includes a Unicode lexer, symbolic parser, token/AST/LLVM inspection,
and native backend handoff for supported programs. Its grammar and semantics are
intentionally experimental.

```aix
∴ fib ⟦ n:ℕ ⟧ → ℕ
  ⊢ n ≤ 1 ⇒ n
  ⊢ fib⟦n - 1⟧ + fib⟦n - 2⟧
∎

∴ main ⟦⟧ → ∅
  ⟣ fib⟦10⟧
∎
```

Implemented forms include function and constant definitions, typed parameters,
local bindings, return and conditional-return statements, output, scalar
literals and operators, explicit block terminators, and metadata blocks that are
parsed then ignored.

APL-inspired symbols such as `⍴`, `⍳`, `¨`, `↑`, and `↓` are reserved. The lexer
recognizes them, but the parser reports that their semantics are not yet
implemented.

## Install

```bash
pip install airx
aix --help
aix --show-tokens program.aix
aix --show-ast program.aix
aix --show-llvm-ir program.aix
aix --run program.aix
```

## Relationship to Arrow

AIX shares IRx's native runtime architecture, but the AIX language does not yet
define Tensor, DataFrame, Series, RecordBatch, or other Arrow-backed syntax.
Those features should be described symbolically before the frontend exposes them
rather than copied mechanically from Arx.

Read the [AIX syntax](syntax.md) for the current forms and the
[ecosystem status](../ecosystem.md) for project boundaries.
