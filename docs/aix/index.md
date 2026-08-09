# AIX: a toy symbolic-language experiment

AIX is a small project built for fun while exploring Unicode-heavy symbolic
syntax on top of ASTx and IRx. It is not a primary ArxLang product, supported
language, or committed roadmap item.

- distribution: `airx`
- Python import: `aix`
- CLI: `aix`
- source files: `.aix`

## What currently works

The toy implementation includes a Unicode lexer, limited parser, token/AST/LLVM
inspection, and native backend handoff for its documented subset. Its grammar
and semantics can change freely.

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

## Explore locally

```bash
aix --help
aix --show-tokens program.aix
aix --show-ast program.aix
aix --show-llvm-ir program.aix
aix --run program.aix
```

There is no product or compatibility commitment. In particular, AIX does not
define the Tensor, DataFrame, Series, or RecordBatch syntax promoted by the main
Arx and IRx documentation.

Continue with:

- [AIX syntax](syntax.md)
- [Toy grammar](grammar.md)
- [Examples](examples.md)
- [Reserved APL-inspired operators](apl-inspired-operators.md)
- [Ecosystem status](../ecosystem.md) for project boundaries
