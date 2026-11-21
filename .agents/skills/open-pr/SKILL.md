---
name: open-pr
description: Open a scoped Arx pull request from the intended fork and upstream base with Conventional Commit title and explicit verification. Use when asked to open or update a PR.
---

# Open or update an Arx PR

Use [minimal-change](../minimal-change/SKILL.md) and [pr-review](../pr-review/SKILL.md).

1. Verify requested upstream repository, target base, fork, source branch, remote permissions and local modifications. Prefer a feature branch based on the current upstream `main`; never infer that the fork's `main` is current.
2. Review the complete diff and remove only clearly task-unrelated changes that you own. Never discard another contributor's work.
3. Verify no accidental secrets, generated docs, caches, benchmark files, lockfile edits or unrelated renaming are included. Preserve necessary source contracts.
4. Run the smallest meaningful checks possible, report failures honestly, and note what CI will verify. Do not re-run already successful identical CI merely for ritual.
5. Use a Conventional Commit PR title (`feat:`, `fix:`, `docs:`, etc.). Write a short body with goal, important changes, executed checks, omissions and remaining risks. Draft state is appropriate for autonomous work not yet reviewed by a human, but do not force Dask's nonconventional title prefix on Arx.
6. Open/update only when explicitly requested. Never merge, force-push, publish, label or comment on unrelated issues without authorization.

A PR should represent one coherent deliverable. If separate changes are independently reviewable, prefer distinct PRs, not an artificial milestone explosion.
