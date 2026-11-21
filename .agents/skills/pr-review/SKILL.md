---
name: pr-review
description:
  Review Arx PRs or local diffs for compiler correctness, ABI safety, scope
  creep, test duplication and documentation churn. Use for code review requests.
---

# Review an Arx pull request or local branch

**Use when asked to review a PR, change set or branch.** This is read-only
unless the user explicitly asks to submit a GitHub review or edit code. Apply
[minimal-change](../minimal-change/SKILL.md) and
[arx-architecture](../arx-architecture/SKILL.md).

## Inputs and modes

- **PR URL/number:** fetch exact base/head SHA, diff, body, files, commits,
  conversations, pending review comments and CI. The PR is the subject; upstream
  `main` code/tests/config are the comparison baseline. Account for stacked
  branches.
- **Local diff:** inspect `git status`, `git diff <base>...HEAD`, staged and
  uncommitted changes separately as appropriate. Never assume a branch contains
  only one commit.
- **No target:** use current branch only when that is the user's clear intent;
  otherwise identify the required target without guessing.

Never claim GitHub CI or a local test passed without reading its actual result.

## Read and reason, don't checklist blindly

1. Summarize the intended contract and affected packages.
2. Trace modified functions into callers and downstream compiler phases.
3. Check architecture ownership: Arx syntax/discovery, ASTx modeling, IRx
   analysis for meaning, LLVM lowering consuming semantic sidecars, registered
   native features and C ABI boundaries.
4. Probe relevant failure modes: shadowing/aliases, Unicode locations,
   unsupported nodes, Python-version discrepancies, result-stack and
   terminators, PHI fallthrough, Arrow validity/null/overflow, output status,
   ownership/cleanup and installed package export.
5. Compare changed tests against existing coverage. A new
   function/file/parameter set is _not_ inherently valuable. Check whether a
   useful negative regression is actually covered.
6. Review **scope**: unrelated renames/docstring edits/formatting, abstractions
   without actual consumers, duplicated guides, unnecessary benchmark/CI
   additions and future milestones. Respect pre-2.0 compatibility policy; don't
   demand compatibility shims by default.
7. Examine current CI, manifests, release wiring and docs **only where touched
   contract warrants it**. CI cannot replace reasoning about semantic validity
   or native ownership.

## Severity rubric

- **P0/P1 blocking:** demonstrable unsafe behavior, incorrect semantics,
  ABI/lifetime defect, invalid IR, missing critical contract, or design placing
  meaning in wrong owner.
- **P2 blocking or important:** reproducible regression, lack of essential
  behavior-specific test, broken consumer/export; explain impact.
- **Non-blocking:** genuine simplification, naming/maintainability or duplicate
  test/docs that meaningfully increase scope but don't jeopardize correctness.
  Avoid nitpicks already checked by Ruff or CI.

Each finding must state **location, contract, concrete impact, evidence, and
requested minimal correction**. Investigate instead of hypothesizing. Do not
praise unrelated code or repeat findings.

## Report template

```markdown
## Blocking findings

- [P1] <finding> — path:line Contract / impact / evidence / requested change

## Non-blocking

- <only useful follow-ups>

## Verification and uncertainties

- Confirmed: <checks or code evidence>
- Not verified: <specific risk>

## Recommendation

Request changes / No blockers / Unable to conclude
```

Omit empty sections. If no blockers, say so; never invent a defect to fill the
report. Do not post a review, add labels or modify the PR without permission.
