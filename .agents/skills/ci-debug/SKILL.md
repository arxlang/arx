---
name: ci-debug
description: Investigate Arx GitHub Actions and Makim check failures by identifying the first root failure and narrow remediation. Use for CI failures.
---

# Diagnose Arx CI failures without unnecessary reruns

**Use for a failed GitHub Actions run, Makim task, installation issue or status check.** Read exact run/job, matching commit SHA, log and workflow revision before concluding cause.

## Locate and classify

1. Fetch failed workflow, job, failing step and **first meaningful error** (the final summary may be secondary). Note branch/PR head SHA, Python version, OS, native toolchain and any retry.
2. Compare the job against `.github/workflows/main.yaml` and task invoked in `.makim.yaml`. The current matrix includes Python 3.11–3.14 on Ubuntu for package/language tests; confirm it from current CI rather than hardcoding this forever.
3. Determine category:
   - Source/behavior regression (assertion, compilation error, invalid IR).
   - Test fixture/expectation or coverage problem.
   - Dependency or environment installation failure.
   - Native artifact/ABI/Clang mismatch or sanitizer failure.
   - Workflow configuration, permissions or release token/secrets issue.
   - Intermittent infrastructure issue (requires repeated evidence, not guesswork).
4. Check whether failure exists on baseline or is introduced by PR. Avoid blaming unrelated historical job failures.

## Next action by failure

| Failure | Investigate | Avoid |
| --- | --- | --- |
| `makim arx.test-compiled` | Actual `.x`, lexer/parser, IRx semantic diagnostics, emitted LLVM | Rewriting workflow to skip tests |
| `makim irx.test-sanitizers` | Native ownership, ABI/status, sanitizer report and Clang | Suppressing the sanitizer |
| `makim <package>.typecheck` | Changed annotations/exports and current strict mypy | Adding broad `Any` or ignores |
| Poetry install/lock | Manifest constraints, artifact availability, Python matrix | Manually editing `poetry.lock`, blind dependency upgrades |
| Douki docs/lint | Changed source docstring/schema, `douki` command in Makim | Disabling docstring enforcement |
| GitHub permission failure | Token permissions, workflow event, branch protection | Granting broad write privileges speculatively |

## Verify minimally

Attempt the failing command in its owning environment if available. Use narrow pytest/targeted Makim before any full suite. Green checks on the *same commit* need not be repeated merely as ceremony; new source or environment revisions require appropriate validation. Do not increase timeouts or retries unless measurements show infrastructure flakiness rather than repeated work.

## Report

State exact URL/job, SHA, first failure, most likely root cause with supporting evidence, minimal fix, verification commands/results and remaining unknowns. If logs are unavailable, say so; do not invent causes.

**Done:** concrete diagnosis or explicit blocker, without unrelated CI/manifest changes.
