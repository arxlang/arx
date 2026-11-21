---
name: compiler-design
description:
  Implement and review Arx syntax, ASTx, IRx semantics, LLVM lowering,
  diagnostics and cross-stage compiler contracts. Use for compiler changes.
---

# Compiler feature and lowering contracts

**Use when changing the Arx frontend, ASTx nodes, IRx analysis, LLVM IR or
compiler diagnostics.** First read
[arx-architecture](../arx-architecture/SKILL.md) and
[minimal-change](../minimal-change/SKILL.md).

## Stage 1 — source → ASTx

Inspect lexical truth in `packages/arx/src/arx/lexer/syntax.json`, and the
parser modules in `packages/arx/src/arx/parser/` (mixins composed by
`parser/__init__.py`). Arx uses **two-space significant indentation**. All
committed `.x` modules require a Douki module docstring at line 1.

When adding syntax, check manifest → tokenization → parser → ASTx model. Don't
silently emit a generic ASTx object or discard a token just because later stages
are incomplete. Use `LexerError` or `ParserException` with trusted locations.

## Stage 2 — ASTx → IRx semantic meaning

Search `packages/irx/src/irx/analysis/` and `analysis/resolved_nodes.py` for a
comparable resolved plan. The `analysis/__init__.py` exports `analyze`,
`analyze_module(s)`, `CompilationSession`, diagnostics, symbols and resolution
structures.

**Resolve before lowering:** symbol identity, shadowing, type validity, numeric
conversions, imports, class rules, flow/cursor behavior, native feature needs.
Analyze through the host-provided `ParsedModule`/`ImportResolver`; IRx must
never open or lex source on its own. Attach semantic info to nodes/session.
Reject unsupported operations explicitly at the earliest responsible stage.

Avoid rediscovering semantics in `irx.builder`, including guessing the type from
expression shapes, re-resolving imports, or repeating class dispatch. Keep
dispatch through Plum `visit` overloads with a typed fail-closed fallback.

## Stage 3 — IRx → LLVM → executable

Lowering consumes `node.semantic`/`CompilationSession`. Verify:

- **Result stack:** only value-producing constructs push;
  branch/statement/terminator paths must not fabricate values.
- **Control flow:** never insert after a terminator; PHI incoming blocks must be
  actual fallthrough predecessors with compatible types.
- **IR validity:** parse and verify produced LLVM module where affected (the Arx
  adapter in `packages/arx/src/arx/codegen.py` calls `llvm.parse_assembly`
  before object emission).
- **Native requirements:** use runtime feature registration; ABI symbols must be
  available at link time, and Arrow layouts stay opaque.

## Debugging decision table

| Symptom                                  | Inspect first                                                         |
| ---------------------------------------- | --------------------------------------------------------------------- |
| Token not recognized                     | `lexer/syntax.json`, tokens, lexer                                    |
| Wrong indent/parse shape                 | `parser/state.py`, parser mixin, token positions                      |
| Accepted invalid type/name               | `irx.analysis` resolution and diagnostic                              |
| Crash/incorrect IR                       | semantic sidecar consumption, `irx.builder`, result stack, terminator |
| Link/runtime failure                     | feature registry, C ABI status/ownership, linker                      |
| Python-decorated JIT behaves differently | `arxjit` extract/validate/signature/lower; `@jit` is fallback         |

## Evidence

Use narrow tests first: `makim arx.check-syntax`, `makim irx.test-analysis`,
targeted `pytest packages/arx/tests/python/`, `makim arx.test-compiled`,
`makim arx.test-smoke`. Check output with `arx --show-tokens`, `--show-ast`,
`--show-llvm-ir` as suitable. Reuse tests that cover an invariant; extend only
for an uncovered contract.

**Exit:** source, ASTx, semantic, lowering, native and linked execution claims
each match actual implemented stage. List unsupported cases honestly; do not
mark planned work complete.
