---
name: release-check
description: Check Arx lockstep release readiness, dependency manifests, semantic-release configuration and GitHub workflow permissions. Use for release preparation or review.
---

# Review Arx release readiness, without publishing

**Use for packaging, lockstep release, artifact, or publishing-workflow questions.** By default this skill **does not publish or edit remote state**.

## Evidence to collect

- `.releaserc.json`: release branches, semantic-release plugins, replacement wiring and release steps.
- Root and package `pyproject.toml`, root `poetry.lock`, release scripts and the current `.github/workflows/main.yaml`.
- CI status on the exact proposed commit and any changed artifact build/installed-wheel tests.
- Current `packages/irx/pyproject.toml` and source package versions for Arrow/PyArrow/native bundle; do not use migration targets from prose as deployed facts.

## Checklist

1. Every released package in the lockstep set (Arx, ASTx, IRx, ArxPy, ArxJIT, AIX) has consistent version/dependency references and matching release replacements; inspect consumers rather than relying only on strings in root manifest.
2. If dependencies changed, regenerate with root `poetry lock`. Never hand-edit `poetry.lock`.
3. Confirm Python-version constraints and declared CI matrix agree. Preserve tested native Clang/C++ prerequisites where affected.
4. Confirm built wheel smoke covers imports and exact dependencies. For ABI changes check both native producer and LLVM consumer, compatible Arrow source/PyArrow versions and clean install behavior.
5. Read actual release-workflow triggers, branch restrictions and GitHub permissions. Differentiate PR dry-run (no publish) from live `main` publication, tag/release/issue-comment/commit side effects. If secrets are unavailable to PRs, do not treat that as proof the live release can authenticate.
6. Check actual failure/recovery surfaces: possible partial publication, commit/tag/release side effects, idempotent reruns and permissions. Recommend the **smallest** change that addresses an observed failure, not a wholesale release redesign.
7. Run existing `makim release.dry-run`, `makim all.wheel-smoke` or relevant tasks only as applicable and permitted. Do not add a duplicate full CI pipeline merely because a release is planned.

## Findings format

- **Blockers:** evidenced version/ABI mismatch, missing artifact, missing permissions or bad release step.
- **Non-blocking:** narrow improvements to reliability where justified.
- **Verified:** exact checks performed and their results.
- **Unverified:** live-publish-only behavior that a PR cannot validate.

Do not create release commits, update issues, tag, push or publish without explicit authorization.

**Done:** clear go/no-go for *verified* criteria, no invented confidence about the live workflow.
