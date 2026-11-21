---
name: open-pr
description: Open a scoped Arx pull request from the intended fork and upstream base with Conventional Commit title and explicit verification. Use when asked to open or update a PR.
---

# Open or update a focused Arx PR

**Use only when asked to create, push, open or update a PR.** Follow [minimal-change](../minimal-change/SKILL.md) and [pr-review](../pr-review/SKILL.md). Never infer authority to merge, publish or force-push.

## Preflight

1. Identify upstream `arxlang/arx`, the explicitly requested fork (often `xmnlab/arx`), branch, base ref and actual commit SHA. Do **not** assume the fork's `main` matches upstream `main`.
2. Inspect local `git status` before branch/checkout operations. Do not reset or overwrite unrelated work.
3. Create a feature branch from the target **upstream main** commit (or another explicitly requested base). Verify the branch's ancestor and intended diff before writing.
4. Run focused relevant checks, then review the **whole** branch diff against the actual upstream base. Examine staged/untracked files separately if working locally.

## PR quality gate

- Diff contains only the requested coherent implementation, its required tests/source-contract updates and true dependencies.
- No duplicate tests, generated API references, incidental renames, benchmarks, new CI jobs, manually modified `poetry.lock` or secrets.
- All cross-package contract changes are included; no ignored semantic analysis or C ABI consumer.
- Report actual tests and limitations; do not claim green CI from a local assumption.
- Title is Conventional Commit format, e.g. `fix(irx): preserve ownership on failed native operation`.
- Body is brief: **goal**, **changes**, **verification**, **limitations**. Link issue when one exists, but don't invent one.

## Draft behavior

Prefer draft for autonomous AI-produced changes awaiting human review. Do not introduce Dask's `[unsupervised AI]` title prefix, which conflicts with Arx's Conventional Commit conventions. If the user explicitly requests ready-for-review and its validation is satisfied, follow that request.

## Remote side effects

Commit, push, or open/update PR **only with user authorization**. Never merge, tag/release, edit unrelated issues, or force update refs just to make the PR pass. If the integration cannot create cross-fork PRs (e.g. permission `403`), leave the committed branch intact and give the precise compare/create link instead of falsely claiming success.

## Done

Provide exact branch, upstream base SHA, compare or PR URL, relevant checks, and unresolved blockers. One independently reviewable change is better than several artificial milestones.
