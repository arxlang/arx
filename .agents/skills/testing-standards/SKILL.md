---
name: testing-standards
description: Select and reuse existing Arx tests, adding only distinct necessary coverage and targeted verification. Use when writing, reviewing or selecting tests.
---

# Minimal, meaningful verification

Use when selecting, writing, changing, or reviewing tests. Read [minimal-change](../minimal-change/SKILL.md) first.

## Coverage before new tests

Locate existing suites, fixtures, parametrized cases, and assertions before creating anything. Ask: what distinct invariant or failure mode is currently unproven? Reuse existing coverage when sufficient; extend a nearby test or its parameters if that is the clearest solution. Add a new test or file only when existing coverage cannot express the new contract cleanly. Do not create a per-PR or per-bug test merely for visibility.

Tests must be capable of detecting the regression, not just exercise the code. Preserve existing relevant negative tests, data integrity, cleanup, ownership, invalid types, and boundary conditions. Avoid repeating the same large parameter matrix in parser, ASTx, analysis, and compiled integration layers.

## Verification selection

- Lexer/parser: syntax, significant indentation, invalid forms and reliable locations.
- ASTx: reusable node shape and runtime invalid-input checks.
- IRx analysis: meaning, symbols, shadowing, conversions, and structured failures.
- Lowering: LLVM verification, terminators, PHIs and result-stack safety.
- Native Arrow: null, empty, mismatch, status/error, overflow, ownership and interchange when affected.
- ArxJIT: Python AST, Unicode, closures, signatures and `analyze(lower(...))`.
- Public package boundary: representative installed-package and compiled execution test when relevant.

Start with a narrow pytest target; use existing `makim <package>.ci`, `makim arx.test-compiled`, `makim irx.test-sanitizers`, and broader checks only when their boundaries are affected or requested. Do not add CI tasks or benchmarks by default. Report exact checks run and limitations. Do not reduce coverage thresholds or weaken assertions for speed.
