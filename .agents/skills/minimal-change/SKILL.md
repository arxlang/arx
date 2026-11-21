---
name: minimal-change
description: Keep Arx changes and PRs minimal without compromising correctness; avoid incidental refactors, duplicate tests, unnecessary docs, benchmarks and tooling. Use for all planning and implementation.
---

# Minimal necessary change

**Use for every implementation, plan, refactor, test, review, or documentation task.** This skill is a scope-control procedure, not a prohibition on changing established code. Root `AGENTS.md` owns the binding project policy.

## First establish the actual change

1. Read the user's request and current behavior. State the observable result in one sentence; distinguish explicitly requested work from ideas that merely sound useful.
2. Inspect the smallest relevant set of source files, tests, and existing extension points **before** proposing new files. Trace affected callers and contract boundaries.
3. Choose the minimum complete design that preserves correctness, typing, ownership, diagnostics, compatibility policy, and necessary documentation contracts.
4. Identify the verification that demonstrates the result; prefer existing coverage. Do not automatically create a test, document, task, or benchmark for a PR.
5. Compare the final diff to the goal. Remove incidental changes that are not needed, without discarding another contributor's work.

## Decision table

| Proposed change | Normally do | Only expand when |
| --- | --- | --- |
| Rename a variable/function | Preserve existing name | It misrepresents changed semantics, causes a defect, or impedes a coherent fix |
| Restructure code | Keep local structure | The current organization prevents a correct or maintainable solution |
| Add helper/interface | Reuse direct code or established extension point | Multiple real callers need it, or correctness requires separation |
| Change docstring | Leave untouched | Signature, meaning, parameters, return, or safety contract actually changed |
| Add test function | Search existing tests/parameters first | A distinct behavior/failure is not covered cleanly |
| Add docs page | Usually do not | Critical user workflow, restriction, or architecture requires a page not covered elsewhere |
| Add benchmark | Do not | Explicitly requested or accepted performance criterion requires one |
| Change CI/dependencies | Do not | The requested feature/fix cannot be verified or delivered without it |
| Format nearby code | Do not | A touched expression cannot conform to established required formatting otherwise |

**Important nuance:** A necessary change is allowed even if it spans multiple packages or files. Cross-package coherence and native ABI safety are not "scope creep." Conversely, superficial cleanup is not justified just because a file is open.

## During implementation

Before each new file or unrelated subsystem edit, ask: *which acceptance criterion or affected invariant requires this?* If none, don't make it. Prefer direct names and code, clear guard clauses, and established patterns. Avoid preemptive rewrites, duplicated compatibility wrappers, "while here" renamings, or speculative architecture.

Do not weaken validations, suppress diagnostics, omit test coverage of an exposed regression, lower coverage gates, or skip error-path cleanup to save lines.

## Stop rule and delivery

Stop when the specific behavior works, required affected contracts are aligned, and relevant checks have passed or their blockers are reported. Do not launch a second optimization/refactor/documentation phase by default.

Final report: what changed, what evidence was run, what remains unverified. Mention optional improvements only if materially useful and **do not implement them**.

## Review red flags

- Diff contains broad variable or docstring rewrites unrelated to changed meaning.
- A new file duplicates an existing test, guide, wrapper, or task.
- Plan expands a one-week request into many phases or speculative futures.
- A passing implementation is followed by unrequested polish.
- The supposed "minimal" fix bypasses an essential IRx semantic, native ownership, or diagnostic contract.
