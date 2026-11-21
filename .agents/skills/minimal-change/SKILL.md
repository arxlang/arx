---
name: minimal-change
description: Keep Arx changes and PRs minimal without compromising correctness; avoid incidental refactors, duplicate tests, unnecessary docs, benchmarks and tooling. Use for all planning and implementation.
---

# Minimal necessary change

Use for any implementation, refactoring, documentation, testing, or planning work. Root `AGENTS.md` remains authoritative.

## Goal and scope

Solve the stated problem with the smallest **complete and correct** change. Understand the requested result, existing behavior, and affected contracts before editing. Code is not immutable: rename, move, simplify, or redesign when the change genuinely requires it or the current structure obstructs a correct solution. Avoid stylistic rewrites and opportunistic cleanup.

- Preserve unaffected variable names, function names, comments, docstrings, formatting, and APIs.
- Inspect nearby code and affected callers before introducing helpers, interfaces, dependencies, or files.
- Prefer existing extension points and utilities. Do not refactor neighboring modules merely because they could be improved.
- Do not silently weaken safety, typing, diagnostics, runtime ownership, test coverage, or CI gates to reduce the diff.
- If a requested change requires a broader modification to remain correct, make it and explain the dependency succinctly.

## Tests, documents, and benchmarks

Search existing tests and docs **before** adding or changing them. Reuse or extend existing tests when they already express the invariant; add a focused test only for an uncovered behavior or failure mode. Never create a new test function or file solely because the PR needs a dedicated test. Retire obsolete assertions only when their contract is intentionally removed. Preserve essential regressions.

Keep required Douki source docstrings accurate, but do not rewrite unrelated text or add pages, explanatory diaries, duplicate API references, or documentation churn. Update existing concise guidance only for a changed workflow, restriction, architecture, or safety contract.

Do not add benchmarks, benchmarking frameworks, or benchmark CI unless the user explicitly requests them or the stated acceptance criteria require them. Existing performance diagnostics may be run when relevant.

## Stop rule

When the requested behavior is delivered, relevant contracts are preserved, and the narrow necessary checks are complete, **stop**. Mention unrelated observations as optional follow-ups rather than implementing them. Do not demand line-by-line justification; use engineering judgment to keep the PR reviewable.
