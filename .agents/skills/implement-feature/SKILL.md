---
name: implement-feature
description:
  Implement a scoped Arx feature across the necessary frontend, ASTx, semantic,
  LLVM and native boundaries. Use for approved feature implementations.
---

# Implement the smallest complete Arx feature

**Use for an approved new language/runtime/API capability.** Read
[implementation-planning](../implementation-planning/SKILL.md),
[arx-architecture](../arx-architecture/SKILL.md),
[compiler-design](../compiler-design/SKILL.md), and
[minimal-change](../minimal-change/SKILL.md).

## Acceptance first

Define what `.x` program or Python API should work, which invalid forms must
fail, and the minimum evidence of linked execution. Propose an ordinary one-week
implementation slice, not a long speculative roadmap. Confirm whether similar
functionality already exists.

## Stage-by-stage decision process

1. **Surface:** verify actual accepted syntax in
   `packages/arx/src/arx/lexer/syntax.json` and split parser modules. Change
   manifest/tokens/parser only if syntax changes. Retain two-space indentation
   and valid Douki module docs in `.x`.
2. **Representation:** reuse ASTx nodes/types when possible; add reusable
   modeling only if required. No Arx-owned AST class or generic catch-all node
   for unsupported forms.
3. **Meaning:** implement typing, name/shadow resolution, conversions, imports,
   option and call identity in `irx.analysis`. Attach closed semantic metadata;
   ensure invalid forms yield structured, trustworthy errors. Check host
   `ParsedModule`/`ImportResolver` when imports are involved.
4. **Lowering:** consume semantic plan in IRx builder. Preserve result-stack,
   terminators, fallthrough and PHI validity. Verify LLVM representation.
5. **Runtime:** if needed, check Arrow-first support and use registered typed C
   ABI features. Handle statuses, null/overflow, lifetimes and output slots.
   Check linked execution and installed consumers for public feature.
6. **Integration:** update only changed exports, source docstrings and existing
   examples/tests. New docs page or benchmark is not automatic.

## Selection of checks

| Changed boundary       | Verification                                         |
| ---------------------- | ---------------------------------------------------- |
| Lexer/parser           | `makim arx.check-syntax`, targeted parser tests      |
| ASTx                   | `packages/astx/tests` target and type checking       |
| Semantics              | `makim irx.test-analysis`, negative form tests       |
| LLVM/compiled          | `makim arx.test-compiled`, emitted LLVM verification |
| Arrow/native           | Existing ABI tests, `makim irx.test-sanitizers`      |
| Package export/install | `makim all.wheel-smoke` when relevant                |

## Completion criteria

Feature works end to end for **explicitly supported** inputs; invalid inputs
fail at the responsible layer; affected tests verify the contract; unimplemented
forms are described honestly. Stop; do not add unrelated language
generalizations or future-proofing. For a genuinely larger goal, identify the
next independent PR rather than silently expanding the current one.
