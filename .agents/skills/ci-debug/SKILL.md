---
name: ci-debug
description: Investigate Arx GitHub Actions and Makim check failures by identifying the first root failure and narrow remediation. Use for CI failures.
---

# Diagnose Arx CI failures

Use for GitHub Actions failures, test regressions and environment breakages. Do not automatically mutate CI or dependencies.

1. Locate the exact run/job, commit SHA, Python version, operating system, and failed step. Read complete relevant logs and the matching `.github/workflows/main.yaml` and `.makim.yaml` task definitions.
2. Isolate the **first meaningful failure**, separating product bug, test contract, environment/toolchain, dependency resolution, and workflow permissions.
3. Check whether the failure is introduced by the PR or existed on the baseline; do not describe flaky or unrelated errors as certain regressions without evidence.
4. Inspect the smallest owning layer and run the narrowest local reproducer when environment permits. Preserve important compiler/runtime checks rather than disabling them.
5. Recommend or implement only the necessary fix. Do not bump unrelated dependencies, alter `poetry.lock` manually, relax coverage or typechecking, or add retries/timeouts merely to mask a root cause.
6. Report cause, exact failing command, evidence, verified remediation and remaining unknowns.

Avoid repeated full CI reruns once an unchanged green check establishes the same result. Changes that require a new environment or revised source must still be validated appropriately.
