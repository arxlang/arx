---
name: testing-standards
description:
  Select and reuse existing Arx tests, adding only distinct necessary coverage
  and targeted verification. Use when writing, reviewing or selecting tests.
---

# Select the smallest meaningful test coverage

**Use whenever adding, changing, selecting or reviewing tests.** Apply
[minimal-change](../minimal-change/SKILL.md). The goal is proving contracts, not
maximizing test/function/file counts.

## Pre-test audit (mandatory before adding a test)

1. Search relevant tests, existing fixtures, parametrized matrices, and
   compiled-language cases for the **invariant** rather than the bug/PR number.
   Trace the assertion to the changed code.
2. Ask: would the existing test fail if the broken behavior returned? If yes, no
   new test is required. If no, can an existing test be **extended with one
   case/assertion**?
3. Add a new function/file only when the behavior belongs to a distinct layer or
   cannot be represented clearly in existing coverage. Explain the missing
   failure mode briefly in the PR.
4. Avoid duplicating an entire matrix across ASTx, parser, analysis, compiled
   language and native suites. Choose the earliest responsible layer, and one
   meaningful boundary integration if needed.
5. Preserve essential negative paths and regression coverage. Removing a
   duplicated test is acceptable only if its invariant remains covered (or an
   intentionally removed pre-2.0 contract no longer applies).

## Test decision map

| Work area                      | Preferred existing verification                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------ |
| Lexer and syntax               | `packages/arx/tests/python/`, `makim arx.check-syntax`                               |
| Parser and source shape        | Targeted parser tests; significant two-space indent, valid Douki module docs         |
| ASTx node/model                | `packages/astx/tests/` with invalid-input checks                                     |
| IRx meaning                    | `packages/irx/tests/analysis/`, `makim irx.test-analysis`                            |
| LLVM lowering/control flow     | Existing codegen translation tests, `llvm.parse_assembly`, `makim arx.test-compiled` |
| Native C ABI/Arrow             | Existing IRx native tests, `makim irx.test-sanitizers` when ownership/UB affected    |
| ArxJIT                         | `packages/arxjit/tests/` and `analyze(lower(...))` proof                             |
| Source user workflow           | Existing compiled `.x` tests/examples and `makim arx.test-smoke`                     |
| Public installed package graph | `makim all.wheel-smoke` when exports/import/ABI change                               |

## Distinct failure probes

Choose **relevant** risks, not all for every change: wrong types including
nested collection items, Unicode spans, shadowed symbols, signed integer
edges/overflow, empty and null arrays, C ABI error output, double release,
terminators, invalid PHI predecessors, unsupported syntax, Python-version
differences, installed wheel imports.

Do not create a new benchmark, test suite, CI job, test harness, or
parametrization dimension merely to be comprehensive. The current `.makim.yaml`
defines canonical tasks; test paths and commands must be confirmed from code.

## Verification order

Run targeted `pytest -q <existing test path or node>` first; follow with
relevant `makim <package>.typecheck`, `makim <package>.lint`,
`makim <package>.ci` or cross-package checks only when affected. Existing
`all.ci` is not an excuse to repeatedly perform costly unchanged checks. Do not
reduce assertions, coverage gates, or skip markers for a green result.

**Exit report:** what invariant is proven by which test; commands actually
executed and outcomes; what remains unverified. Do not claim that code coverage
percentage alone proves correctness.
