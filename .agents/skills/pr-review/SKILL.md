---
name: pr-review
description: Review Arx PRs or local diffs for compiler correctness, ABI safety, scope creep, test duplication and documentation churn. Use for code review requests.
---

# Review an Arx PR or branch

Read [arx-architecture](../arx-architecture/SKILL.md), [minimal-change](../minimal-change/SKILL.md), and domain skills relevant to changed files.

## Evidence

Fetch exact base/head commits, diff, PR description, review history, CI status, and relevant current files. The requested PR/commit is authoritative for what is proposed; compare against upstream `main` contracts, tests/config and then docs/issues. Distinguish merged versus proposed changes and stacked-branch effects.

Review callers and downstream stages rather than diff lines alone. Check semantics versus lowering, unsupported nodes, Unicode/source locations, shadowing, result-stack/terminators, Arrow null/overflow, native status/ownership, Python version differences, exports, release wiring, and executable examples where applicable.

## Scope review

Identify unnecessary variable/function renames, docstring rewrites, formatting churn, speculative abstractions, redundant tests or docs, new benchmarks or tasks without acceptance need. Do not request a new test merely as ritual if the existing suite covers the invariant. Conversely do not excuse a real correctness gap as "minimal scope". Respect Arx's pre-2.0 API policy.

## Report

Lead with actionable **blocking** findings, then genuine non-blocking follow-ups. Each finding names violated contract, impact, evidence, file/line, and a focused suggested fix. Prefer confirmed defects over hypotheticals and avoid commenting on issues already enforced by passing CI unless drift makes them material. If no blockers, state so and enumerate only meaningful unverified risks.

Do not submit GitHub reviews, comments, labels, or merges unless explicitly asked. Never claim to have run unexecuted checks.
