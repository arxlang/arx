---
name: release-check
description: Check Arx lockstep release readiness, dependency manifests, semantic-release configuration and GitHub workflow permissions. Use for release preparation or review.
---

# Review Arx release readiness

Use for release changes, packaging issues, and publication readiness. This skill is primarily read-only unless publication is explicitly authorized.

1. Read current package manifests, root lockfile, `.releaserc.json`, build/publish scripts, `.github/workflows/main.yaml`, and relevant PR/CI context.
2. Check consistent lockstep version and dependency wiring across Arx, ASTx, IRx, ArxPy, ArxJIT and AIX; inspect paths/exports when packages are added or renamed.
3. Check Poetry lock generation policy: edit manifests and run root `poetry lock`; never edit `poetry.lock` by hand.
4. Confirm selected Arrow/PyArrow/native artifacts have a compatible exact version and supported ABI; do not assume an unpublished source bundle exists.
5. Check release permissions, secrets scope, artifact build/wheel smoke, semantic-release conditions and idempotency/failure points. Avoid adding unnecessary duplicate full-CI runs if the required PR CI is already green.
6. Run an existing release dry-run or focused packaging check when available and appropriate. State exact evidence and blockers.

Do not publish releases, create version commits, update changelogs or post issues without an explicit user request. Do not introduce speculative release infrastructure or new tests by default.
