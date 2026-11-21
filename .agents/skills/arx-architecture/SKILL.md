---
name: arx-architecture
description: Navigate Arx's package ownership and compiler pipeline, preserving Arx, ASTx, IRx, ArxPy, ArxJIT and AIX boundaries. Use for architecture and cross-package changes.
---

# Arx architecture: ownership and contracts

**Use before cross-package changes, review of a new abstraction, or architecture questions.** Root `AGENTS.md` is authoritative. Validate paths and support claims against current `main`; don't treat planned work as merged.

## End-to-end map

```text
.x source
  → arx lexer/parser and file/package discovery
  → astx.Module and reusable astx nodes
  → irx.analysis (typed sidecars, CompilationSession)
  → irx.builder LLVM lowering
  → registered native runtime features / C ABI
  → object → link → executable
```

| Owner | Responsible for | Must not acquire |
| --- | --- | --- |
| `packages/arx` | `syntax.json`, parser, source discovery, CLI, stdlib, language tests | Parallel reusable AST, general-purpose semantic analysis or LLVM lowering |
| `packages/astx` | Language-agnostic node/type modeling | Claims of specific frontend or backend support |
| `packages/irx` | Validity, symbols, conversions, semantic plans, diagnostics, LLVM, linking and native runtime | File discovery/parsing from source paths |
| `packages/arxpy` | Python integration API | Unapproved replacement for compiler stage contracts |
| `packages/arxjit` | Extract → validate → resolve signature → lower Python functions | Claims of native dispatch (`@jit` currently runs Python fallback) |
| `packages/aix` | Toy syntax experiment | Authority over Arx's public syntax |

**Key sources:** `packages/arx/src/arx/parser/__init__.py` composes parser mixins; `packages/arx/src/arx/codegen.py` remains an adapter using IRx builder; `packages/irx/src/irx/analysis/__init__.py` exports semantic APIs and `CompilationSession`. IRx hosts receive `ParsedModule` and `ImportResolver` (see `irx.analysis.module_interfaces`).

## Change impact procedure

1. Identify **what meaning changes**: surface syntax, AST shape, typing, runtime behavior, Python bridge, or installation.
2. Locate its owner above; inspect existing comparable implementation and the actual caller chain.
3. If a new reusable node is required, implement ASTx shape first, then align frontend emission, IRx analysis and lowering. Do not claim that AST modeling alone enables execution.
4. If the change is semantic, resolve it in `irx.analysis` and attach metadata rather than reparsing names/types in the builder.
5. If native behavior changes, follow [native-runtime-design](../native-runtime-design/SKILL.md). Also follow [arrow-first-design](../arrow-first-design/SKILL.md) when data representations, compute semantics or interchange contracts change.
6. Touch exports, schemas, docs, package manifests, examples or tests **only where the changed contract reaches them**.

## Design decision examples

- **Wrong:** `arx/codegen.py` infers a call's argument conversions after the frontend compiled it.
- **Right:** IRx analysis resolves the call and its conversions; lowering uses its semantic plan.
- **Wrong:** IRx opens a path to resolve an import.
- **Right:** The host resolves/parses modules and supplies `ParsedModule`/`ImportResolver`.
- **Wrong:** A new ASTx node is described as "supported by Arx."
- **Right:** Support is separately demonstrated at parsing, semantic validation, lowering and linked execution as appropriate.

## Verification

Choose the earliest affected layer and one representative downstream test. Examples: `makim arx.check-syntax`, `makim irx.test-analysis`, `makim arx.test-compiled`, `makim all.wheel-smoke`. Use full `makim all.ci` when the change spans sufficient boundaries to justify it. Follow [testing-standards](../testing-standards/SKILL.md).

**Exit:** no layer owns someone else's work, no unsupported form falls through silently, and every affected boundary has evidence or a clearly reported blocker.
