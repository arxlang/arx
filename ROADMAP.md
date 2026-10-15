# Native Apache Arrow C++ Roadmap

**Current priority:** finish M1-M4 and their outstanding earlier prerequisites
for a reviewable PR. Do not start M5-M10 as part of that completion effort.
**Status snapshot:** 2026-09-22.

This is the authoritative **current** milestone tracker. The
[design and implementation archive](docs/arrow-roadmap-archive.md) preserves all
detailed contracts, historical transitions, decisions, alternatives, and prior
test evidence. Its old status rows are not active assignments.

## Work in this pass

- **Selected item:** DOC-001 — scope communication and roadmap organization
  (**DONE**).
- **Included:** contributor rules, rename `PLAN.md` to `ROADMAP.md`, separate
  historical material, reconcile current progress, and expose the M1-M4 PR work.
- **Excluded:** compiler/runtime changes and implementation of any open M4 item.
- **Acceptance:** Markdown formatting, local links, preserved archive content,
  current-status consistency, and removal of stale active-file references.
- **Active milestone implementation:** none during this documentation pass.
- **Last completed implementation:** C7 — nullable list/tensor owners and
  current-frame list failure cleanup, within M4-002 and M2-006.
- **Next proposed implementation:** M4-002-A, managed by-value struct lifetime.
  It is **NOT STARTED**, not an implicit commitment that all M4 work is active.

Before the next implementation pass, announce its task IDs, included/excluded
work, and acceptance checks to the user. If scope changes, report that while
working. Finish with results against that same scope, not a surprise partial
milestone report.

## Status rules

| Status          | Meaning                                                                                                    |
| --------------- | ---------------------------------------------------------------------------------------------------------- |
| **NOT STARTED** | Implementation of this bounded item has not begun.                                                         |
| **IN PROGRESS** | The announced bounded item is actively being worked on now.                                                |
| **PARTIAL**     | Verified behavior exists, but stated acceptance is incomplete; active child work is identified separately. |
| **BLOCKED**     | A named condition prevents this specific item from proceeding.                                             |
| **DONE**        | This item's implementation and stated verification are complete.                                           |
| **DEFERRED**    | An explicitly recorded scope decision moved the item elsewhere; this is not completion.                    |

Update a completed item immediately with its observed evidence. At handoff,
leave no inactive item `IN PROGRESS`. Do not count a blocked test as missing
implementation, or a passing test suite as implementation of an absent feature.
The milestone table is a roll-up of the current item tables below; update them
together. Append detailed evidence and decisions to the archive, not another
competing current-status table.

## Milestone status

| Milestone                               | Status          | Current completion boundary                                                                       |
| --------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------- |
| M0 — contracts and design               | **DONE**        | Accepted architecture, API placement, ownership/null/schema contracts, capability inventory.      |
| M1 — native runtime and ABI             | **DONE**        | All ten M1 items; keep ABI compatibility and installed-artifact checks green.                     |
| M2 — ownership and cleanup              | **PARTIAL**     | Cycle/static lifetime policies, cross-frame fatal cleanup, full allocator sweeps and LSan remain. |
| M3 — logical types and schemas          | **PARTIAL**     | Descriptor implementation exists; M3-006 and combined Gate B verification remain open.            |
| M4 — first-class containers             | **PARTIAL**     | M4-001, M4-003 and M4-004 are done; M4-002 still needs general aggregate/element lifetimes.       |
| M5 — tensors and multidimensional data  | **NOT STARTED** | Future milestone; dynamic tensor bounds/shape work is not supplied by C7 owner validity.          |
| M6 — compute                            | **NOT STARTED** | Future milestone.                                                                                 |
| M7 — streaming, IPC and file formats    | **NOT STARTED** | Future unified surface; existing legacy IPC still needs its M2 fault coverage.                    |
| M8 — datasets and Acero                 | **NOT STARTED** | Future milestone.                                                                                 |
| M9 — packaging and distribution         | **NOT STARTED** | Future distribution stabilization; current feature wheel checks are still required now.           |
| M10 — hardening and support declaration | **NOT STARTED** | Future full-support declaration, not the M1-M4 PR.                                                |

## Completed M1-M4 work

These statuses carry forward verified implementation; this documentation pass
does not rerun their implementation checks. Original individual item
descriptions and evidence remain in the archive.

| Items                 | Status   | Implemented scope                                                                                                                                          |
| --------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M1-001 through M1-010 | **DONE** | Versioned native ABI/status/error/handle contracts, generated bindings, feature registration, compatibility and artifact/conformance checks.               |
| M2-001 through M2-008 | **DONE** | Current managed-value ownership metadata, retain/move/borrow, local cleanup, class/frame destruction and deterministic Python wrappers.                    |
| M2-011, M2-012        | **DONE** | Bounded lifecycle accounting, aggregate allocation guards and isolated generator resume cleanup.                                                           |
| M2-014, M2-015        | **DONE** | Covered builder failure atomicity and current-function fatal cleanup; this does not include cross-frame unwinding.                                         |
| M3-001 through M3-005 | **DONE** | Recursive logical modeling, canonical validation/conversion classification, physical sidecars, schema round trips and native descriptor syntax/operations. |
| M4-001                | **DONE** | Primitive nullable storage, validity queries, conversions and checked unwrap.                                                                              |
| M4-003                | **DONE** | Primitive/logical arrays, reusable builders, chunks, numeric buffer copies, checked C Data and packed buffer/bitmap constructors.                          |
| M4-004                | **DONE** | Variable-width/nested Arrow values, batches/tables, row selection, extension storage and explicit DataFrame/Series adapters.                               |

M4-002 already includes nullable operators, flow proofs, casts, opaque owners,
strings, legacy DataFrame/Series owners, class fields and C7 list/tensor owners.
**Nested Arrow values are not the same as recursively owned language collections
or by-value structs.** The former are implemented; the remaining latter cases
are listed explicitly below.

## Remaining implementation

Work in the following bounded order, announcing the selected part before edits.
No row in this queue is currently active. Suffixes A-C divide existing M4-002
requirements; M2-016 gives the already documented cross-frame gap its own ID.
These are bookkeeping clarifications, not added milestone scope.

| ID       | Status          | Remaining scope and acceptance                                                                                                                                                                                                                                                                                                           |
| -------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M4-002   | **PARTIAL**     | Complete A-C below while preserving the supported nullable owners and operators.                                                                                                                                                                                                                                                         |
| M4-002-A | **NOT STARTED** | Managed by-value struct lifetime: resolved field ownership and recursive retain/move/drop across construction, copies, replacement, calls, returns, partial failure and scope exits; positive native and negative semantic tests.                                                                                                        |
| M4-002-B | **NOT STARTED** | Recursive language collection/aggregate elements, including managed list/tuple storage: element ownership, safe copies/transfers, replacement and recursive destruction; empty/nested/alias/failure tests. Reuse A's lifetime machinery where applicable.                                                                                |
| M4-002-C | **NOT STARTED** | Nullable language collection elements: validity-preserving construction, conversion and access without reading absent payloads; combine with B for managed nested payloads and verify native cleanup.                                                                                                                                    |
| M2-013   | **PARTIAL**     | Finish supported cyclic-class and static-managed lifetime policies. Implement and document the chosen policies with mutation/alias/lifetime tests; existing rejection guards and string-field support alone are not completion. Record assumptions and the top three alternatives.                                                       |
| M2-016   | **NOT STARTED** | Cross-frame fatal cleanup: failure in a generated callee must release acquired caller/callee owners exactly once without invalidating error details. Verify nested calls, partial construction and real allocator failures. Current-frame cleanup remains M2-015/C7.                                                                     |
| M2-010   | **PARTIAL**     | Complete allocator-failure sweeps for implemented M1-M4 native operations, including move import and legacy IPC. Account for every fallible allocation stage, output clearing, callback consumption, retry safety and releases; not just entry failpoints. Future M6-M7 operations are tested when implemented, not pulled into this PR. |

The local implementation still diagnoses managed struct destruction, recursive
list ownership and nullable collection elements as unsupported in
`packages/irx/src/irx/analysis/`. These are implementation gaps, **not
environment blockers**. The existing runtime failure path cleans only the active
generated function. Do not report M4 or earlier partial milestones complete
while these requirements remain open.

## Remaining verification

| ID          | Status      | Required evidence or unblock condition                                                                                                                                                                                                            |
| ----------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M2-009      | **PARTIAL** | ASan/UBSan passed the native harness and 20 generated programs. Rerun after new ownership work and complete the LSan check below.                                                                                                                 |
| M2-009-LSAN | **BLOCKED** | The recorded local run failed because LSan cannot run under ptrace. Run the unmodified leak-enabled sanitizer task on a compatible runner and attach its actual result. Configured CI or `--skip-leak-detection` is not evidence of passing LSan. |
| M3-006      | **PARTIAL** | Native descriptor ABI is implemented; close its full failure/lifetime evidence and combined Gate B after the remaining M2/M4 work. Do not reimplement descriptors or mark this gate done based only on descriptor tests.                          |

The LSan restriction blocks that check only. It does not block the remaining
implementation or allocator tests. M3/M4's combined Gate B still requires
nullable/nested lifetimes, recursive schemas, variable-width buffers, field
destruction and offset/bitmap correctness; partial ownership is not a waiver.

## PR readiness for M1-M4

This is the completion target, not a claim that the PR is ready today. Preserve
M1's completed contracts and finish the current open rows; do not expand the PR
into later Arrow features.

- [x] M1 implementation is recorded complete; M4-001/003/004 are recorded done.
- [ ] Finish M4-002-A/B/C, M2-013 and M2-016 with cross-package tests and docs.
- [ ] Close M2-010 allocation sweeps and M2-009 leak/sanitizer evidence.
- [ ] Review and close M3-006/Gate B, then roll M2, M3 and M4 up to DONE.
- [ ] On the final implementation tree, run relevant package tests, LLVM/native
      checks, compiled Arx tests, ABI/capability freshness and conformance,
      Ruff/mypy/Douki, documentation and installed-wheel checks.
- [ ] Record actual required CI/platform/Python-matrix results and any unrun or
      blocked checks; do not infer them from local Python 3.14 success.
- [ ] Prepare a reviewable diff and Conventional Commit PR title, with scope,
      compatibility notes, decisions/alternatives and remaining future work. Do
      not create or mutate a remote PR unless requested.

Representative repository checks are `makim all.ci`, `makim all.typecheck`,
`makim all.lint`, `makim arx.check-syntax`, `makim irx.check-arrow-abi`,
`makim irx.check-arrow-capabilities`, `makim irx.check-arrow-abi-conformance`,
`makim irx.check-arrow-ownership-sanitizers`, `makim all.wheel-smoke` and
`makim docs.build`. Use focused checks first and report the exact commands run.

## Last recorded implementation verification

**Recorded on 2026-09-22 for C7; not rerun by this documentation pass.** The
[archive](docs/arrow-roadmap-archive.md) retains exact test targets, failed
attempts/fixes, assumptions and detailed evidence. Counts overlap.

| Check                                                   | Last recorded result                                                                       |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Complete IRx suite                                      | **1,494 passed** in 686.89 seconds.                                                        |
| Analysis/parser/lexer/ABI-capability selection          | **899 passed**.                                                                            |
| Ownership/runtime/nullable regression selection         | **275 passed**.                                                                            |
| Nullable collection/translate/allocation selection      | **30 passed**.                                                                             |
| Native sanitizer harness and generated programs         | **20 programs plus harness passed ASan/UBSan**; leak detection disabled, not an LSan pass. |
| Strict mypy                                             | Passed in all six packages.                                                                |
| Ruff, Douki, syntax, ABI/capability freshness           | Passed for the recorded change set.                                                        |
| ASTx/IRx/Arx builds and current-environment wheel smoke | Passed; not fresh isolated dependency resolution.                                          |

Full repository CI, Quarto build, Python 3.10-3.13, non-Linux execution and a
passing LSan run were not established by C7. Earlier evidence is dated history,
not a substitute for checks of the final PR tree.

## Architecture and scope constraints

- Arrow is Arx's core data model: builtin-first types, schemas, ownership,
  nullability and operations; no `import arrow` or `stdlib.arrow.*` namespace.
  Standard-library composition uses names such as `stdlib.compute` and
  `stdlib.io`, backed by the same native primitives.
- Arx owns syntax/discovery; ASTx owns reusable nodes/types; IRx analysis owns
  meaning and ownership; LLVM lowering consumes semantic sidecars. Keep the Arx
  codegen adapter small and never embed Arrow C++ layouts in LLVM.
- Opaque C ABI handles, checked statuses/output slots, explicit ownership and
  registered runtime features remain mandatory. No Python execution fallback.
- Preserve the accepted logical-type, schema, null, error, ABI, package and
  module-scope contracts in the archive. Do not reinterpret "full Arrow C++
  support" as exposing every upstream C++ method or as completing only M1-M4.
- Dynamic tensor bounds/shape work remains M5; Compute M6; unified streaming and
  formats M7; Dataset/Acero M8; distribution stabilization M9; full support
  hardening M10. Current native-asset/wheel checks are not deferred to M9.
- Keep the separate machine-validated foundation/capability inventory current in
  `docs/data/arrow-capabilities.json` and its generated matrix when behavior
  changes. This documentation-only reorganization changes no capability claims.

## Documentation maintenance record

| Date       | Item    | Status   | Scope and evidence                                                                                                                                                                                                                                |
| ---------- | ------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-09-22 | DOC-001 | **DONE** | Contributor guidance, concise current roadmap, archive and references updated. Prettier check, five local link targets, archive-content preservation, current-status/reference audit and whitespace checks passed. No implementation tests rerun. |

Future implementation passes should update the selected current row and add a
dated archive entry for the announced scope, results, decisions, assumptions and
top three alternatives where requested. Do not grow this dashboard into another
full historical transcript.
