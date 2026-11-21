---
name: arx-architecture
description: Navigate Arx's package ownership and compiler pipeline, preserving Arx, ASTx, IRx, ArxPy, ArxJIT and AIX boundaries. Use for architecture and cross-package changes.
---

# Arx repository architecture

Use when locating ownership, reviewing cross-package changes, or evaluating an implementation design. Root `AGENTS.md` holds the binding rules; verify current code for volatile facts.

The pipeline is `.x` source → Arx lexer/parser → ASTx → IRx semantic analysis/sidecars → LLVM lowering → registered native runtime features → linking/execution.

- `packages/arx`: source discovery, lexer/parser, CLI, language tests, stdlib; builds ASTx nodes, not a private reusable AST or generic lowerer.
- `packages/astx`: frontend-agnostic node/type modeling. A node does not establish executable backend support.
- `packages/irx`: semantic validity, resolved metadata, LLVM lowering, diagnostics, native features, linking, Arrow interoperability. Hosts supply `ParsedModule` and `ImportResolver`; IRx does not parse/discover source.
- `packages/arxpy`: foundational Python-facing integration.
- `packages/arxjit`: Python extraction/validation/signature/ASTx lowering; `@jit` still runs Python fallback, not native dispatch.
- `packages/aix`: toy experiment, not authority for Arx language design.

Before adding code identify who owns the meaning and whose callers/exports depend on the contract. Keep `arx/codegen.py` a small adapter. New reusable nodes require frontend, analysis, lowering, export, and test coordination where affected.

Consult [compiler-design](../compiler-design/SKILL.md), [arrow-first-design](../arrow-first-design/SKILL.md), and [native-runtime-design](../native-runtime-design/SKILL.md) for specialized decisions. Never add speculative backend architectures, source-finding to IRx, or unnecessary cross-package refactors.
