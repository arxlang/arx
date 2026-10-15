# Native Arrow design and implementation archive

**Archived snapshot:** 2026-09-22, through implementation slice C7.

The root [ROADMAP.md](../ROADMAP.md) is the authoritative current tracker. This
file preserves the detailed design, original work-item descriptions, historical
transitions, assumptions, alternatives, and verification evidence from the
former `PLAN.md`.

**Status words below are historical, not active assignments.** In particular,
`NOT STARTED -> IN PROGRESS` records a past transition, not a task still being
worked on. Later entries may supersede earlier completion claims or test counts.
Use the root roadmap for current status, outstanding work, and PR readiness.

The accepted architecture and contracts remain design references unless a later
record explicitly changes them. Moving them here does not waive milestone exit
criteria. The former file's contradictory Git-ignore note is retired: it was
tracked, and this reorganization does not change tracking policy.

<!-- BEGIN PRESERVED ROADMAP BODY -->

## Implementation control

This document is the execution ledger as well as the design roadmap. Every
implementation change must reference a stable item ID. Set an item to **IN
PROGRESS** before changing code and change it to **DONE** only after its stated
evidence passes. Update the item immediately when it is completed, blocked, or
re-scoped; do not defer status updates until the end of a milestone.

| Status          | Meaning                                                       |
| --------------- | ------------------------------------------------------------- |
| **NOT STARTED** | No implementation work has begun.                             |
| **IN PROGRESS** | The item is the active bounded implementation slice.          |
| **PARTIAL**     | Checked baseline behavior exists, but completion is inactive. |
| **BLOCKED**     | Work cannot continue; the row must name the concrete blocker. |
| **DONE**        | The implementation and listed evidence are complete.          |
| **DEFERRED**    | The item was deliberately moved out of the current scope.     |

### Milestone status

| Milestone                               | Status          | Gate or dependency                   |
| --------------------------------------- | --------------- | ------------------------------------ |
| M0 — contracts and design decisions     | **DONE**        | None                                 |
| M1 — one native Arrow runtime and ABI   | **DONE**        | M0, Gate A                           |
| M2 — semantic ownership and cleanup     | **PARTIAL**     | M1 and current managed-value surface |
| M3 — complete logical types and schemas | **PARTIAL**     | M1-M2, Gate B                        |
| M4 — first-class containers             | **PARTIAL**     | M1-M3, Gate B                        |
| M5 — tensors and multidimensional data  | **NOT STARTED** | M1-M4                                |
| M6 — compute                            | **NOT STARTED** | M1-M4, Gate C                        |
| M7 — streaming, IPC, and file formats   | **NOT STARTED** | M1-M4, Gate D                        |
| M8 — datasets and Acero                 | **NOT STARTED** | M6-M7, Gate D                        |
| M9 — packaging and distribution         | **NOT STARTED** | M0-M8, Gate E                        |
| M10 — hardening and support declaration | **NOT STARTED** | M0-M9, Gate E                        |

### Milestone 0 work items

| ID     | Item                                                      | Status   | Evidence or blocker                |
| ------ | --------------------------------------------------------- | -------- | ---------------------------------- |
| M0-001 | Version `PLAN.md` and establish status control            | **DONE** | `PLAN.md`; `.gitignore`            |
| M0-002 | Generate the pinned Arrow capability inventory            | **DONE** | Manifest, matrix, task, and tests  |
| M0-003 | Convert the foundation readiness ledger to tracked rows   | **DONE** | 18 validated `FND-*` rows          |
| M0-004 | Fix public container and module naming policy             | **DONE** | Section 2.1                        |
| M0-005 | Classify each public operation by implementation layer    | **DONE** | 52 validated operation families    |
| M0-006 | Specify nullability semantics                             | **DONE** | Accepted `T \| none` contract      |
| M0-007 | Specify static- and dynamic-schema APIs                   | **DONE** | Accepted schema contract           |
| M0-008 | Specify ownership and value semantics                     | **DONE** | Accepted handle ownership contract |
| M0-009 | Specify language/runtime error contracts                  | **DONE** | Accepted status/error contract     |
| M0-010 | Decide binary distribution model                          | **DONE** | Dedicated runtime wheels           |
| M0-011 | Define the stable Arrow C ABI version policy              | **DONE** | Accepted ABI 1.0.0 policy          |
| M0-012 | Classify Arrow modules as core, optional, or out of scope | **DONE** | 29 classified module groups        |

### Progress log

| Date       | Item           | Transition                 | Evidence                                                                                                                                        |
| ---------- | -------------- | -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-09-03 | M0-001         | NOT STARTED -> DONE        | Plan is no longer ignored and now carries tracked states.                                                                                       |
| 2026-09-03 | M0-002         | NOT STARTED -> IN PROGRESS | Capability manifest and generated matrix started.                                                                                               |
| 2026-09-03 | M0-002         | IN PROGRESS -> DONE        | `makim irx.check-arrow-capabilities`; two tests pass.                                                                                           |
| 2026-09-03 | M0-003         | NOT STARTED -> IN PROGRESS | Validated foundation readiness rows started.                                                                                                    |
| 2026-09-03 | M0-003         | IN PROGRESS -> DONE        | 18 owners, states, test targets, and blockers validate.                                                                                         |
| 2026-09-03 | M0-004         | NOT STARTED -> DONE        | Builtin-first, unqualified naming is fixed in Section 2.1.                                                                                      |
| 2026-09-03 | M0-005         | NOT STARTED -> IN PROGRESS | Public operation placement catalog started.                                                                                                     |
| 2026-09-03 | M0-005         | IN PROGRESS -> DONE        | 52 families cover every capability and approved layer.                                                                                          |
| 2026-09-03 | M0-006         | NOT STARTED -> IN PROGRESS | Existing `T \| none` syntax selected for the null contract.                                                                                     |
| 2026-09-03 | M0-006         | IN PROGRESS -> DONE        | Type, flow, operator, container, and ABI rules recorded.                                                                                        |
| 2026-09-03 | M0-007         | NOT STARTED -> IN PROGRESS | Static and runtime schema contract started.                                                                                                     |
| 2026-09-03 | M0-007         | IN PROGRESS -> DONE        | Static identity and checked dynamic access rules recorded.                                                                                      |
| 2026-09-03 | M0-008         | NOT STARTED -> IN PROGRESS | Native handle ownership and value semantics started.                                                                                            |
| 2026-09-03 | M0-008         | IN PROGRESS -> DONE        | Share, move, borrow, view, and cleanup rules recorded.                                                                                          |
| 2026-09-03 | M0-009         | NOT STARTED -> IN PROGRESS | Unified status and language error policy started.                                                                                               |
| 2026-09-03 | M0-009         | IN PROGRESS -> DONE        | ABI status and recoverable/fatal policies recorded.                                                                                             |
| 2026-09-03 | M0-010         | NOT STARTED -> IN PROGRESS | Native runtime wheel strategy started.                                                                                                          |
| 2026-09-03 | M0-010         | IN PROGRESS -> DONE        | Dedicated core and optional runtime artifacts fixed.                                                                                            |
| 2026-09-03 | M0-011         | NOT STARTED -> IN PROGRESS | Unified C ABI v1 compatibility policy started.                                                                                                  |
| 2026-09-03 | M0-011         | IN PROGRESS -> DONE        | ABI 1.0.0 layout and compatibility rules recorded.                                                                                              |
| 2026-09-03 | M0-012         | NOT STARTED -> IN PROGRESS | Local Arrow 24 module tree classification started.                                                                                              |
| 2026-09-03 | M0-012         | IN PROGRESS -> DONE        | 29 groups cover all seven declared product scopes.                                                                                              |
| 2026-09-03 | M0             | IN PROGRESS -> DONE        | All 12 contract items and 11 focused checks complete.                                                                                           |
| 2026-09-03 | M1-001         | NOT STARTED -> IN PROGRESS | Packed Arrow ABI version query implementation started.                                                                                          |
| 2026-09-03 | M1-001         | IN PROGRESS -> DONE        | C harness and ctypes verify the native ABI 1.0.0 query.                                                                                         |
| 2026-09-03 | M1-002         | NOT STARTED -> IN PROGRESS | Stable status categories and error codes started.                                                                                               |
| 2026-09-03 | M1-002         | IN PROGRESS -> DONE        | Native ABI and 44 runtime tests use stable Arx statuses.                                                                                        |
| 2026-09-03 | M1-003         | NOT STARTED -> IN PROGRESS | Owned, thread-safe error detail implementation started.                                                                                         |
| 2026-09-03 | M1-003         | IN PROGRESS -> DONE        | Owned snapshots pass isolation, lifetime, and 64 regressions.                                                                                   |
| 2026-09-03 | M1-004         | NOT STARTED -> IN PROGRESS | Unified opaque-handle ownership implementation started.                                                                                         |
| 2026-09-03 | M1-004         | IN PROGRESS -> DONE        | ABI manifest and 50 Arrow ABI/runtime tests pass.                                                                                               |
| 2026-09-03 | M1-005         | NOT STARTED -> IN PROGRESS | Cross-language ABI declaration generation started.                                                                                              |
| 2026-09-03 | M1-005         | IN PROGRESS -> DONE        | 67 generated symbols have C/Python/LLVM parity; 55 tests pass.                                                                                  |
| 2026-09-04 | M1-009         | NOT STARTED -> IN PROGRESS | Capability-specific native artifact split started.                                                                                              |
| 2026-09-04 | M1-009         | IN PROGRESS -> DONE        | 21 feature tests and all 983 IRx tests pass.                                                                                                    |
| 2026-09-04 | M1-010         | NOT STARTED -> IN PROGRESS | Installed ABI conformance gates started.                                                                                                        |
| 2026-09-04 | M1-010         | IN PROGRESS -> DONE        | GCC/Clang, wheel, symbol, and all 995 IRx tests pass.                                                                                           |
| 2026-09-04 | M1             | IN PROGRESS -> DONE        | All ten native runtime and ABI work items are complete.                                                                                         |
| 2026-09-04 | M2-001         | NOT STARTED -> IN PROGRESS | Arrow semantic resource descriptors started.                                                                                                    |
| 2026-09-04 | M2-001         | IN PROGRESS -> DONE        | Nine ownership tests and all 1,004 IRx tests pass.                                                                                              |
| 2026-09-05 | M2-002         | NOT STARTED -> IN PROGRESS | Current Arrow expression and binding ownership flow started.                                                                                    |
| 2026-09-05 | M2-002         | IN PROGRESS -> PARTIAL     | Current types carry ownership; future M3-M7 types remain.                                                                                       |
| 2026-09-05 | M2-003         | NOT STARTED -> IN PROGRESS | Retained table-column projection contract started.                                                                                              |
| 2026-09-05 | M2-003         | IN PROGRESS -> DONE        | Parent-first and child-first native release tests pass.                                                                                         |
| 2026-09-05 | M2-004         | NOT STARTED -> IN PROGRESS | Generic semantic cleanup lowering started.                                                                                                      |
| 2026-09-05 | M2-004         | IN PROGRESS -> DONE        | All current exit and partial-build paths use slot cleanup.                                                                                      |
| 2026-09-05 | M2-005         | NOT STARTED -> IN PROGRESS | Move-safe, terminator-safe cleanup hardening started.                                                                                           |
| 2026-09-05 | M2-005         | IN PROGRESS -> DONE        | Releases null slots; generated LLVM has no late cleanup.                                                                                        |
| 2026-09-05 | M2-006         | NOT STARTED -> IN PROGRESS | Aggregate and suspended-frame ownership audit started.                                                                                          |
| 2026-09-05 | M2-006         | IN PROGRESS -> PARTIAL     | Owners fail closed until aggregate destruction exists.                                                                                          |
| 2026-09-05 | M2-007         | NOT STARTED -> IN PROGRESS | Borrowed and retained view ownership started.                                                                                                   |
| 2026-09-05 | M2-007         | IN PROGRESS -> PARTIAL     | Buffer, tensor, and table-column views are explicit.                                                                                            |
| 2026-09-05 | M2-008         | NOT STARTED -> IN PROGRESS | Deterministic Python wrapper lifecycle hardening started.                                                                                       |
| 2026-09-05 | M2-008         | IN PROGRESS -> DONE        | Core and stream wrappers close and fail closed.                                                                                                 |
| 2026-09-05 | M2-009         | NOT STARTED -> IN PROGRESS | Native ownership sanitizer gate started.                                                                                                        |
| 2026-09-05 | M2-009         | IN PROGRESS -> PARTIAL     | ASan/UBSan pass; local ptrace blocks LSan execution.                                                                                            |
| 2026-09-05 | M2-010         | NOT STARTED -> IN PROGRESS | Test-only native handle allocation failpoint started.                                                                                           |
| 2026-09-05 | M2-010         | IN PROGRESS -> PARTIAL     | Current creation/finish/projection OOM paths pass.                                                                                              |
| 2026-09-05 | M2-011         | NOT STARTED -> IN PROGRESS | Bounded lifecycle and release-order checks started.                                                                                             |
| 2026-09-05 | M2-011         | IN PROGRESS -> DONE        | 256 iterations and both parent/child orders pass.                                                                                               |
| 2026-09-05 | M2             | IN PROGRESS -> PARTIAL     | 1,014-test suite and 13-test ownership rerun pass.                                                                                              |
| 2026-09-05 | M2-002         | PARTIAL -> DONE            | All modeled expression and binding sites carry ownership.                                                                                       |
| 2026-09-05 | M2-006         | PARTIAL -> DONE            | Class destructors and generator-frame close cleanup pass.                                                                                       |
| 2026-09-05 | M2-007         | PARTIAL -> DONE            | Borrowed and retained views preserve parent/root ownership.                                                                                     |
| 2026-09-05 | M2-009         | PARTIAL -> DONE            | Sanitizer CI gate added; local ASan/UBSan harness passes.                                                                                       |
| 2026-09-05 | M2-010         | PARTIAL -> DONE            | Allocation failures leave current inputs retry-safe.                                                                                            |
| 2026-09-05 | M2             | PARTIAL -> DONE            | All 11 work items meet current-surface acceptance criteria.                                                                                     |
| 2026-09-16 | M2-009/010/011 | DONE -> PARTIAL            | Reopened: configured CI is not a passing LSan run; entry failpoints and iteration counts are not full allocator/memory evidence.                |
| 2026-09-16 | M2-012         | NOT STARTED -> DONE        | Allocation guards, MCJIT runtime loading, isolated resume cleanup; real malloc-failure regressions pass.                                        |
| 2026-09-16 | M2-013         | NOT STARTED -> PARTIAL     | Reject unsafe heap-string field initialization; remaining storage policies tracked explicitly.                                                  |
| 2026-09-16 | M3-001/002     | NOT STARTED -> DONE        | Immutable descriptors, canonical validation, structural type identity and conservative conversions; focused ASTx/IRx tests pass.                |
| 2026-09-16 | M3-004         | NOT STARTED -> DONE        | Every modeled logical family passes host C Data, IPC schema and native recursive-field round trips.                                             |
| 2026-09-16 | M3-003/006     | NOT STARTED -> PARTIAL     | Shared scalar/physical mapping and recursive native schema copying; source operations and dedicated descriptor handles remain.                  |
| 2026-09-16 | M2-011         | PARTIAL -> DONE            | Live Arrow-pool accounting over 256 iterations and wrapped malloc/free accounting in a generated owning-local loop pass.                        |
| 2026-09-16 | M1-006         | DONE (updated)             | Array feature contract 1.1.0 advertises recursive schema support; C ABI 1.0.0 remains baseline-compatible.                                      |
| 2026-09-17 | M2-009/010     | PARTIAL -> IN PROGRESS     | Generated ownership sanitizer programs and real allocator-failure probes started.                                                               |
| 2026-09-17 | M2-014/015     | NOT STARTED -> DONE        | Retry-safe primitive/Tensor builders and cleanup-aware fatal paths pass allocator/accounting regressions.                                       |
| 2026-09-17 | M2-009/010     | IN PROGRESS -> PARTIAL     | Expanded probes pass; LSan remains ptrace-blocked and remaining operation sweeps are incomplete.                                                |
| 2026-09-18 | M3-003/005     | IN PROGRESS -> DONE        | Builtin descriptor construction, closed inspection and compile-time conversion classification lower from resolved sidecars to native Arrow C++. |
| 2026-09-18 | M3-006         | IN PROGRESS -> PARTIAL     | Dedicated type/field ABI and lifecycle paths implemented; combined Gate B and complete sanitizer/fault coverage remain open.                    |
| 2026-09-21 | M4-002/003/004 | PARTIAL -> PARTIAL         | Logical scalars, nested values, optional classes, buffer copies and row selection implemented; external/legacy/general-nullable gaps remain.    |

Latest 2026-09-22 closure: M4-003 and M4-004 are **DONE** (C1–C3); M4-002
remains **PARTIAL**, with nullable strings and legacy DataFrame/Series owners
now implemented (C4/C6). Nullable by-value list/tensor owner cleanup is also
implemented (C7). Remaining aggregate and M2/M3 verification gaps are recorded
at the end of this plan.

### Verification — 2026-09-16

Local checks on Python 3.14.3, against the working tree (not a remote branch):

| Check                                                                                                                  | Result                                                                          |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `pytest -q packages/irx/tests packages/astx/tests`                                                                     | **1,758 passed** in 381.82 seconds                                              |
| `pytest -q packages/arx/tests/python/test_codegen_ast_output.py packages/arx/tests/python/test_codegen_file_object.py` | **26 passed**                                                                   |
| `makim arx.test-compiled`                                                                                              | **30 passed**, zero failures                                                    |
| `mypy src` from `packages/astx` and `packages/irx`                                                                     | Success: 54 and 141 source files respectively                                   |
| `ruff check --no-fix` and `ruff format --check` on all 66 changed Python files                                         | Passed; separate checks of all scripts and the full IRx source tree also passed |
| `douki sync` on all 66 changed Python files                                                                            | Idempotent: zero updates                                                        |
| `python scripts/gen_arrow_abi.py --check`                                                                              | Passed                                                                          |
| `python scripts/gen_arrow_capability_matrix.py --check`                                                                | Passed                                                                          |
| `python scripts/check_arrow_abi_compatibility.py`                                                                      | ABI 1.0.0 satisfies the recorded baseline                                       |
| `python scripts/gen_api_docs.py`                                                                                       | Passed                                                                          |
| `git diff --check`                                                                                                     | Passed                                                                          |

The earlier
`pytest -q -n 2 packages/irx/tests packages/astx/tests --durations=5` run had
1,757 passes and one 60-second subprocess timeout in
`test_record_batch_build_lock_recovers_after_owner_exits`. An isolated retry
passed (19.16 seconds), followed by the clean full serial run above. The test's
timeout was not relaxed.

The native ownership harness passes ASan/UBSan with
`python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`.
Running without that flag failed because LeakSanitizer cannot run under this
sandbox's ptrace environment; this is not a passing leak check. CI keeps LSan
enabled but its result has not been observed here. Arrow-pool accounting and the
generated generator-loop malloc/free accounting cover bounded cases, not all
possible class graphs or allocator failures.

The four new IRx schema/interop modules also passed Bandit (`-iii -lll`) and
Vulture (`--min-confidence 80`). McCabe (`--min 10`) reports complexities 21 and
17 in the parameter/nested validators; it is not a zero-warning result. The full
pre-commit/Prettier stack, Quarto `docs.build`, installed-wheel checks, and the
Python 3.10–3.13 matrix were not run in this slice.

**Current scope remaining (2026-09-18):** descriptor literals, dedicated owners,
physical sidecars and native inspection now execute. M3-006 and Gate B remain
partial: complete nullable semantics, general nested/variable-width containers
and complete offset/bitmap guarantees are not descriptor features. M2 retains
LSan, remaining allocator-operation sweeps and aggregate storage/cycle work. See
the latest decision and verification record at the end of this file.

## 1. Objective

Arx should be able to declare, construct, pass, return, transform, stream,
persist, and exchange Arrow-backed values without routing execution through
Python. Generated LLVM must call a stable IRx C ABI whose implementation owns
all Arrow C++ objects and invokes Arrow C++ APIs.

This plan uses **full Arrow C++ support** to mean:

1. The Arrow logical type system has an explicit Arx/ASTx/IRx mapping.
2. Core Arrow containers have first-class ownership and language semantics.
3. A curated, typed surface exposes the useful Arrow Compute and Acero
   operations; Arx does not become a second SQL engine or expose arbitrary C++
   classes.
4. Arrow C Data, C Stream, IPC, PyArrow, and file-format interoperability are
   supported with documented copy and zero-copy behavior.
5. Native artifacts are installable and executable on supported platforms
   without a source checkout.
6. Every Arrow C++ module in the supported Arrow release is classified as
   language-facing, library-facing, interoperability-only, optional, or
   intentionally out of scope.

“Full” does not mean mirroring every Arrow C++ method in Arx syntax. Internal,
unstable, testing-only, benchmark-only, and third-party connector APIs remain
outside the language contract. Flight, Substrait, device backends, and optional
filesystem providers are separate runtime features rather than mandatory core
language dependencies.

## 2. Non-negotiable architecture

The implementation must preserve these boundaries:

```text
.x source
  -> Arx lexer/parser
  -> reusable ASTx types and operation nodes
  -> IRx semantic sidecars
  -> IRx LLVM lowering
  -> feature-gated irx_arrow_* C ABI
  -> opaque Arrow C++ objects
```

- Arx owns syntax and parser diagnostics.
- ASTx owns reusable data types and operation nodes, not Arrow C++ behavior.
- IRx analysis owns schemas, type validity, null rules, kernel resolution,
  ownership, conversions, and shape rules.
- IRx lowering consumes resolved semantic metadata and never re-resolves a
  schema, type, kernel, ownership transfer, or conversion.
- Arrow C++ layouts never appear in LLVM IR. LLVM sees opaque handles and stable
  plain C structs only.
- Native code is activated only through registered runtime features.
- `packages/arx/src/arx/codegen.py` remains an integration adapter and does not
  acquire general Arrow lowering.
- Every status/output-slot call initializes its output, checks status, and
  records ownership only after success.
- Zero-copy is promised only for individually documented operations with
  lifetime tests. It is not a blanket property of Arrow support.

## 2.1 Builtin-first support policy

Arrow support is **builtin-first**. Anything that determines static type,
schema, ownership, null behavior, ABI representation, runtime feature
activation, or kernel selection is a compiler/runtime builtin. The standard
library may organize and compose those builtins, but it must not be a fallback
Python implementation of Arrow behavior.

Arrow is the core data model of Arx, not an optional foreign library. Public Arx
source therefore does **not** use an `arrow` namespace and does not require an
`import arrow`. Users work with Arx types such as Array, Series, DataFrame,
Table, RecordBatch, Tensor, and Stream directly. Documentation may explain that
these are implemented by Arrow C++, but the surface remains Arx-native.

Public standard-library modules use domain names such as `stdlib.compute`,
`stdlib.io`, and `stdlib.dataset`, not `stdlib.arrow.compute`,
`stdlib.arrow.io`, or `stdlib.arrow.dataset`. Optional integrations follow the
same rule, for example a Flight or Substrait module is named for the capability
rather than being nested under `arrow`.

An `arrow/` directory may still be used inside ASTx, IRx, the compiler, native
runtime, or packaged standard-library implementation when it improves code
ownership. That directory is an implementation detail. If internal modules need
it, a public facade must expose the unqualified Arx module name and user
programs must not import the internal path.

“Builtin” does not mean “add a keyword or parser special case for every Arrow
API.” Arx should distinguish three layers:

1. **Compiler intrinsics:** concepts understood by ASTx and IRx semantics and
   lowered directly to feature-gated native ABI calls.
2. **Bundled builtin modules:** compiler-provided declarations or operations
   that need intrinsic behavior but do not need to pollute the ambient
   namespace.
3. **Standard-library modules:** stable, documented Arx APIs built from
   intrinsics and builtin declarations. These still execute through Arrow C++
   and remain fully native.

The default placement is:

| Capability                                                                                                  | Placement                                                            | Reason                                                                         |
| ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Arrow logical types, recursive fields, schema and nullability                                               | Compiler builtin                                                     | Required for static checking and physical representation                       |
| Array, Series/ChunkedArray, RecordBatch, Table/DataFrame, Tensor, stream and dataset types                  | Compiler builtin                                                     | Ownership, calls, returns, and lowering require compiler knowledge             |
| Literals/builders, indexing, field projection, length/shape, slicing, casts, iteration, and null inspection | Compiler builtin                                                     | These establish core language semantics and safety                             |
| Retain/release/move/view operations                                                                         | Internal compiler builtin                                            | Users should receive safe value semantics, not manually balance native handles |
| Compute kernel signature and option resolution                                                              | Compiler builtin registry                                            | Kernel choice and result types must be resolved before lowering                |
| Common arithmetic, comparison, Boolean, selection, and aggregate operations                                 | Builtin operators/methods where natural                              | They should feel like native collection operations                             |
| Long-tail compute functions and option constructors                                                         | Bundled builtin or `stdlib.compute`                                  | Avoid keywords while retaining typed intrinsic lowering                        |
| IPC, CSV, JSON, Parquet and filesystem APIs                                                                 | `stdlib.io` backed by native builtins                                | These are library APIs with substantial policy/options, not language syntax    |
| Dataset scanning and Acero plan construction                                                                | Builtin handle/expression types plus `stdlib.dataset`                | Static expression safety is builtin; orchestration is a library concern        |
| Flight, Substrait, cloud filesystems, DLPack and device adapters                                            | Optional standard-library modules backed by optional native features | Keep heavyweight or environment-specific dependencies out of core programs     |
| Convenience algorithms expressible in Arx                                                                   | Standard library                                                     | Prefer ordinary Arx composition once the primitives are sufficient             |

The authoritative operation-family catalog is stored in
`docs/data/arrow-capabilities.json` and rendered in
`docs/arrow-capability-matrix.md`. It assigns a stable ID, public surface,
visibility, implementation layer, public module, blocking milestone, related
capabilities, and rationale to every currently proposed operation family. The
validator rejects unknown layers and capability references, incomplete coverage,
incorrect domain facades, duplicate IDs, and a public `arrow` namespace.

Canonical public source names follow the existing lowercase builtin-type
convention:

| Concept                    | Canonical Arx source name                  | Compatibility rule                                               |
| -------------------------- | ------------------------------------------ | ---------------------------------------------------------------- |
| Scalar                     | The ordinary scalar `T` or `T \| none`     | Do not wrap scalars in an Arrow-branded type                     |
| Buffer                     | `buffer[T]`                                | Raw layout and owners remain internal                            |
| Array                      | `array[T]`                                 | New builtin type and constructor                                 |
| ChunkedArray               | `series[T]`                                | Preserve the existing name; ChunkedArray is internal terminology |
| RecordBatch                | `recordbatch[...]`                         | New builtin type and constructor                                 |
| Table                      | `dataframe[...]`                           | Preserve the existing name; Table is internal terminology        |
| Tensor                     | `tensor[T, ...]`                           | Preserve existing static and runtime-shaped forms                |
| Stream                     | `stream[T]`                                | New builtin owning stream type                                   |
| Schema                     | `schema[...]`                              | New builtin recursive schema descriptor                          |
| Recoverable result         | `result[T, data_error]`                    | Core typed success/error control flow                            |
| Dataset and scanner        | `dataset[...]`, `scanner[...]`             | Builtin handle types orchestrated by `stdlib.dataset`            |
| Execution plan and context | `execution_plan[...]`, `execution_context` | Builtin opaque types returned by domain modules                  |

Internal Python, ASTx, and C++ classes may retain conventional names such as
`RecordBatch`, `ChunkedArray`, and `Table`; this table governs Arx source.

Core Arrow type constructors should be available as builtins, following the
existing `tensor`, `dataframe`, and `series` direction. Only the smallest, most
common set should be ambient. Domain-oriented builtin/stdlib modules should
carry specialized types, options, I/O, datasets, and advanced kernels without
exposing an `arrow` namespace.

An API belongs in the compiler/builtin layer if any of these are true:

- its result type or schema cannot be derived in ordinary Arx;
- it creates, borrows, shares, moves, or releases an opaque native resource;
- it changes nullability, shape, chunking, ordering, or physical encoding;
- it selects an Arrow kernel or activates native runtime/link features; or
- implementing it in ordinary Arx would require exposing Arrow C++ layout.

An API belongs in the standard library when it can be expressed entirely in
terms of stable typed builtins, primarily supplies defaults/options/policy, or
composes operations without new ownership or lowering rules.

The implementation should migrate type-dependent behavior out of parser scope
tracking where possible. The parser should recognize approved syntax and emit
ASTx; IRx semantic analysis should decide whether an operation is valid. A
builtin-first strategy must not grow a second semantic analyzer in Arx.

Placement tests must prove that:

- core types and operations work without importing an implementation package;
- builtin and domain-oriented standard-library APIs resolve reproducibly without
  an `arrow` import or qualifier;
- standard-library wrappers activate the same native features as direct
  intrinsics;
- unused optional modules do not add Arrow libraries or artifacts to a build;
- no supported Arrow operation falls back to PyArrow or Python at execution; and
- installed wheels contain all builtin and standard-library source assets.

## 3. Current repository baseline

The repository already contains substantial pieces that should be extended, not
replaced:

- `irx_arrow_*` wraps primitive arrays, schemas, dense tensors, tables, and
  chunked arrays behind opaque C++ handles.
- Primitive array support covers signed and unsigned integers, floats, Boolean
  values, null metadata, Arrow C Data import/export, and readonly buffer views.
- `irx_rb_*` separately wraps RecordBatch schemas, builders, values, and IPC
  streams. It covers numeric and Boolean values, UTF-8 and large UTF-8, date,
  timestamp, time, fixed-width list children, and fixed-width struct fields.
- ASTx models Tensor, DataFrame, and Series values and operations. Its array
  node is currently only an internal int32 length helper.
- Arx exposes fixed-shape numeric `tensor`, numeric/Boolean static-schema
  `dataframe`, and typed `series` values.
- IRx runtime features compile native sources on demand and obtain Arrow 24.0.0
  headers/sources from `arx-arrowcpp-sources` and shared libraries from PyArrow
  24.x.
- Python and native tests exercise Arrow C Data, IPC, PyArrow round trips,
  ownership primitives, tensors, DataFrames, lists, structs, nulls, and error
  paths.

Important gaps:

- The array and RecordBatch runtimes have separate type enumerations, error
  models, handles, build paths, and ABI declarations.
- Arrow handles are not yet integrated into the general IRx `ResourceOwnership`
  model used by strings and dynamic lists.
- Arx has no first-class general Arrow Array, RecordBatch, Table, stream,
  compute, dataset, or file-format surface.
- Arx DataFrames do not yet expose nullable, string, binary, temporal, decimal,
  dictionary, or nested columns.
- Runtime-schema DataFrame access and runtime-shaped Tensor indexing are
  incomplete.
- Tensor storage is readonly and dense fixed-width numeric support is narrow.
- Arrow C Stream is declared in the local ABI header but is not the general
  streaming boundary.
- Native builds rely on the header/library compatibility of two Python
  distributions and active CI is Ubuntu-only.

Before starting a milestone, refresh this baseline against the checked-out code.
Documentation or an AST class alone is not evidence of end-to-end support.

## 4. Definition of the supported Arrow surface

Milestone 0 must produce a versioned capability matrix. At minimum it must
classify the following Arrow 24 families.

### 4.1 Logical types

| Family                                       | Required target                                                             |
| -------------------------------------------- | --------------------------------------------------------------------------- |
| Null and Boolean                             | Full construction, null propagation, scalar access, and interchange         |
| Signed/unsigned integers and floats          | Full core support                                                           |
| Binary, large binary, binary view            | Full core support                                                           |
| UTF-8, large UTF-8, string view              | Full core support with Unicode-safe Arx conversion                          |
| Fixed-size binary                            | Full core support                                                           |
| Decimal32/64/128/256                         | Schema, construction, casts, comparison, arithmetic where Arrow supports it |
| Date, time, timestamp, duration, interval    | Units and timezone metadata preserved and validated                         |
| List, large list, fixed-size list, list view | Recursive type and null support                                             |
| Struct and map                               | Recursive field schemas and null support                                    |
| Sparse and dense union                       | Construction, inspection, interchange, and supported compute behavior       |
| Dictionary                                   | Index/value typing, ordered metadata, encode/decode, and interchange        |
| Run-end encoded                              | Construction, inspection, decode, and interchange                           |
| Extension types                              | Preserve storage and metadata; execute only registered extensions           |

New Arrow types introduced by a supported Arrow upgrade must default to
unsupported with an actionable diagnostic until the matrix and tests are
updated. Never silently coerce an unknown Arrow type.

### 4.2 Containers and execution modules

Required core containers are Scalar, Buffer, Array, ChunkedArray, RecordBatch,
Table, dense Tensor, and the Arrow C Data/C Stream objects used at boundaries.
Sparse tensors, Dataset, Scanner, filesystem, CSV, JSON, Parquet, Acero, Flight,
Substrait, and device/DLPack support are staged features with separate link
dependencies.

#### Accepted upstream module scope (M0-012)

The Arrow 24 C++ tree is classified in the generated capability matrix. Its 29
module groups use these product scopes:

- **Core language/runtime:** the logical data model, core containers, Tensor,
  and Compute. Common operations are ambient builtins; long-tail kernels use
  `stdlib.compute`.
- **Standard library:** Acero, IPC, CSV, JSON, Parquet, local filesystem, and
  Dataset through `stdlib.io` or `stdlib.dataset`.
- **Interoperability only:** Arrow C Data/C Stream, C++ STL adapters, and the
  Python bridge. C/C++ bridges stay internal and Python conversion belongs to
  ArxPy.
- **Optional:** Flight/Flight SQL, Substrait, cloud and HDFS filesystems, device
  and GPU backends, ORC, Parquet encryption, and interpreted Parquet geospatial
  support. Each is feature-gated and has no link effect when unused.
- **Preserve only:** unregistered Arrow extension types retain their storage and
  metadata but have no execution semantics.
- **Internal implementation:** Arrow I/O primitives, telemetry, utilities,
  generated headers, and vendored code inherit the runtime feature that uses
  them and have no public Arx namespace.
- **Out of scope:** Gandiva, the TensorFlow adapter, upstream testing and
  integration utilities, benchmarks, examples, fuzzers, and command-line tools.
  Gandiva would duplicate IRx/LLVM and typed Compute lowering; framework
  adapters belong in external ecosystem packages.

Internal subdirectories inherit their nearest listed module group unless an
explicit row overrides them. A new public Arrow module or library introduced by
an Arrow upgrade defaults to unsupported and out of the release claim until its
scope, packaging, feature ID, dependencies, semantics, and tests are added to
the manifest. The phrase “full Arrow support” therefore means full support for
the declared core and standard-library scopes, accurate optional and
preserve-only behavior, and explicit diagnostics for everything else—not an
unchecked mirror of every C++ symbol.

### 4.3 Core Arx foundations required by Arrow

Arrow is core to Arx, but Arrow features must not conceal missing language or
compiler foundations. If a vertical slice needs a capability below, implement
that capability in its owning Arx, ASTx, or IRx layer first. Do not solve it
with parser-side type tracking, untyped kernel strings, leaked handles,
process-lifetime allocation, or a one-off C++ call from lowering.

#### Foundation readiness ledger

The authoritative tracked rows live in `docs/data/arrow-capabilities.json` and
are rendered with stable `FND-*` IDs in `docs/arrow-capability-matrix.md`. Each
generated row includes its owner, status, concrete test targets, and blocking
milestones. The `irx.check-arrow-capabilities` task rejects missing fields,
nonexistent test targets, invalid milestones, duplicate IDs, and stale generated
output. The table below retains the design baseline and completion contract.

| Foundation                              | Current baseline                                                                                                           | Required completion                                                                                                                     |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Scalar numerics and Boolean             | Core signed/unsigned integers, floats, casts, and Boolean rules exist                                                      | Define exact Arrow cast, overflow, comparison, NaN, and non-finite behavior                                                             |
| Null values                             | Primitive nullable storage, validity queries, checked unwrap and local/call/return conversion exist                        | Complete nullable operators, managed payloads, array extraction and flow-sensitive branch behavior                                      |
| Strings and bytes                       | UTF-8 strings exist; Arrow RecordBatch supports UTF-8 internally                                                           | Add owned/borrowed binary values, large offsets, Unicode conversion, view lifetimes, and zero-copy rules                                |
| Decimal values                          | ASTx reserves decimal data-type kinds                                                                                      | Add Arx literals/types, precision and scale checking, 32/64/128/256-bit representation, arithmetic, casts, and ABI rules                |
| Temporal values                         | Date, time, timestamp, and datetime types/literals exist                                                                   | Add Arrow units, duration/interval types, timezone metadata, range checking, and conversion policy                                      |
| Parametric and structural types         | Templates, tensors, DataFrames, structs, and unions provide partial foundations                                            | Support recursive schema parameters, fixed sizes, dictionary/index types, union codes, field nullability, and canonical equality        |
| Compile-time values                     | Tensor dimensions and DataFrame fields carry selected static metadata                                                      | Provide checked type parameters for dimensions, decimal precision/scale, time units, fixed sizes, and schema fields                     |
| Ownership and destruction               | Managed values have semantic ownership across handles, views, fields, calls, returns, temporaries, classes, and generators | Extend the same mandatory contract with each later container, compute, stream, dataset, and file operation                              |
| Buffer and bitmap model                 | `irx_buffer_view` models data, owner, dtype, shape, strides, offset, and flags                                             | Add checked dynamic bounds, validity bitmap operations, variable-width offsets, alignment, endianness, and large-buffer overflow checks |
| Collection sizes and indices            | Existing APIs mix static metadata and integer result widths                                                                | Standardize Arrow lengths, row counts, offsets, and indices on checked `i64` semantics and narrow only explicitly                       |
| Methods, overloads, and intrinsics      | Typed calls and semantic sidecars exist                                                                                    | Add one typed builtin/intrinsic registry for container methods and kernels; lowering consumes only resolved entries                     |
| Error handling                          | Structured compile/link/runtime diagnostics and integer native statuses exist                                              | Define one recoverable/fatal operation contract, error propagation, cleanup during failure, and stable user-visible categories          |
| Iteration and streaming                 | List iteration and initial generators exist                                                                                | Define Array/Series iteration, batch-stream EOF, early close, cancellation, backpressure, and deterministic stream cleanup              |
| Classes and aggregate storage           | Classes have shared references and reverse-order managed-field destruction                                                 | Reuse aggregate ownership rules for future owning structs and schema-defined container records                                          |
| FFI and opaque handles                  | C externs and opaque handles exist                                                                                         | Add nullability, ownership annotations, C Data/C Stream contracts, callbacks only where required, and ABI conformance checks            |
| Modules, builtins, and standard library | Ambient builtins, bundled builtin modules, and a small stdlib exist                                                        | Define stable intrinsic registration and public facades without exposing an `arrow` import or internal module paths                     |
| Execution context                       | Runtime features can add native artifacts and linker flags                                                                 | Add memory pool, allocator, thread count, cancellation, resource limits, and optional device selection                                  |
| Native packaging                        | Runtime sources build on demand from Arrow/PyArrow metadata                                                                | Provide matched headers/libraries, platform discovery, clean-wheel execution, and cross-platform CI                                     |

The ledger is a tracked implementation artifact, not only prose. Each row must
have an owner, status, tests, and the first Arrow milestone it blocks.

#### Mandatory core semantics

Before broadening the Arrow surface, Arx needs these common rules.

1. **Nullable scalar model**

   - A nullable element is a value plus validity, not a zero value and not an
     unchecked pointer.
   - Analysis defines how null participates in assignment, calls, returns,
     comparisons, Boolean logic, casts, aggregates, and pattern/branch tests.
   - Scalar extraction checks validity before accessing data.
   - Schema nullability and value nullability use one compatible model.

2. **Recursive type and schema model**

   - One canonical representation covers fields, children, metadata,
     dictionaries, unions, fixed sizes, decimal parameters, time units, and
     timezones.
   - Equality distinguishes logical compatibility from exact physical and
     metadata equality.
   - Recursive validation has depth and size limits and rejects cycles that
     Arrow cannot represent.

3. **General resource semantics**

   - Owned, borrowed, shared, moved, static, and view values are resolved in IRx
     analysis.
   - Cleanup covers normal exits, all terminators, partial initialization,
     failed native operations, early stream exit, and abandoned iteration.
   - Aggregates recursively destroy owned fields in a specified order.
   - Users do not manually balance Arrow reference counts in ordinary Arx.

4. **Safe sizes, offsets, and indexing**

   - Logical lengths and offsets use checked signed 64-bit values compatible
     with Arrow.
   - All multiplication, addition, byte-size, and offset calculations detect
     overflow before allocation or address calculation.
   - Static bounds fail during analysis when provable; dynamic bounds use a
     checked runtime path unless an explicit unsafe mode is designed later.
   - Bit-packed Boolean and validity buffers have bit-aware access rather than
     pretending to be byte arrays.

5. **Binary, string, decimal, and temporal scalar support**

   - Variable-width data has explicit owner/view lifetime and offset-width
     semantics.
   - Decimal values have exact precision/scale and never pass through float as
     an implementation shortcut.
   - Temporal values preserve units and timezones and reject ambiguous lossy
     conversions.
   - These scalar rules land before claiming their Array or DataFrame columns
     are language-supported.

6. **Typed builtin and overload resolution**

   - Container operations and compute functions resolve through one typed
     semantic registry.
   - Overloads account for scalar/container shape, nullability, schema,
     promotion, options, and result ownership.
   - The frontend emits normal reusable ASTx nodes and does not choose native
     symbols.
   - Lowering receives a resolved operation ID, exact result type, normalized
     options, ownership action, and required runtime features.

7. **Operation failure model**

   - Every fallible operation has a defined user-visible behavior.
   - Recoverable errors and fatal invariant violations are not conflated.
   - Native errors retain structured category, operation context, and safe
     message text across the C ABI.
   - Failure paths run cleanup and never read unsuccessful output slots.

8. **Iteration, streams, and cancellation**

   - Iteration defines the yielded type, ordering, chunk/batch boundaries, and
     owner lifetime.
   - EOF is distinct from failure.
   - Early loop exit closes or releases stream state deterministically.
   - Streaming and Acero/Dataset execution share cancellation, thread, memory,
     and backpressure controls.

9. **Builtin/stdlib declaration mechanism**

   - Compiler intrinsics have stable identities independent of their source
     spelling or module facade.
   - Public stdlib wrappers are typed Arx code or compiler-known declarations,
     not Python callbacks.
   - Feature activation is transitive and based on resolved operations, not on
     importing a module alone.

10. **Native build and compatibility model**
    - Header version, shared-library version, enabled Arrow components, C++ ABI,
      compiler/runtime library, and platform are validated together.
    - Compiler caches and produced artifacts include those inputs in their
      identity.
    - The same contract works from a clean installed wheel and a source tree.

#### Accepted nullability contract (M0-006)

Arx reuses its existing union spelling instead of adding nullable-only syntax.
`T | none` is the canonical source form for a nullable `T`; this plan does not
introduce `T?`. Union order and duplicates are normalized during analysis.

This is the target contract. M4 implements primitive storage, injection,
copy/widening, calls/returns, explicit validity queries, predicate flow
narrowing, nullable operators and optional implemented scalar/container/class
owners. Nullable C strings, general language collections and recursive managed
by-value struct destruction remain pending.

- An exact union of one non-`none` type and `none` resolves to a reusable ASTx
  `NullableType(T)` semantic type. The parser may continue to emit the source
  `UnionType`; IRx analysis attaches the normalized type to `node.semantic`.
- A union with multiple non-`none` members is a general finite union, not an
  Arrow dense or sparse union and not a nullable scalar. Until tagged runtime
  unions land, an owning runtime use receives an actionable semantic error.
- `none` in a no-value function return remains the existing void-like return
  contract. `Array[none]` denotes Arrow's Null logical type. Context must
  distinguish both from `T | none` rather than relying on LLVM storage alone.
- A field declared as `T` is non-nullable. A field declared as `T | none` is
  nullable. This rule applies recursively to list elements, struct fields, map
  keys and values, dictionary values, and container schema parameters. Arrow map
  keys remain non-nullable as required by Arrow.

Assignment and flow rules are:

- `T` promotes implicitly to `T | none`; `none` is assignable only to `none`,
  `T | none`, or another explicitly compatible nullable target.
- A nullable value never unwraps implicitly. Passing, returning, storing, or
  casting it to `T` requires analysis-proven validity or an explicit
  `expect_valid()` operation, which produces a checked runtime failure on null.
- `is_null()` and `is_valid()` return a non-nullable Boolean. Branches using
  these predicates narrow the value to `none` or `T` on the corresponding path.
  Invalidated aliases and mutations terminate the narrowing fact.
- Scalar extraction from `Array[T | none]` or `Series[T | none]` returns
  `T | none`; extraction from a non-nullable container returns `T`.
- A nullable Boolean cannot be used directly as a branch condition. Code must
  narrow it, fill it, coalesce it, or compare through an operation with a
  documented non-nullable result.

Scalar operator rules use Arrow-compatible three-valued behavior:

- equality and ordering return `bool | none`; the result is `none` when either
  operand is null;
- `not none` is `none`;
- `false and none` is `false`, while `true and none` is `none`;
- `true or none` is `true`, while `false or none` is `none`; and
- null testing uses `is_null()` or `is_valid()`, so `value == none` is rejected
  rather than being confused with equality propagation.

Construction and schema rules are:

- Non-null values determine the inferred element type. Nulls make that type
  nullable but never determine a payload type by themselves; an all-null literal
  needs an explicit type or becomes `Array[none]` only where that type is
  explicitly allowed.
- Builders expose typed value append and null append operations. A non-nullable
  builder rejects null before invoking Arrow C++.
- Kernel result nullability is part of its registered signature and normalized
  options. Lowering does not infer it from the selected native symbol.
- Schema equality distinguishes field nullability. A runtime schema cannot be
  coerced to a non-nullable static field without a checked assertion.

The native boundary represents null independently of failure:

- A successful status may return an invalid value. A failure status never means
  null, and a null handle is never a valid null-scalar encoding.
- Nullable scalar ABI results carry an explicit validity output plus a typed
  payload. The payload and any payload owner are read only after success and
  only when valid.
- Null builder appends do not read a placeholder payload. Partial construction
  and failed appends release all initialized owners.
- Arrow validity bitmaps remain bit-packed with checked offsets and lengths.
  Imports preserve validity exactly; exports do not fabricate a non-nullable
  schema merely because the observed null count is zero.
- C Data, C Stream, IPC, and PyArrow interchange preserve both logical
  nullability and value validity. Copy versus borrow does not change either.

M2 implementation must add focused ASTx normalization, IRx assignment and
flow-narrowing, LLVM representation, native bitmap, container, and PyArrow
round-trip tests before any nullable capability row becomes complete.

#### Accepted static and runtime schema contract (M0-007)

Schemas are immutable ordered values. A field contains a UTF-8 name, canonical
logical type, nullability, recursive children and parameters, and optional
metadata. IRx analysis interns a canonical semantic descriptor; native schema
handles are opaque shared owners. LLVM never reconstructs a schema from field
names or native type IDs.

The public static forms build on existing syntax:

- `dataframe[name: T, ...]` remains the static DataFrame type.
- `recordbatch[name: T, ...]` uses the same ordered field grammar for a batch.
- `schema[name: T, ...]` names the reusable schema descriptor when a schema
  value or type parameter is required.
- `series[T]`, `array[T]`, lists, structs, maps, dictionaries, and nested
  schemas carry nullability recursively through `T | none`.
- Duplicate field names, invalid map-key nullability, illegal child counts,
  invalid decimal parameters, invalid temporal units, excessive recursion, and
  unsupported extension descriptors fail during analysis when static and at the
  native import boundary otherwise.

Static schema identity includes field order, names, logical types, parameters,
and nullability. Arbitrary application metadata is preserved but does not change
ordinary assignment compatibility. A separate exact-schema comparison also
includes metadata, dictionary ordering, extension identity, and physical
encoding. Assignment never silently reorders, adds, drops, widens, narrows, or
casts fields; code uses explicit project, rename, cast, or schema-assertion
operations.

The runtime-schema marker remains the existing ellipsis form:

- `dataframe[...]` and `recordbatch[...]` mean that fields are known only at
  runtime. The current parameter-only DataFrame restriction remains until M3
  supplies full local, call, return, and destruction ownership.
- A dynamic container still has safe untyped operations: row count, column
  count, schema inspection, slicing, IPC forwarding, and release. An operation
  needing a concrete element or result schema is rejected during analysis.
- Dot access and string subscripting remain static-schema operations. IRx must
  resolve them to a field index and type before lowering; lowering never looks
  up a name and guesses the returned type.
- Dynamic typed projection uses the proposed intrinsic operation
  `value.column<T>("name")`. It checks field existence and the complete expected
  logical type, including nullability and parameters, before returning
  `series[T]`. Mismatch is a schema error and never an unchecked cast.
- A whole-container schema assertion checks an explicit static target and, on
  success, returns the same native value with a refined static semantic type.
  Failure leaves the input valid and follows the recoverable/fatal policy from
  M0-009.
- Schema introspection returns immutable field/type descriptor values. A type
  descriptor may be compared, displayed, preserved, or supplied to a checked
  assertion, but it cannot drive an untyped LLVM load.

Construction and external-data rules are:

- Literals have static schemas derived from their declared field types. Runtime
  inference is used only by explicitly dynamic I/O and dataset APIs.
- I/O and Dataset callers may provide an expected static schema. The native
  reader validates it before yielding any batch. Without one, the result stays
  runtime-schema and requires checked projection or assertion.
- Multiple input fragments reconcile schemas only through an explicit policy.
  The default is exact logical compatibility, not best-effort promotion.
- C Data, C Stream, IPC, and PyArrow imports preserve field order, nullability,
  dictionaries, extension metadata, and nested parameters. Unsupported fields
  are rejected or preserved only where the capability matrix says preserve-only.
- Dynamic schemas and their field descriptors have checked depth, field-count,
  metadata-size, and total-allocation limits. Schema handles retain children for
  their documented lifetime and are safe across container views.

M2 and M3 tests must cover static equality versus exact equality, mismatched
order and nullability, duplicate fields, nested schemas, dynamic projection
success and mismatch, unsupported types, import limits, and ownership across
schema assertions.

#### Accepted ownership and value-semantics contract (M0-008)

Immutable Arrow-backed values use shared reference-value semantics in Arx.
Builders, stream cursors, scanners, execution plans, and mutable buffers use
unique affine semantics. These rules extend the existing IRx `ResourceOwnership`
sidecar; they are resolved in analysis and consumed by lowering rather than
reconstructed from AST shape.

The semantic ownership states are:

- **owned:** the value owns one releasable native handle token;
- **borrowed:** the value is usable only within the proven lifetime of another
  owner and must not be released;
- **static:** the value has program lifetime and is not released by ordinary
  control flow; and
- **moved:** a flow-analysis state that rejects every later read, borrow, move,
  retain, or release of that binding.

An owned handle token may contain a C++ `shared_ptr`; semantic ownership refers
to the token, not exclusive ownership of the underlying Arrow object. Retaining
an immutable value creates a second owned token. Borrowing creates no token and
records its root owner. Views are not a fifth ownership state: a public escaping
view owns a retained parent token, while a compiler-proven temporary view may
borrow its parent without escaping.

Value-category rules are:

- Array, Series, RecordBatch, DataFrame, immutable Tensor, Schema, Scalar, and
  Buffer views are immutable shared values. Binding a fresh temporary moves its
  token into the binding. Copying from a named live value retains, so both
  bindings remain valid.
- Builders, stream readers and writers, scanners, execution plans, mutable
  buffers, and mutable tensors are unique. Assignment, argument consumption, and
  return move them; implicit retain or copy is rejected.
- Function parameters borrow by default. A consuming parameter must be marked in
  semantic signature metadata before call lowering. The initial public Arx
  surface does not add manual retain/release syntax.
- Returning an owned local moves it to caller ownership. Returning an immutable
  borrowed parameter or view retains an owned result. Returning a borrowed
  unique resource is rejected.
- Slicing, projection, chunk access, schema access, and zero-copy conversion
  return an owned shared handle whenever the result may escape the expression.
  Its native object retains every parent buffer or container it needs.
- Reassigning an owned binding releases its previous initialized token only
  after the replacement operation succeeds. Self-assignment and aliasing are
  resolved before lowering.

IRx must generalize `ResourceKind` beyond its current LIST and STRING cases.
Each resource descriptor records the canonical handle kind, cleanup intrinsic,
retain capability, mutability, owner root, transfer action, and escape action.
Lowering dispatches the resolved descriptor and fails closed if metadata is
missing; it does not maintain an independent Arrow ownership table.

Cleanup rules cover all control flow:

- Every owned slot is initialized to a null handle before a fallible operation.
  It is registered for cleanup only after success has produced a valid owned
  token. Release accepts a null slot as a no-op but diagnoses invalid non-null
  tokens in debug builds.
- Lexical scope exit, return, break, continue, conditional fallthrough, loop
  backedges, and runtime-error branches release every live owner exactly once.
  No cleanup instruction is emitted after an LLVM terminator.
- Ownership merges require compatible states on all incoming fallthrough paths.
  A value moved on only one path cannot be read after the merge without a
  diagnostic.
- Aggregates recursively destroy initialized owned fields in reverse
  initialization order. Replacing a field releases its old value only after the
  new value is ready. This must land before Arrow owners are stored in classes,
  structs, closures, or collections.
- Generator and stream frames store owner state explicitly and release it on
  exhaustion, error, cancellation, or early close. Process-lifetime allocation
  is not an acceptable fallback.
- Partial builders and failed kernels release initialized child handles,
  buffers, option values, and outputs before propagating the failure.

Native handle rules are:

- Every handle kind has one retainability and one release contract in the
  unified `irx_arrow_*` ABI. Shared retain returns a new handle through a
  checked output slot; unique handles are explicitly non-retainable. Release
  consumes one token. C++ exceptions never cross the C boundary.
- A handle has a documented thread-safety class. Immutable Arrow objects may be
  shared according to Arrow's guarantees; mutable builders and execution state
  cannot be aliased across threads without an explicit synchronized wrapper.
- C Data and C Stream copy import retain or copy the producer as documented.
  Move import consumes the producer release callback and clears it exactly once.
  Exported release callbacks remain valid after the originating Arx wrapper is
  released.
- Borrowed raw buffers never outlive their parent owner. Variable-width scalar
  views and tensor views either retain an owner or copy before escape.

Gate A requires ownership tests for locals, arguments, returns, reassignment,
branches, loops, partial failure, and double-release defense. Gate E
additionally requires aggregate fields, generators, streams, cancellation,
sanitizer runs, and fault injection before declaring stable support.

#### Accepted error and status contract (M0-009)

Compile-time invalidity remains a structured lexer, parser, or IRx semantic
diagnostic. Native execution uses one Arrow-specific status contract and never
throws a C++ exception, Python exception, `errno`, or raw Arrow status across
the C ABI.

The unified ABI defines `irx_arrow_status` as a fixed-width signed value with
stable symbolic codes:

- `OK` is successful completion;
- `EOF` is successful stream exhaustion and is not an error;
- error categories cover invalid argument, null or released handle, out of
  bounds, type mismatch, schema mismatch, overflow, I/O, out of memory,
  cancellation, unsupported operation, ABI mismatch, internal invariant, and an
  unknown upstream Arrow failure; and
- new categories are append-only within an ABI major version. Native Arrow,
  operating-system, and codec-specific codes may be attached as detail but are
  not the stable language category.

ABI 1.0.0 fixes the following status values. `END_OF_STREAM` is the ABI symbol
for the EOF condition described above. The fixed-width
`irx_arrow_status_category` returned by `irx_arrow_status_get_category()` groups
codes without exposing platform `errno` or `arrow::StatusCode` values.

| Status                                 | Value | Category |
| -------------------------------------- | ----: | -------- |
| `IRX_ARROW_STATUS_OK`                  |     0 | success  |
| `IRX_ARROW_STATUS_END_OF_STREAM`       |     1 | control  |
| `IRX_ARROW_STATUS_INVALID_ARGUMENT`    |   100 | invalid  |
| `IRX_ARROW_STATUS_NULL_POINTER`        |   101 | invalid  |
| `IRX_ARROW_STATUS_INVALID_STATE`       |   102 | invalid  |
| `IRX_ARROW_STATUS_TYPE_MISMATCH`       |   103 | invalid  |
| `IRX_ARROW_STATUS_SCHEMA_MISMATCH`     |   104 | invalid  |
| `IRX_ARROW_STATUS_INDEX_OUT_OF_BOUNDS` |   105 | invalid  |
| `IRX_ARROW_STATUS_OVERFLOW`            |   106 | invalid  |
| `IRX_ARROW_STATUS_NOT_SUPPORTED`       |   107 | invalid  |
| `IRX_ARROW_STATUS_ABI_MISMATCH`        |   108 | invalid  |
| `IRX_ARROW_STATUS_OUT_OF_MEMORY`       |   200 | resource |
| `IRX_ARROW_STATUS_RESOURCE_EXHAUSTED`  |   201 | resource |
| `IRX_ARROW_STATUS_IO_ERROR`            |   300 | I/O      |
| `IRX_ARROW_STATUS_CANCELLED`           |   301 | control  |
| `IRX_ARROW_STATUS_ARROW_ERROR`         |   400 | internal |
| `IRX_ARROW_STATUS_INTERNAL`            |   401 | internal |

Unknown integer values map to the `unknown` category. The unified runtime maps
known Arrow statuses deterministically and uses `ARROW_ERROR` only when no more
specific stable mapping exists. `std::bad_alloc` maps to `OUT_OF_MEMORY`; other
caught C++ exceptions map to `INTERNAL`. M1-003 replaces the temporary
`irx_arrow_last_error` detail path with owned error records.

Every fallible function returns a status and has explicit ordinary output slots
plus an `irx_arrow_error_handle` output. The contract is:

- the caller initializes handles to null and POD outputs to zero;
- the callee publishes ordinary outputs only after complete success;
- on `EOF` and every failure, ordinary owning outputs remain null and no
  partially initialized value is observable;
- on success and `EOF`, the error output is null;
- on failure, the error output owns immutable code, operation, safe UTF-8
  message, and optional upstream detail; it is released through the same handle
  ownership system; and
- if an error handle cannot be allocated, the stable status still reports the
  failure and the error output may remain null. Callers must have a
  category-only fallback diagnostic.

Error detail is explicit rather than a borrowed global `last_error` pointer.
This makes concurrent calls, callbacks, nested failures, and async execution
safe. The compatibility layer may temporarily populate the existing
`irx_arrow_last_error` and `irx_record_batch_errmsg` accessors, but new lowering
must not depend on them. Every C++ exception is caught at the outermost C entry
point and translated; `std::bad_alloc` maps to out of memory and unknown
exceptions map to internal failure without exposing unsafe exception text.

Arx has two deliberate failure modes selected in resolved operation metadata:

1. **Recoverable:** the expression returns `result[T, data_error]`. I/O,
   Dataset, Flight, Substrait, dynamic schema assertions, and explicitly
   fallible compute APIs use this mode by default. The error value is ordinary
   typed control flow and owns any native detail until consumed or dropped.
2. **Checked fatal:** the compiler emits cleanup followed by the existing
   structured runtime-failure path. Bounds-checked indexing, `expect_valid()`,
   impossible compiler invariants, and operator allocation failures use this
   mode unless a documented recoverable variant is selected.

An operation family cannot choose its mode in lowering. IRx analysis records the
exact status policy, public error category, source call site, cleanup set, and
result type. An `expect` operation converts a recoverable result into
checked-fatal behavior; it does not disable native checks. Public APIs do not
offer an unchecked fallback merely for performance.

Null values, empty inputs, and EOF are not failures. Kernel-specific behavior
such as division, invalid UTF-8, decimal overflow, temporal ambiguity, minimum
aggregate counts, and null selection must be fixed in the registered operation
signature and options. Unknown Arrow status text never decides semantic behavior
after lowering.

Runtime diagnostics use trustworthy locations supplied by the compiler call
site. Native code supplies operation and detail but does not invent an Arx span.
Messages must not leak credentials or unbounded input data, must remain valid
UTF-8, and must survive source value cleanup. Recoverable and fatal paths both
release partial outputs, error handles, execution contexts, and all live owners
exactly once.

M1 conformance tests must cover every category, missing error-detail allocation,
exception translation, null output slots, stale and released handles, concurrent
failures, EOF, cancellation, output non-publication, and cleanup for both
language failure modes.

#### Foundation gates

- **Gate A — first public Arrow owner:** stable status/output rules, local and
  call/return ownership, deterministic cleanup, checked `i64` sizing, and the
  canonical type registry must be complete.
- **Gate B — nullable and nested containers:** nullable scalars, recursive
  schemas, variable-width buffers, field destruction, and offset/bitmap checks
  must be complete.
- **Gate C — compute:** typed intrinsic overloads, option representation,
  execution context, result ownership, and operation error propagation must be
  complete.
- **Gate D — streaming and datasets:** stream/generator close semantics, EOF,
  cancellation, backpressure, paths/URIs, and resource limits must be complete.
- **Gate E — stable release:** aggregate/class/generator ownership, matched
  native packaging, cross-platform CI, sanitizers, fault injection, and wheel
  isolation must be complete.

A milestone may implement its missing foundation in an earlier focused PR, but
it may not waive a gate or advertise partial infrastructure as end-to-end Arrow
language support.

## 5. Milestone 0 — contracts and design decisions

Do not expand syntax until these contracts are reviewed and recorded.

### Deliverables

- Add a generated Arrow capability matrix keyed to the pinned Arrow C++ release
  and link each entry to tests.
- Turn the core-foundation readiness ledger into tracked statuses with an owner,
  test target, and blocking milestone for every row. Resolve Gate A before the
  first new public owning container.
- Decide the public Arx names for Array, ChunkedArray/Series, RecordBatch,
  Table/DataFrame, streams, schemas, and datasets. Preserve existing `tensor`,
  `dataframe`, and `series` behavior unless an explicit migration is approved.
- Reserve public modules such as `stdlib.compute`, `stdlib.io`, and
  `stdlib.dataset` for the Arx-native data surface. Keep any internal `arrow/`
  organization hidden behind those facades.
- Assign every proposed public operation to compiler intrinsic, bundled builtin
  module, standard library, or optional module using the builtin-first policy
  above. Record why any core Arrow capability is not a builtin.
- Decide how Arx spells element nullability and how it relates to `none`, union
  types, nullable schema fields, and three-valued compute results.
- Decide the static-schema and runtime-schema APIs. Dynamic access must require
  a checked type assertion or return a safe dynamic value; it must never guess a
  column type during lowering.
- Specify value versus reference semantics, mutability, moves, borrows, shared
  retains, views, and return ownership for every container.
- Specify runtime errors: fatal checked-runtime diagnostics versus recoverable
  result values. The ABI must support both without unchecked output reads.
- Decide the binary distribution model described in Milestone 9.
- Define the initial stable Arrow C ABI version and compatibility policy.
- Record which Arrow modules are core, optional, or out of scope.

### Exit criteria

- Design decisions are represented in versioned documentation and executable
  test fixtures where possible.
- No proposed syntax is added only to the lexical manifest.
- Each later milestone has an agreed vertical slice and compatibility story.

## 6. Milestone 1 — one native Arrow runtime and ABI

Consolidate the current `irx_arrow_*` and `irx_rb_*` foundations before adding
more types or modules. Compatibility shims may retain old symbols temporarily,
but new functionality must use one contract.

### Milestone 1 work items

| ID     | Item                                                          | Status   | Evidence or blocker                       |
| ------ | ------------------------------------------------------------- | -------- | ----------------------------------------- |
| M1-001 | Add the packed ABI 1.0.0 constants and version query          | **DONE** | C harness and ctypes tests pass           |
| M1-002 | Define stable status categories and error codes               | **DONE** | Native header/runtime; 44 tests pass      |
| M1-003 | Unify thread-safe error-detail retrieval                      | **DONE** | Snapshot, lifetime, and thread tests pass |
| M1-004 | Define every opaque handle and its ownership operations       | **DONE** | ABI manifest; 50 Arrow tests pass         |
| M1-005 | Generate C, Python, LLVM, and symbol declarations             | **DONE** | 67-symbol generated ABI; 55 tests pass    |
| M1-006 | Add the versioned runtime-feature query                       | **DONE** | 68-symbol ABI; 56 Arrow tests pass        |
| M1-007 | Delegate legacy `irx_rb_*` symbols through compatibility      | **DONE** | 74-symbol ABI; 81 batch tests pass        |
| M1-008 | Enforce executable transitive runtime-feature dependencies    | **DONE** | 17 registry tests; 978 IRx tests pass     |
| M1-009 | Split runtime artifacts and linking by activated capability   | **DONE** | 21 feature tests; 983 IRx tests pass      |
| M1-010 | Add installed-header, layout, symbol, and version conformance | **DONE** | 12 conformance tests; wheel smoke passes  |

### Implemented error-detail snapshot contract (M1-003)

Every unified runtime entry point that can report an error begins a fresh
thread-local capture context named for that C ABI operation. A failure records
its stable `irx_arrow_status`, operation, bounded message, and optional upstream
Arrow detail. A later successful operation on the same thread clears that
capture, while activity on another thread cannot replace it.

`irx_arrow_error_snapshot()` copies the calling thread's captured failure into
an immutable `irx_arrow_error_handle`. The snapshot remains valid across later
runtime calls and can be inspected or released from another thread after normal
caller synchronization. Its accessors expose the code, operation, message, and
upstream detail; `irx_arrow_error_release()` consumes the owner. Snapshotting
when no error is present succeeds with a null output. A null output slot or
allocation failure returns a stable fallback status without destroying the
original captured failure.

`irx_arrow_last_error()` remains only as a borrowed, thread-local compatibility
view. M1-005 adds explicit owned error output slots to generated fallible
declarations and removes new lowering's dependency on that compatibility view.
M1-007 translates failures from delegated legacy RecordBatch operations back to
the historical thread-local message contract without exposing it to new unified
ABI consumers.

### Implemented opaque-handle ownership contract (M1-004)

`packages/irx/src/irx/builder/runtime/arrow/abi.json` is the checked-in source
for the initial opaque-handle vocabulary. Stable kind IDs cover errors, types,
schemas, scalars, array builders, arrays, chunked arrays, record batches,
tables, tensor builders, tensors, streams, datasets, and execution plans. Each
entry fixes its C type, shared or unique ownership class, thread-safety class,
availability milestone, and lifecycle symbol names. M1-005 generates the
language bindings and declaration tables from this manifest; M1-004 alone did
not claim that generation work was complete.

Every currently constructible unified handle begins with an internal validated
header containing its kind, ownership class, live marker, and reference count.
Immutable shared handles use atomic reference counts. Retain takes a live
borrowed source plus an output slot and publishes a second owner token only on
success. Release takes a pointer to an owner slot, consumes one token, and
clears the slot. A non-null slot containing null is an idempotent success; a
null slot pointer, wrong handle kind, or invalid state returns a stable status
without consuming a live token. Copying a raw pointer without retain never
creates an owner token.

Array and Tensor builders are unique, thread-confined handles and deliberately
have no retain operation. Their finish operations consume and clear the builder
slot only after publishing a complete result; a failed finish leaves the builder
owned by the caller. Their releases use the same consuming slot rule. The
Tensor-to-buffer bridge transfers its Tensor token through a dedicated one-shot
callback adapter so the general buffer-owner callback ABI does not weaken the
public Arrow release contract.

Opaque types for later milestones are reserved but cannot be constructed until
their declared feature lands. The implemented families are error, schema, array
builder, array, chunked array, record batch, table, tensor builder, and tensor.
Tests cover kind and ownership introspection, all implemented lifecycle
functions, null and wrong-kind inputs, double release, use after cleared release
slots, builder consumption, retained lifetime, and concurrent shared
retain/release. The earlier in-tree pointer-only lifecycle signatures were
provisional and are replaced here before ABI 1.0 conformance and distribution;
released ABI 1.x signatures remain subject to the compatibility policy below.

### Generated cross-language ABI declarations (M1-005)

`packages/irx/src/irx/builder/runtime/arrow/abi.json` is now authoritative for
the stable status values, status categories, ownership kinds, primitive type
IDs, opaque handles, function signatures, runtime-feature symbol membership,
fallibility, and ordinary result slots. `scripts/gen_arrow_abi.py` validates
that manifest and deterministically emits the installed C declaration header,
private native implementation aliases, public native wrappers, Python ctypes
signature metadata, LLVM signature metadata, and the initial 67-symbol
inventory. M1-006 appends the feature query as the 68th stable symbol. M1-007
appends six stable RecordBatch operations, producing 74 symbols.

Every ordinary fallible declaration returns `irx_arrow_status`, publishes
ordinary results through explicit output slots, and ends with an owned
`irx_arrow_error_handle` output. Generated wrappers keep outputs empty until
success, preserve the stable status when error allocation fails, rewrite error
operation names to the public ABI symbol, and snapshot immutable detail without
exposing C++ state. ABI version/category queries remain direct and the one-shot
Tensor release callback retains its required `void(void*)` callback shape.
`irx_arrow_last_error()` remains an unregistered compatibility symbol only.

The array, Tensor, and DataFrame runtime features no longer maintain handwritten
LLVM declaration maps. They instantiate generated `ExternalSymbolSpec` records,
and lowering appends an initialized owned-error slot to every fallible call.
DataFrame fatal-error lowering reads the generated owned error record rather
than the borrowed last-error view. Python tests configure ctypes directly from
the same generated signature table. Private legacy-shaped C++ implementations
are hidden inside the runtime artifact; only the generated public inventory is
exported.

`makim irx.check-arrow-abi` fails on invalid manifests or stale generated
outputs and runs in `irx.ci`. Focused tests enforce manifest validity, exact C,
Python, LLVM, feature-symbol, native-definition, and inventory parity, explicit
owned error behavior, runtime lifecycle and interoperability, and parseable LLVM
lowering.

### Versioned runtime-feature query (M1-006)

The canonical ABI manifest assigns append-only 32-bit feature IDs to `core` (1),
`array` (2), `tensor` (3), `dataframe` (4), and `record_batch` (5). Each feature
has an independent contract version packed as `0xMMMMmmpp`. The `array` contract
is now 1.1.0 for recursive schema copying; the other contracts remain 1.0.0. The
C ABI itself remains 1.0.0. The generator emits the IDs and versions into the
installed C header, Python ctypes metadata, LLVM metadata, and the native lookup
table so those surfaces cannot silently disagree.

`irx_arrow_runtime_has_feature()` accepts a stable feature ID and a required
contract version, then returns both an availability flag and the runtime's
supported version through explicit output slots. A zero required version is a
discovery query. A nonzero requirement is compatible only when the major is an
exact match and the supported packed version is greater than or equal to the
required version. A known but incompatible feature returns success with
`available = 0` and reports its supported version. An unknown future feature ID
returns success with `available = 0` and version zero, which lets a newer
consumer probe an older runtime without turning normal capability absence into a
runtime failure.

The query follows the generated fallible ABI: null output slots return the
stable null-pointer status, any writable output is reset before failure, and an
immutable owned error handle identifies the public query operation. Consumers
still check `irx_arrow_abi_version()` first; ABI compatibility and per-feature
compatibility are separate gates.

Focused manifest, C harness, and ctypes tests enforce exact cross-language ID,
version, signature, and symbol parity; discovery, exact matches, newer-minor and
new-major rejection; forward-compatible unknown IDs; explicit owned error
details; and output initialization. Package build verification confirms that the
generated lookup table ships in the wheel.

### Legacy RecordBatch compatibility layer (M1-007)

`IrxRbBatch` is now a source-compatible alias for the canonical
`irx_arrow_record_batch_handle`, not a second pointer layout. Batches produced
by the deprecated builder and IPC reader therefore carry the same validated kind
marker, shared owner token, atomic retain count, and underlying
`arrow::RecordBatch` as the stable ABI. Legacy row-count, column-count, and
release entry points delegate to the generated stable operations and translate
owned error details back to the historical integer status/message contract. The
remaining legacy value readers inspect that same canonical Arrow object; they do
not wrap, copy, or reinterpret it as a separate batch handle.

The generated ABI adds stable RecordBatch move-import, export, row and column
counts, retain, and release operations under runtime feature `record_batch`
(feature ID 5, contract 1.0.0). Arrow C Data provides the neutral boundary for
new consumers. A batch can be built through `irx_rb_*`, retained and exported
through `irx_arrow_*`, re-imported through the stable ABI, and read again by a
legacy consumer while preserving one owner-token discipline. The RecordBatch
runtime feature builds the unified runtime and compatibility translation unit as
one artifact set, and its cache fingerprint includes their private headers and
generated includes.

Every `irx_rb_*` declaration carries a compiler deprecation attribute stating
that consumers must migrate to `irx_arrow_*` before ABI major 2. Existing
consumers can temporarily define
`IRX_RECORD_BATCH_DISABLE_DEPRECATION_WARNINGS`; the implementation uses a
separate build-only suppression. No new capability may be added under the legacy
prefix. Legacy schema, builder, and IPC reader/writer objects remain
compatibility-only because the stable recursive schema, batch builder, and
stream APIs land in later milestones; only their produced or consumed batch
value overlaps a currently implemented stable handle kind.

Focused tests prove cross-ABI handle-kind and ownership inspection, retain and
release, Arrow C Data export and move-import, stable-to-legacy value access,
error translation, and compiler deprecation/suppression behavior. The combined
RecordBatch and compatibility suites pass 81 tests, the stable ABI/runtime and
compatibility selection passes 59 tests, and the complete IRx suite passes 973
tests. ABI and capability generation checks, strict IRx type checking and lint,
and the IRx package build also pass; the built wheel contains both native
translation units, the shared internal handle definition, and generated
includes.

### Executable runtime-feature dependencies (M1-008)

`RuntimeFeature.dependencies` is now a typed tuple rather than an informal
metadata entry. Construction validates the tuple and every dependency name
through IRx's runtime type-checking policy. The registry resolves the complete
transitive closure with dependencies before their dependents, deduplicates
shared subgraphs, and reports an unknown dependency with its full path. Cycles
fail with structured diagnostic `IRX-R004` and the exact closed cycle.
Resolution finishes before activation mutates module state, so either the whole
closure is activated or no new feature is.

All activation paths use this resolver, including explicit builder activation,
generated runtime-symbol requirements, feature-backed externs, and builder
initialization. Native artifact and linker-flag collection therefore sees every
activated transitive dependency while retaining the existing cross-feature
deduplication. RecordBatch's dependency on `array` has moved from `metadata` to
the executable field, and the standalone RecordBatch build fingerprint records
that dependency graph as a build input.

Registry tests cover transitive resolution, per-item runtime type validation,
unknown dependencies, cycles, atomic failure, artifacts, and linker flags. A
translate-path test proves that a RecordBatch-backed extern activates its
dependency closure, includes the required native inputs, and emits the requested
symbol. The runtime-feature suite passes 17 tests and the complete IRx suite
passes 978 tests. ABI/capability generation, strict type checking, lint, and the
IRx package build also pass. ABI generation renders feature-symbol tuples
canonically so its freshness check stays idempotent with the repository
formatter.

### Capability-specific runtime artifacts (M1-009)

The Arrow ABI is now partitioned into `core`, `array`, `tensor`, `dataframe`,
and `record_batch` native translation units. `core` owns ABI/version queries,
status and handle introspection, owned error details, and the shared
thread-local error state. Every data capability depends on `core`;
`record_batch` additionally depends on `array` while its deprecated `irx_rb_*`
adapter remains a separate compatibility input. The default runtime registry
resolves these dependencies before collecting artifacts, so an array-only
program links only the core and array objects rather than every implemented
Arrow entry point.

Each stable ABI function has exactly one capability owner in `abi.json`.
Generated public wrappers are compiled only for that owner, while linked
capability objects register their contract versions with the core during native
initialization. `irx_arrow_runtime_has_feature()` therefore reports the
capabilities present in the final link, not every capability implemented by the
source distribution. The Python ctypes configurator can likewise bind a named
capability subset without resolving intentionally absent symbols.

The standalone RecordBatch builder fingerprints and compiles its complete
`core -> array -> record_batch` closure plus the compatibility adapter. Focused
registry tests assert exact link-input sets for every current Arrow capability.
A clean array executable test inspects the resulting native symbol table and
proves that array entry points are present while tensor and dataframe entry
points are absent. A C harness also proves that the runtime query rejects an
implemented but unlinked capability.

The runtime-feature suite passes 21 tests and the complete IRx suite passes 983
tests. ABI and capability generation checks, strict IRx type checking, lint,
formatting, and the IRx package build pass. The built wheel contains all five
capability translation units and the shared Arrow feature builder.

### Installed ABI conformance gates (M1-010)

ABI 1.0.0 now has an immutable checked-in consumer baseline. The compatibility
checker requires every same-major runtime to preserve the baseline prefixes for
statuses, categories, ownership and type IDs, opaque-handle contracts, runtime
feature identities, and function declarations. It permits append-only minor
growth and planned-to-implemented availability changes, but rejects an older
minor runtime, changed stable declarations, version regression, or removal of an
implemented feature or handle.

The generated public header defines portable export and calling-convention
macros, packed-version compatibility helpers, and C11/C++20 compile-time checks
for every fixed-width ABI type. On 64-bit targets it also checks size,
alignment, and representative offsets for `irx_buffer_view` and the Arrow C Data
and C Stream structures. Strict header probes compile both the source-tree and
installed-wheel header families with warnings promoted to errors.

Native Arrow artifacts compile with hidden implementation visibility. On Linux,
a generated ELF version script exposes only stable `irx_arrow_*` declarations
and the explicitly retained transitional RecordBatch symbols. Conformance tests
link each capability closure independently, enumerate its dynamic symbols, and
require the exact manifest-owned export set. The version script and the ABI
baseline ship in the IRx wheel and participate in the standalone RecordBatch
build fingerprint.

`makim irx.check-arrow-abi-conformance` runs the baseline, header, layout, and
symbol checks as part of `irx.ci`. A dedicated Ubuntu CI matrix exercises GCC
and Clang. The focused suite passes 12 tests with both toolchains, the installed
wheel smoke compiles both header modes and executes the native interop probes,
and the complete IRx suite passes 995 tests.

### Accepted ABI v1 compatibility policy (M0-011)

The unified ABI is named `irx_arrow` and starts at **1.0.0**. All stable symbols
use the `irx_arrow_` prefix. `irx_rb_*` is a transitional compatibility prefix,
not a second ABI; shims delegate to the unified implementation and are removed
only at the next ABI major after a documented deprecation window.

`irx_arrow_abi_version()` is callable without initializing Arrow and returns a
fixed `uint32_t` packed as `0xMMMMmmpp` for 16-bit major, 8-bit minor, and 8-bit
patch components. Consumers query it before binding or calling any other stable
symbol. `irx_arrow_runtime_has_feature()` reports a stable feature ID and
feature-contract version; the canonical ABI manifest determines which feature
IDs and versions a compiler output requires.

Compatibility follows these rules:

- the ABI major must match exactly;
- a runtime minor must be greater than or equal to the consumer's required
  minor, and every required feature/version must be present;
- patch releases may fix implementation defects but cannot change declarations,
  layouts, enum values, ownership, output-slot behavior, or documented
  semantics;
- minor releases may append symbols, feature IDs, enum values, and fields at the
  end of size-versioned structs, but cannot reinterpret or remove existing
  entries; and
- any signature change, field reorder, representation change, ownership change,
  error-code reinterpretation, or removed stable behavior requires a new major.

Every public POD struct begins with `struct_size` and `abi_minor` fields and has
zero-initialized reserved space where justified. Callers set the size they know;
callees read and write only the common prefix. Stable declarations use fixed
width integers, explicit pointer-plus-`int64_t` lengths, opaque handles, and C
enums with fixed 32-bit storage. They never expose C++ types, `size_t`, platform
`long`, compiler `bool`, STL layout, Arrow class layout, exceptions, RTTI, or
allocator ownership.

The ABI specifies export visibility, C linkage, calling convention, alignment,
endianness assumptions, nullability, thread safety, ownership, output
publication, and release behavior in one installed header family. Type and error
IDs are Arx-owned append-only values rather than aliases of upstream Arrow
enums. Arrow C Data and C Stream structs retain their upstream ABI, but all Arx
functions that create, consume, or transfer them follow the versioned Arx status
and ownership contract.

Stable runtime libraries hide all non-ABI symbols. Experimental entries use a
separate `irx_arrow_experimental_` prefix and are never emitted by a stable
compiler. Internal Python module APIs, C++ classes, source paths, and build
helpers do not acquire ABI compatibility merely because they ship in the same
artifact.

The runtime manifest records ABI version, Arrow version, feature versions,
library hashes, platform, architecture, C++ runtime, and build configuration.
Compiler caches and executable dependency manifests include these values. A
provider mismatch fails before native compilation or execution, not after a
symbol happens to be missing.

ABI tests compile the installed headers as C11 and C++20, assert sizes and
offsets on each supported platform, enumerate symbols, exercise older-minor
consumers against newer runtimes, reject newer-minor consumers against older
runtimes, verify ctypes and LLVM declarations, and run from clean wheels.

### Native ABI work

- Introduce one ABI header family with:
  - a version query;
  - stable status categories and error codes;
  - thread-safe error detail retrieval;
  - opaque handles for types, schemas, scalars, arrays, chunked arrays, batches,
    tables, tensors, streams, datasets, and execution plans;
  - explicit retain, release, move, and borrow contracts; and
  - consistent output-slot rules.
- Catch all C++ exceptions at the C boundary and translate them to statuses.
- Replace duplicated primitive/RecordBatch type enums with one stable recursive
  type-descriptor API. Do not expose `arrow::Type::type` as the stable ABI.
- Represent field name, nullability, metadata, child fields, dictionary type,
  decimal precision/scale, fixed sizes, time units, and timezones.
- Generate the C declarations, Python bindings, LLVM declarations, symbol
  tables, and ABI conformance tests from one checked-in manifest.
- Make runtime feature dependencies executable rather than metadata-only.
- Split native artifacts by link need, for example `arrow_core`,
  `arrow_compute`, `arrow_acero`, `arrow_ipc`, `arrow_dataset`, `arrow_parquet`,
  and `arrow_flight`.
- Keep compatibility aliases for `array`, `tensor`, `dataframe`, and
  `record_batch` until callers migrate.

### Required tests

- ABI size, alignment, version, exported-symbol, and declaration parity tests.
- Null input, invalid handle, double release, use-after-release, failed retain,
  and untouched-output-slot tests for every handle family.
- Concurrent error reporting and retain/release tests.
- Header/library Arrow version mismatch must fail before compiling user code.

### Exit criteria

- There is one canonical type system, status model, error source, ownership
  vocabulary, and ABI manifest.
- Old and new paths cannot build incompatible handles for the same semantic
  value.

## 7. Milestone 2 — semantic ownership and cleanup

Arrow values cannot become first-class Arx values until their lifecycle is part
of semantic analysis.

### Milestone 2 work items

| ID     | Item                                                               | Status      | Evidence or blocker                                                                                                                                                                                    |
| ------ | ------------------------------------------------------------------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| M2-001 | Extend semantic resource descriptors for every Arrow handle        | **DONE**    | All current ABI handle contracts with manifest-parity tests                                                                                                                                            |
| M2-002 | Attach ownership metadata at every expression and binding site     | **DONE**    | All currently accepted managed types and sites are covered; modeled-only M3 value types fail closed                                                                                                    |
| M2-003 | Define table-column ownership and parent/child release ordering    | **DONE**    | Retained child; both release orders pass                                                                                                                                                               |
| M2-004 | Emit cleanup across every non-terminating control-flow exit        | **DONE**    | Generic slot cleanup covers current types                                                                                                                                                              |
| M2-005 | Prevent post-terminator cleanup and double release after moves     | **DONE**    | Nulling slots and terminator guards                                                                                                                                                                    |
| M2-006 | Add class-field and generator-frame ownership cleanup              | **DONE**    | Aggregate destructors and frame close implemented                                                                                                                                                      |
| M2-007 | Model retained and borrowed view owners explicitly                 | **DONE**    | Views carry parent/root and retain policy                                                                                                                                                              |
| M2-008 | Harden Python wrappers for deterministic close and use-after-close | **DONE**    | Context-manager and fail-closed tests                                                                                                                                                                  |
| M2-009 | Run ownership programs under ASan, LSan, and UBSan                 | **PARTIAL** | Native harness and all 20 generated ownership programs passed ASan/UBSan serially; LSan retry remains ptrace-blocked (exit 23)                                                                         |
| M2-010 | Add allocator-fault injection across native Arrow operations       | **PARTIAL** | Primitive builder/Tensor regressions and current-frame list/class/comprehension malloc/realloc accounting pass; move import, legacy IPC and remaining native operations still need full failure sweeps |
| M2-011 | Add bounded-memory loops and release-order property tests          | **DONE**    | 256 native lifecycle iterations return Arrow-pool bytes to baseline; a generated generator loop has zero remaining malloc/free owners; both release orders pass                                        |
| M2-012 | Guard aggregate allocation and isolate resume-state cleanup        | **DONE**    | 22 aggregate/generator tests; real malloc-failure class/frame executables report errors; resumed owning locals verify and execute                                                                      |
| M2-013 | Close remaining aggregate storage-class and cycle gaps             | **PARTIAL** | Owned and borrowed string fields now clone/move safely with destructor cleanup; cyclic class graphs and static-managed storage still need supported lifecycle policies                                 |

### Additional verified M2 slices

| ID     | Item                                                              | Status   | Evidence                                                                                                  |
| ------ | ----------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------- |
| M2-014 | Preserve builder contents across real allocation failures         | **DONE** | 53 allocation tests, including all 11 primitive builders and standalone C++ finish sweeps                 |
| M2-015 | Clean current-function owners on assertion and arithmetic failure | **DONE** | Two malloc/free-accounted fatal executables; report-before-cleanup keeps borrowed IRx message bytes valid |

### Semantic resource descriptor foundation (M2-001)

`ResourceKind` now covers all 16 opaque handle families in the canonical Arrow
ABI: error, type, schema, scalar, array builder, array, chunked array,
RecordBatch, table, tensor builder, tensor, stream, dataset, execution plan,
field, and C Data carrier. Manifest-parity tests fail if a handle is added,
removed, or renamed without a matching semantic resource contract.

Every `ResourceOwnership` sidecar now carries the resource's sharing class,
mutability, cleanup intrinsic, optional retain intrinsic, immediate owner, root
owner, source owner, transfer action, and escape action. `MOVED` is an explicit
fail-closed ownership state. Shared Arrow values are immutable and retainable;
builders, streams, and execution plans are mutable unique resources with no
retain operation. Existing list and string ownership helpers also construct the
complete descriptor, so lowering can migrate to one resource contract rather
than maintaining per-type lifecycle tables.

The exported `arrow_resource_ownership()` factory is the single semantic entry
point for Arrow handle metadata. It rejects non-Arrow resource kinds, derives a
root owner when possible, and preserves that root and the static lifecycle
contract across validated transfers. Focused tests cover manifest parity, shared
and affine descriptors, owner roots, transfers, managed type mapping, runtime
type validation, invalid resource families, and the moved state.

### Current ownership and cleanup implementation (M2-002 through M2-011)

All currently supported IRx managed values use one semantic resource classifier.
Generator ownership here is an ASTx/IRx capability: Arx source does not yet
parse user-defined `yield`, and its bundled `range` currently returns a list.
DataFrame/Table, Series/ChunkedArray, Tensor-backed buffer views, ordinary
buffer views, lists, strings, class instances, and generator frames carry typed
ownership through literals, identifiers, parameters, calls, declarations,
assignments, returns, fields, loop values, projections, yields, and explicit
releases. Shared copies lower through the retain ABI; fresh values move into
their destination. New M3-M7 types and operations must enter through the same
classifier and site-specific ownership helpers rather than reopening M2.

Lowering consumes semantic cleanup and retain intrinsic names through the
runtime-feature registry. Owned locals and temporaries use entry-initialized
slots, cleanup runs in reverse order on fallthrough, return, loop transfer, and
runtime failure, and successful moves or releases null the source slot. Builder,
append, finish, borrow, and projection statuses are checked before outputs are
read. Array, DataFrame, and tensor partial construction registers each
successful intermediate owner immediately.

Table-column projection is a retained child handle, so table and column can be
released in either order. Tensor slices retain their buffer owner; raw
descriptor views remain explicitly borrowed. Supported class objects have a
common descriptor/dispatch/destructor/reference-count header, reverse-order
managed field destruction, and shared retain/release helpers. Generator values
carry a frame, resume function, and destroy function; owned frame slots are
initialized to empty values and released both on exhaustion and early close.
Python RecordBatch schema, builder, batch, writer, and reader wrappers support
deterministic context management and reject use after release, finish, or close.

`irx.check-arrow-ownership-sanitizers` builds a 256-iteration C++ lifecycle
harness that checks live Arrow-pool bytes return to baseline after each
iteration with ASan, UBSan, and LSan. It also runs four ASan-instrumented
generated programs covering class owners and generator exhaustion, early close,
and resumed failure, with UBSan on their registered native artifacts. The Clang
ABI CI job runs this task; that remote result has not been observed here. ASan
and native UBSan pass locally; this sandbox runs under ptrace, so local LSan
execution is blocked while the unmodified CI command retains leak detection.

Operation-entry failpoints alone are not proof of post-mutation recovery. M2-014
adds test-only Arrow pool failures for partial allocation/reallocation, plus
standalone C++ allocation sweeps through Array/Tensor finish. These verify
OUT_OF_MEMORY, null outputs, retry safety, preserved values/nulls, and release.
Primitive Array finish snapshots buffers before consuming the builder; Tensor
finish shares its existing buffer without moving from it early. The 53 new
regressions cover all 11 executable primitive builder types, not every modeled
Arrow type or native operation. General compute and unified stream/file paths
remain future work. C Data move import and legacy RecordBatch IPC/stream
operations still need allocator-failure contracts and coverage; future M6-M7
paths require the same guarantees.

M2-015 also cleans current-function owners on assertion and scalar integer
arithmetic failure. Assertion reporting precedes cleanup to keep borrowed
message bytes live. This is not cross-function fatal stack unwinding.

The 2026-09-16 audit reopens M2: operation-entry failpoints are not proof of
allocator failure atomicity, unmeasured loops do not establish a memory bound,
and configured CI is not evidence of a successful LSan run. M2-011 now adds
measured Arrow-pool and generated-program allocation accounting. Later
milestones may add resource kinds, views, or fallible operations only with
ownership metadata, deterministic cleanup, sanitizer coverage, and
allocation-failure tests in the same vertical slice.

### IRx work

- Extend `ResourceKind` and `ResourceOwnership` for every Arrow handle family.
- Attach owner/borrow/shared/view/move/escape metadata to literals,
  declarations, assignments, calls, returns, fields, loop values, and
  temporaries.
- Define whether selecting a table column returns an owned shared handle or a
  borrow. Test parent/child release in both orders.
- Emit cleanup on block fallthrough, return, `break`, `continue`, replacement,
  runtime failure, and partial construction failure.
- Prevent cleanup after terminators and prevent double release after moves.
- Add class-field and generator-frame cleanup before permitting Arrow owners in
  either location.
- Model view owners explicitly for sliced arrays, tensors, buffers, batches, and
  streamed data.
- Make Python wrappers deterministic context managers and reject use after
  close/release/finish.

### Verification

- Run ownership programs under ASan, LSan, and UBSan.
- Add allocator-fault injection for create, reserve, append, finish, import,
  compute, stream, and file operations.
- Add bounded-memory loops and release-order property tests.

### Exit criteria

- No Arrow owner is process-lifetime by accident.
- Every successful handle-producing call immediately acquires one documented
  cleanup obligation.
- Every failed call leaves outputs unread and previously acquired owners valid
  or released according to the contract.

## 8. Milestone 3 — complete Arrow type and schema model

### Milestone 3 work items

| ID     | Item                                                                                         | Status      | Evidence or blocker                                                                                                                                                           |
| ------ | -------------------------------------------------------------------------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M3-001 | Reusable recursive logical types, fields, schemas and container types in ASTx                | **DONE**    | 45 logical kinds, immutable recursive descriptors, runtime collection checks, ASTx tests                                                                                      |
| M3-002 | Canonical schema validation and lossless conversion rules in IRx                             | **DONE**    | Field paths, metadata identity, parameter validation and conversion-domain tests                                                                                              |
| M3-003 | Central scalar/storage mapping and physical type resolution                                  | **DONE**    | All 45 families resolve to immutable C Data sidecars consumed by verified native LLVM lowering; no PyArrow serialization in compilation                                       |
| M3-004 | Descriptor/schema, C Data and IPC metadata round trips                                       | **DONE**    | 45 families round-trip through PyArrow C Data, IPC schemas and native recursive field handles; synthetic-child restrictions documented                                        |
| M3-005 | Builtin source syntax and typed descriptor construction/inspection/conversion classification | **DONE**    | Arx literals and nine closed queries, ASTx nodes, IRx validation and native execution; conversion_kind classifies literals, not value casts                                   |
| M3-006 | Native descriptor ABI, ownership, failure paths and milestone gate                           | **PARTIAL** | ABI and array contract 1.6 implemented, including extension storage and owned C Data; import/owner regressions pass; combined Gate B and full leak/fault coverage remain open |

### Implemented descriptor execution (2026-09-18)

See `docs/arrow-type-schemas.md` and `examples/schema_descriptors.x` for the
exact source API. All 45 logical families have builtin descriptor syntax,
canonical semantic validation, pre-resolved physical sidecars, dedicated opaque
native owners and C Data round-trip coverage. Inspection, checked projection,
exact equality, call/return sharing and replacement execute natively. Remaining
modeled-only columnar value types and descriptor container wrappers fail in
analysis rather than reaching unsupported lowering.

There is no Arrow namespace or Python execution fallback. `conversion_kind`
classifies two literal type or schema descriptors at compile time; actual casts
of values remain M4/M6 work. Managed class fields and suspended descriptor
locals use the existing ownership machinery. Unmanaged structs and yielding or
wrapping descriptors remain rejected. Primitive nullable scalar storage first
landed in M4-001; later M4 continuations add variable-width and recursive nested
value paths. The 2026-09-21 closure adds extension value execution and checked
external-buffer/bitmap construction. Gate B still requires complete nullable
aggregate semantics and the remaining ownership/fault verification; its
completion must not be inferred from descriptor support.

### ASTx

- Add reusable Array, ChunkedArray, RecordBatch, Table, Schema, Field, Scalar,
  and stream types where the concepts are language-agnostic.
- Model recursive fields, nullability, parameters, and metadata without
  embedding Arrow C++ objects.
- Add focused nodes for construction, inspection, projection, and conversion. Do
  not encode kernels as untyped strings on generic call nodes.
- Export all public nodes and keep runtime type checking and Douki docs green.

### IRx analysis

- Canonicalize structural schemas and define equality, compatibility, and
  metadata-preservation rules.
- Resolve Arrow scalar/storage mappings in one module shared by arrays,
  DataFrames, RecordBatches, tensors, and compute.
- Validate nested nullability, duplicate names, decimal limits, time units,
  timezones, dictionary indices, union codes, fixed sizes, and extension
  metadata.
- Define safe implicit conversions and require explicit casts for narrowing,
  lossy temporal changes, dictionary changes, and metadata loss.
- Attach a resolved physical representation and required runtime features to
  semantic sidecars.

### Arx frontend

- Update `syntax.json` first for each approved type or operation.
- Implement type parsing, literals/builders, member access, and diagnostics in
  concern-specific parser modules.
- Reuse ASTx nodes directly; do not create Arx-owned AST classes.
- Keep runtime-schema values restricted to safe operations until checked dynamic
  access is implemented.

### Exit criteria

- Every required logical type round-trips through type descriptor, schema, Arrow
  C Data, IPC, and PyArrow metadata tests.
- Unsupported or incompatible types fail during parsing or semantic analysis,
  never as a generic lowering exception.

## 9. Milestone 4 — first-class containers in Arx

Deliver vertical slices rather than implementing all builders before any
language path works.

### Milestone 4 work items

| ID     | Item                                                               | Status      | Evidence or blocker                                                                                                                                                                                                                                                                                       |
| ------ | ------------------------------------------------------------------ | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M4-001 | Primitive nullable scalar storage and explicit validity operations | **DONE**    | Normalized nullable types, independent validity, local/call/return conversion, checked unwrap, native execution and sanitizer cleanup coverage                                                                                                                                                            |
| M4-002 | Nullable operators, predicate flow narrowing and managed payloads  | **PARTIAL** | Operators, compound proofs, numeric casts, optional scalar/class/shared/unique owners and instance fields implemented; nullable strings and by-value list/tensor owners execute with explicit retain/drop; nested nullable elements, recursive managed aggregates and by-value struct destruction pending |
| M4-003 | First-class primitive arrays and nullable scalar extraction        | **DONE**    | Primitive/logical arrays, reusable builders, half-floats, chunks and copying from rank-one numeric tensor/buffer views implemented; checked source C Data owners and packed-buffer/bitmap constructors verified (C2)                                                                                      |
| M4-004 | Variable-width and nested containers, batches and tables           | **DONE**    | Logical scalar/array/batch/table construction, nested child access, deep copies and noncontiguous row selection implemented; registered/opaque extension storage codecs and explicit legacy DataFrame/Series adapters verified (C1/C3)                                                                    |

### Arrays and scalars

- Add typed construction from literals, builders, buffers, and C Data.
- Add length, null count, validity, scalar access, slicing, concatenation,
  rechunking, equality, and explicit copy operations.
- Support offset arrays and nonzero validity offsets everywhere.
- Preserve Boolean bit packing and variable-width offset buffers instead of
  projecting them as byte-addressable fixed-width views.
- Return nullable scalar values safely; never read a null slot as a value.

### RecordBatches, Tables, DataFrames, and Series

- Construct all required logical types, including recursive nested types.
- Support static-schema projection and checked runtime-schema projection.
- Add row/column selection, rename, add/replace/remove column, slice, combine
  chunks, batch/table conversion, and schema metadata access.
- Expand Arx DataFrames from numeric/Boolean literals to nullable, string,
  binary, temporal, decimal, dictionary, and nested columns.
- Define iteration explicitly: batches, rows, columns, or scalars must not be
  selected implicitly by backend convenience.
- Make DataFrame and Table naming an intentional language abstraction rather
  than two aliases with drifting behavior.

### Required edge cases

- Empty schemas, zero rows, zero-length buffers, all-null data, no-null data,
  sliced data, multiple chunks, duplicate names, maximum offsets, overflow,
  malformed external C Data, and parent release before/after child views.

### Exit criteria

- Pure Arx programs can construct, inspect, pass, return, and transform all core
  Arrow containers and types.
- Translate tests prove required runtime features and symbols are activated;
  build/run tests prove linked execution.

## 10. Milestone 5 — tensors and multidimensional interchange

- Add dynamic indexing for runtime-shaped tensors with rank and bounds checks.
- Define return ownership and argument borrowing for runtime-shaped tensors.
- Add partial and symbolic shape constraints only after runtime validation is
  available.
- Support safe reshape, transpose, slice/view, contiguity queries, and explicit
  copies.
- Decide writable tensor semantics. Default imported Arrow storage to readonly;
  require unique mutable storage or copy-on-write before stores.
- Add supported fixed-width Boolean, decimal, temporal, and complex mappings
  only where Arrow Tensor and Arx scalar semantics agree.
- Add SparseCOOTensor, SparseCSRMatrix, SparseCSCMatrix, and SparseCSFTensor as
  optional typed containers.
- Add DLPack and Arrow C Device Data interchange as optional runtime features;
  CPU support remains the required baseline.

Exit requires shape, stride, offset, zero-extent, overflow, non-contiguous,
readonly, aliasing, device, and ownership tests.

## 11. Milestone 6 — Arrow Compute primitives

Arrow kernels remain focused runtime primitives. IRx must not become a generic
query engine and lowering must not dispatch arbitrary user-provided kernel
names.

### Kernel registry

- Build a versioned allowlist from Arrow Compute function metadata.
- Map each kernel to typed input shapes, output type rules, option structures,
  null behavior, required libraries, and deterministic/error behavior.
- Resolve kernels and options during semantic analysis and attach a
  `ResolvedArrowCompute` sidecar.
- Lower only the resolved kernel identifier and normalized options.
- Represent Datum-like results behind typed opaque handles; never expose the C++
  `arrow::Datum` layout.

### Delivery order

1. Cast, fill-null, validity, and selection operations.
2. Element-wise arithmetic, comparison, Boolean, string, and temporal kernels.
3. Filter, take, drop-null, sort, partition, unique, and dictionary kernels.
4. Scalar and hash aggregates.
5. Table operations: group-by, joins, projection, and ordering through focused
   Acero wrappers.

### Exit criteria

- Supported kernels have semantic signature tests, null-policy tests, direct
  native tests, LLVM declaration tests, and Arx build/run tests.
- Unsupported kernels and invalid options produce actionable semantic
  diagnostics.
- Thread count, memory pool, cancellation, and determinism are explicit
  execution-context settings.

## 12. Milestone 7 — streams, IPC, and file formats

- Make Arrow C Stream the common in-process batch-stream boundary.
- Support streaming producers and consumers without materializing all batches.
- Unify current IPC file/buffer readers and writers with the general stream
  lifecycle.
- Add IPC stream and file modes, compression options, schema evolution rules,
  and size/resource limits.
- Add feature-gated CSV and JSON readers/writers with typed option objects.
- Add Parquet read/write, projection, row-group selection, predicate pushdown,
  statistics, compression, and metadata while preserving nullable/nested types.
- Ensure filesystem paths, buffers, and streams have distinct APIs and
  ownership.
- Decide whether I/O errors are recoverable values or structured fatal runtime
  diagnostics before exposing syntax.

Exit requires truncated/corrupt input, empty input, schema mismatch, oversized
metadata, cancellation, partial write, close failure, Unicode path, and PyArrow
interoperability tests.

## 13. Milestone 8 — Dataset, filesystem, and Acero execution

- Add local filesystem support first, followed by explicitly optional S3, GCS,
  Azure, and HDFS providers when distributable dependencies exist.
- Model Dataset, Fragment, Scanner, and batch-stream results as opaque owned
  resources.
- Resolve projection and predicate expressions semantically and lower them to a
  constrained Arrow expression ABI.
- Add scan options, partition discovery, partition expressions, batch sizing,
  readahead, threading, cancellation, and memory limits.
- Use Acero for focused execution plans such as scan, filter, project,
  aggregate, order, and join. Do not add a separate IRx query optimizer.
- Keep Flight and Substrait optional:
  - Flight requires authentication, TLS, timeout, cancellation, and streaming
    ownership contracts.
  - Substrait consumes or emits plans only after all referenced operations map
    to supported typed primitives.

Exit requires deterministic local-dataset integration tests and isolated
optional-provider tests that do not make the core suite network-dependent.

## 14. Milestone 9 — packaging and native deployment

This work begins with Milestone 1 and gates stable release.

### Accepted distribution decision (M0-010)

The supported production strategy is a dedicated `arx-arrowcpp-runtime`
distribution containing a mutually tested Arrow C++ build, required headers, the
unified Arx C ABI runtime, feature manifest, licenses, and notices. It ships
ABI-independent Python platform wheels, so the same native payload serves Python
3.10-3.14 where wheel tags permit. Its release identity records the Arrow
version, Arx ABI major/minor, platform, architecture, C++ runtime, build flags,
enabled components, and packaging revision.

The core runtime wheel contains Arrow core, Compute, IPC, CSV, JSON, Dataset,
Acero, local filesystem, supported compression libraries, and the Arx ABI
adapter as independently discoverable native libraries. Heavy or
environment-specific dependencies use exact-version companion wheels:

- `arx-arrowcpp-flight-runtime` for Flight and Flight SQL;
- `arx-arrowcpp-cloud-runtime` for supported cloud filesystem providers; and
- `arx-arrowcpp-device-runtime` for supported device backends.

Parquet is part of the core data distribution because it is a required M6
format, but remains an independently activated runtime feature so programs that
do not use it do not link or bundle its library.

IRx depends on the matching core runtime package for production native builds.
PyArrow becomes an optional ArxPy interoperability dependency and a temporary
test/bootstrap provider only; new production lowering must not locate native
libraries through `pyarrow.get_library_dirs()`. `arx-arrowcpp-sources` remains
an explicit developer/source-build input rather than the ordinary installation
path.

System or Conda Arrow is an opt-in developer override, never an implicit search
fallback. It must pass the same version, component, compiler-runtime, symbol,
and ABI-manifest checks before use. An advanced source build is also explicit,
content-addressed, and outside normal `pip install`; failure to locate the
accepted runtime produces an actionable diagnostic rather than silently trying a
different provider.

For `arx run`, libraries are loaded from the installed runtime package through
its manifest. For distributable `arx build` output, only activated libraries and
their licenses are copied beside the executable and located through
`$ORIGIN`-relative RPATH on Linux, loader-relative install names on macOS, and
application-local DLL discovery on Windows. Builds record and verify hashes;
they do not depend on the originating Python environment remaining installed.

The runtime package and companions are released and compatibility-tested with
the Arx package set. The lockfile pins exact compatible artifact revisions; it
never accepts an unbounded Arrow major range. Linux, macOS, and Windows wheel
jobs build in reproducible isolated environments and test the artifacts from a
clean consumer environment.

Compiling the full bundled Arrow source tree during ordinary `pip install` is
not an acceptable default.

### Implementation requirements

- Verify header, compile-time, link-time, and runtime Arrow versions match.
- Discover and link only libraries required by activated features.
- Handle Linux RPATH, macOS install names, and Windows DLL discovery.
- Define static/shared linkage, C++ standard library, compiler, and minimum OS
  compatibility.
- Package licenses, notices, native headers, ABI manifests, and required source
  assets.
- Make native caching content-addressed by ABI, Arrow version, compiler,
  platform, flags, and source digest.
- Test installed wheels in a clean environment without relying on the source
  tree or root Poetry environment.
- Add active Linux, macOS, and Windows native matrices for supported Python
  3.10–3.14 versions. Include Clang/GCC/MSVC where supported.
- Keep non-Arrow programs free from Arrow linker inputs.

### Exit criteria

- A released Arx wheel can compile and run an Arrow-backed `.x` program from a
  clean environment on every supported platform.
- The resulting executable locates its Arrow libraries using documented,
  reproducible rules.

## 15. Milestone 10 — hardening and stability

- Fuzz Arrow C Data, C Stream, IPC, schemas, nested builders, compute options,
  and malformed file inputs.
- Run ASan, LSan, UBSan, and TSan native suites.
- Add OOM and I/O fault injection through custom Arrow memory pools and streams.
- Add benchmarks for construction, scans, filtering, aggregation, joins, IPC,
  Parquet, and interchange. Track allocations, copies, peak memory, throughput,
  binary size, and compile/link time.
- Make promised zero-copy paths assert pointer identity and lifetime behavior.
- Add resource limits for rows, bytes, nesting, fields, batches, and metadata.
- Audit all C++ entrypoints for exception containment and all Python/LLVM
  declarations for ABI parity.
- Publish ABI stability, Arrow upgrade, deprecation, and migration policies.
- Update `README.md`, `docs/apache-arrow.md`, `docs/arx/collections.md`, the
  capability matrix, language specification, examples, and package READMEs.

Stable status requires two consecutive supported Arrow upgrades through the
documented upgrade process without bypassing conformance tests.

## 16. Cross-package change map

| Area                          | Expected locations                                                                  |
| ----------------------------- | ----------------------------------------------------------------------------------- |
| Lexical/surface syntax        | `packages/arx/src/arx/lexer/syntax.json`, lexer tokens, parser mixins               |
| Arx construction and bindings | `packages/arx/src/arx/dataframe.py`, `tensor.py`, new concern-specific adapters     |
| Reusable nodes/types          | `packages/astx/src/astx/`, exports, ASTx tests and docs                             |
| Meaning and validity          | `packages/irx/src/irx/analysis/`, typed resolved sidecars                           |
| LLVM lowering                 | `packages/irx/src/irx/builder/lowering/`                                            |
| Native ABI/runtime            | `packages/irx/src/irx/builder/runtime/arrow/native/`                                |
| Feature registry/linking      | `packages/irx/src/irx/builder/runtime/`, `arrowcpp.py`                              |
| Python interoperability       | `packages/irx/src/irx/record_batch.py` and future unified Arrow API                 |
| Packaging                     | package `pyproject.toml` files, root pins, lockfile, build scripts, release wiring  |
| Tests                         | ASTx, IRx, Arx parser, translate, native, compiled-language, and wheel-smoke suites |
| Documentation                 | `docs/apache-arrow.md`, `docs/arx/`, `docs/irx/`, examples and capability matrices  |

Public changes must update all affected rows. A type is not supported merely
because it exists in ASTx or in the C++ runtime.

## 17. Required verification ladder

Every vertical slice should pass the smallest relevant checks first and then the
affected cross-package gates.

1. **Native unit tests:** direct C ABI behavior, ownership, and status handling.
2. **Interop tests:** Arrow C Data/C Stream, IPC, PyArrow, and independent
   protocol consumers where practical.
3. **ASTx tests:** construction, runtime type checks, exports, and structured
   representation.
4. **IRx semantic tests:** positive and negative type/schema/ownership/kernel
   resolution.
5. **IRx translate tests:** active features, declarations, result-stack
   discipline, and LLVM parsing.
6. **Native build/run tests:** linked execution and release behavior.
7. **Arx lexer/parser tests:** syntax manifest, source locations, and earliest
   responsible diagnostics.
8. **Arx compiled tests:** real `.x` programs including empty, null, error,
   overflow, nested, and streaming cases.
9. **Wheel tests:** audit native assets and run from isolated installed wheels.
10. **Quality gates:** Ruff, mypy, Douki, sanitizers, and supported platform and
    Python matrices.

Representative commands, adjusted to the touched slice:

```bash
pytest -q packages/irx/tests/test_arrow_runtime.py
pytest -q packages/irx/tests/test_record_batch.py
pytest -q packages/irx/tests/test_tensor.py
pytest -q packages/irx/tests/test_dataframe.py
pytest -q packages/arx/tests/python/test_codegen_ast_output.py
pytest -q packages/arx/tests/python/test_codegen_file_object.py
makim arx.check-syntax
makim arx.test-compiled
makim all.wheel-smoke
makim all.typecheck
makim all.lint
makim docs.build
```

Add focused Makim tasks for Arrow ABI, sanitizer, interoperability, and
benchmark suites rather than overloading the ordinary unit-test target.

## 18. Pull-request sequencing

Keep changes reviewable and independently testable. A recommended sequence is:

1. Capability matrix, accepted design records, and foundation readiness ledger.
2. Core checked `i64` size/offset/index rules and operation failure contract.
3. ABI manifest, status model, and generated declarations.
4. Nullable scalar semantics and recursive logical type/schema model.
5. Consolidated native type/schema handles and compatibility shims.
6. General native-resource ownership, cleanup, and aggregate field destruction.
7. Binary/string, decimal, and temporal scalar foundations in focused groups.
8. One complete nullable Array vertical slice and Gate A/B review.
9. Remaining logical type families in small groups.
10. RecordBatch/Table/DataFrame/Series vertical slices.
11. Runtime-shaped and writable Tensor decisions and implementation.
12. Typed intrinsic registry followed by compute kernel groups.
13. Stream/generator lifecycle, cancellation, C Stream, and IPC unification.
14. CSV/JSON, then Parquet.
15. Dataset/filesystem, then Acero.
16. Optional Flight/Substrait/device features.
17. Cross-platform packaging, sanitizer, performance, and stability gates.

Packaging and clean-wheel checks evolve with every ABI/runtime PR even though
their final stabilization is listed last. A feature is not complete if its
installed artifact path is deferred to a later cleanup PR.

Do not combine a new syntax family, ABI redesign, and broad runtime refactor in
one PR. Temporary shims must have removal criteria and tests.

## 19. Risks and mitigations

| Risk                                    | Mitigation                                                       |
| --------------------------------------- | ---------------------------------------------------------------- |
| Arrow C++ ABI/library mismatch          | Exact compatibility checks and one artifact strategy             |
| Dangling views or double release        | Semantic ownership plus sanitizer and release-order tests        |
| Null semantics diverge by container     | One nullable scalar/schema model and kernel null-policy metadata |
| Manual symbol/type tables drift         | Generate all bindings from one ABI manifest                      |
| Optional modules bloat every executable | Transitive feature gating and per-module linker inputs           |
| Dynamic schemas weaken static safety    | Checked projection/reflection APIs; no lowering guesses          |
| Compute becomes an untyped query API    | Typed allowlist and resolved semantic sidecars                   |
| File/network input exhausts resources   | Explicit byte/row/nesting limits and cancellation                |
| Wheels work only in the monorepo        | Clean installed-wheel build/run tests on every platform          |
| Upstream Arrow changes break Arx        | Versioned capability matrix and upgrade conformance suite        |

## 20. Final definition of done

Native Arrow C++ support is complete for a declared Arrow release only when:

- all core-foundation ledger rows and Gates A through E are complete;
- every supported logical type and module is listed in the capability matrix;
- approved Arx syntax, ASTx nodes, IRx semantics, LLVM lowering, native ABI,
  runtime feature registration, exports, tests, examples, and docs agree;
- all Arrow resource create/borrow/share/move/view/release paths are enforced;
- C Data, C Stream, IPC, and PyArrow round trips pass for all supported types;
- compute, streaming, and file operations execute without Python in the runtime
  path;
- every supported capability has a reviewed builtin, builtin-module,
  standard-library, or optional-module placement, with compiler intrinsics used
  wherever static safety or native ownership requires them;
- generated LLVM validates and linked executables pass native tests;
- clean wheels work on every supported OS/Python/toolchain combination;
- sanitizer, fault-injection, fuzz, and bounded-memory suites pass;
- unsupported Arrow input fails at the earliest responsible boundary with a
  structured diagnostic; and
- remaining optional or out-of-scope Arrow modules are explicitly documented,
  not silently omitted.

## 21. Implementation decisions and alternatives

### 2026-09-17 — M2 native failure safety (M2-009/010/014/015)

- **Assumption:** failed Array/Tensor finish must preserve logical builder
  contents, not merely leave a non-null handle. Callers may retry or release.
  **Decision:** prepare all fallible results before consuming the owner.
  **Alternatives:** poison/consume the builder on failure (simpler, but changes
  the accepted ABI contract); custom transactional buffers (potentially
  zero-copy, but a larger maintenance burden against the pinned Arrow API).
- **Assumption:** native failure tests need both Arrow buffer allocator failures
  and C++ object allocation failures. Operation-entry failpoints alone are not
  evidence of post-mutation safety. **Decision:** use a test-build-only failing
  Arrow pool and a bounded standalone C++ allocation-failure sweep; production
  builds must ignore test controls. **Alternative:** interpose the entire
  process allocator, which is less deterministic with Python and Arrow caches.
- **Assumption:** generated LLVM ownership code must be exercised, not just the
  C ABI harness. **Decision:** extend the sanitizer task with generated class
  and suspended-generator programs. **Alternative:** rely solely on native
  handle tests, which misses compiler-emitted lifetime bugs.

#### Implemented choices and best alternatives

1. **Primitive Array finish: snapshot, then consume.** Copy value/validity
   buffers once at finish and retain original builder contents until the
   complete Array and handle exist. A failing resize also restores the logical
   capacity marker, so retry cannot skip validity allocation. Actual allocation
   tests exposed a segmentation fault in the previous retry path; the corrected
   regression passes for all 11 current builder families. Capacity can grow on a
   failed call; logical values, nulls and length must not change.
   - **Trade-off:** O(n) copying and transient extra buffer memory at finish,
     not on each append. This applies to the unified primitive Array builder; it
     is not a zero-copy finish claim or a retrofit of legacy RecordBatch.
   - **Best performance alternative:** a two-phase buffer-freeze/publication
     API, ideally upstream in Arrow. It would avoid copying but needs failure
     atomicity tests before replacing this implementation.
   - **Dependency assumption:** the pinned Arrow C++ protected builder API
     remains available. Keep the adapter private; revalidate on Arrow upgrades.
2. **Tensor finish: shared Arrow buffer, no destructive move.** Allocate with
   the Arrow pool, retain the builder's buffer during Tensor construction, then
   consume the builder on success. Value-buffer finalization stays zero-copy.
   - **Alternative:** copy the vector before finish (simpler but O(n)); moving
     the original vector early was rejected because later allocation can fail.
3. **Two independent allocator probes.** A compile-time test-only pool fails the
   selected zero-based Allocate/Reallocate call in each ABI operation. A
   standalone executable sweeps C++ `new` failures through finish until an
   uninjected success, with an explicit upper bound. The process is separate
   from Python, and production artifacts ignore the pool environment control.
   - **Limitation:** these tests are representative operation sweeps, not a
     proof over every allocator, operation, schedule or live process byte.
   - **Alternative:** a public allocator-injection ABI would support embedders
     but should not be added solely to expose testing machinery.
4. **Fatal-path ownership: report, clean, terminate.** Assertions report before
   freeing current-function owners so a borrowed diagnostic string remains
   valid; integer division uses the common cleanup-aware guard. Existing
   assertion record format and exit status remain unchanged, and the legacy
   combined native assertion helper remains available.
   - **Scope assumption:** this is current-function/frame cleanup, not native
     stack unwinding. Arx source still accepts literal assertion messages only;
     dynamic message ownership tests exercise the lower-level ASTx/IRx API.
   - **Best general alternative:** explicit error propagation with cleanup in
     each caller; this requires a language-wide calling convention decision.
     Cross-function fatal unwinding, static managed storage, owned string
     fields, and cyclic class graphs therefore remain open M2 work.
5. **Sanitizer evidence must be real.** Generated functions receive LLVM's
   `sanitize_address` attribute, are compiled with Clang, and the resulting
   object must contain ASan instrumentation. Registered native artifacts use
   ASan/UBSan. Sanitizer failures use distinct exit codes, so an expected
   language failure cannot accidentally count as a passing sanitizer run.
   - **Limitations:** UBSan is not a frontend pass on pre-existing LLVM IR;
     Arrow's installed shared libraries are not rebuilt with sanitizers here.
     Local ptrace prevents LSan; disabling leak detection is an explicit local
     option, never the default or the CI command.
   - **Best stronger alternative:** untraced CI with an instrumented Arrow build
     and a broader generated-program corpus, followed by clean-wheel runs. Keep
     M2-009 partial until the required leak evidence is observed.

#### Verification and remaining work

- `pytest -q packages/irx/tests/test_arrow_allocation_failures.py`: 53 passed.
- Assertion/binary/generator tests: 39 passed; two additional fatal-path
  malloc/free-accounting tests passed.
- `python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`:
  native harness and generated class ownership, generator exhaustion, early
  close, and resumed assertion-failure programs passed.
- `pytest -q packages/irx/tests packages/astx/tests`: 1,813 passed on Python
  3.14.3 (includes the allocation and fatal-path regressions above).
- `pytest -q packages/arx/tests/python/test_codegen_ast_output.py packages/arx/tests/python/test_codegen_file_object.py`:
  27 passed; generated LLVM verifies and source assertions report before
  cleanup/exit.
- `makim arx.test-compiled`: 30 passed, zero failed.
- `pytest -q packages/arx/tests/python/test_wheel_smoke_script.py`: four passed.
- `mypy src` passes in IRx (141 files) and Arx (28 files). Ruff check/format,
  idempotent Douki sync (zero updates), and Vulture pass for all 12 touched
  Python files; Bandit passes its configured high-severity/high-confidence gate
  for touched code.
- All six wheels/sdists rebuilt with `./scripts/build.sh`, using
  `POETRY_VIRTUALENVS_CREATE=false` and workspace-local Poetry cache/TMPDIR
  after the default cache path was rejected by sandbox permissions.
  `python scripts/test_wheels.py --current-environment` passes artifact audit
  and installed-wheel compilation/execution, including the new required native
  header. This offline mode reuses existing third-party dependencies; it is not
  the isolated release gate.
- ABI generation and capability-matrix freshness checks pass; ABI compatibility
  remains 1.0.0. API-doc generation and `git diff --check` pass.
- The default sanitizer invocation was also attempted: LSan exits 23 with its
  explicit ptrace limitation before generated programs run. This is an
  environment blocker, not a passing leak check; CI results remain unobserved.
- No completion of the full M2/M3 milestones, cross-platform/Python matrix,
  fresh third-party dependency installation or Quarto build is inferred from
  these bounded checks.

M2-009/010/013 remain partial with the limitations above. In particular,
allocation failure during consuming C Data move import and legacy RecordBatch
IPC/stream operations still needs an explicit consumption/retry contract and
allocator tests. M3-003/005/006 remain unchanged and incomplete. They require
source operations, focused ASTx nodes, resolved sidecars consumed by native
lowering, and dedicated descriptor handles, not a Python execution fallback.

### 2026-09-17/18 — M3 descriptor execution (M3-003/005/006)

- Implement M3 before M4 because container operations depend on a usable native
  type/schema model. Descriptor support does not imply value/kernel support.
- Use builtin `datatype`, `field`, and `schema` descriptor literals and explicit
  inspection intrinsics; no Arrow-specific public namespace. Keep parameters
  typed in ASTx and validate them in IRx, not in LLVM lowering.
- Resolve portable C Data trees during analysis and lower only those sidecars.
  Native imports copy immutable compiler data into dedicated opaque owners.
  Alternative: compile-time IPC serialization through PyArrow; rejected to keep
  descriptor analysis independent of host Python Arrow execution.

#### Decisions, assumptions and best alternatives

1. **Builtin descriptors, not an Arrow module.** `datatype`, `field` and
   `schema` are ambient value types. `datatype` avoids changing the existing
   `type(...)` query. Closed query names are listed in the lexical manifest and
   modeled as an ASTx enum, never arbitrary native symbol strings in source.
   Alternative: descriptor methods or a general reflection API, once reusable
   method resolution is ready. Any library conveniences should remain
   `stdlib.*`, not `stdlib.arrow.*`.
2. **Descriptors are not container values.** All 45 logical kinds are
   describable; this does not add decimal arithmetic, nested arrays, nullable
   scalars or compute. `conversion_kind` returns
   exact/lossless/explicit/incompatible classifications (0/1/2/3) for two
   literals. Alternative: typed runtime compatibility results and checked value
   casts in M4/M6; do not silently execute casts from this classification.
3. **Resolved C Data, host target.** Analysis canonicalizes and resolves the
   full C Data tree and index promotion. LLVM emits standard C-layout constants
   and calls a version-checked native import-copy operation. Metadata int32
   lengths are checked before lowering. Current metadata encoding assumes host
   endianness, consistent with the existing backend. Alternative: explicit
   target-data serialization for cross compilation. PyArrow IPC serialization
   during compilation was rejected as an unnecessary host dependency.
4. **Metadata and reflection.** Source names, metadata and extension payloads
   use UTF-8 literals. Binary keys/values still round-trip through ASTx and the
   native ABI. Alternative: add language byte literals before arbitrary binary
   source metadata. Type handles normalize away outer field names/nullability
   and ordinary metadata, while retaining opaque extension identity and nested
   metadata. `type_field` reflects Arrow physical fields, not synthetic
   dictionary/extension children; export preserves their complete C Data.
   Alternative: a separate logical-child reflection API.
5. **Owned names and descriptor lifetimes.** Field-name queries return malloc
   copies managed as owned strings; they do not borrow a destroyed descriptor.
   Alternative: a rooted borrowed-string view once that ABI exists. Schema,
   field and type owners use existing retain/release, moves and lexical cleanup.
   Class construction zero-initializes descriptor slots before any fallible
   initializer. Unmanaged structs, container elements, nullable wrappers and
   yielded descriptors remain fail-closed until element destruction/transfer is
   implemented. Suspended descriptor locals do not imply generator source syntax
   support. Fatal native errors clean current-function owners; this does not
   implement cross-function stack unwinding.
6. **Append-only native ABI.** ABI 1.1.0 adds 19 symbols and field handle kind
   15; the array feature contract is 1.2.0. Existing signatures/IDs are
   unchanged. ELF symbols keep `IRX_ARROW_1.0` rather than renaming the version
   node on a compatible minor bump. Alternative: explicit per-symbol
   introduction nodes with version inheritance; changing every old symbol to
   `IRX_ARROW_1.1` would break existing linked consumers. The capability
   inventory's initial ABI decision remains 1.0.0, distinct from the current
   runtime ABI.
7. **Gate accounting.** M3-003 and M3-005 cover executable descriptors;
   M3-006/M3 and Gate B remain PARTIAL. M2 import-copy allocation sweeps now
   also include type/field owners, but do not prove all native operations
   failure atomic. Alternative: split the descriptor exit gate from container
   Gate B in a future roadmap revision; this implementation does not silently
   close it.

#### Verification record

Final focused checks and environment limitations are recorded below. The broad
IRx/ASTx suite, broad Arx Python suite and full compiled-language suite were
started, then interrupted when concurrent native compilation exhausted this 8 GB
environment (less than 250 MB available and severe system load). These are **not
passing full-suite results**. The installed-wheel smoke driver also hit its
300-second timeout during that load; all six wheel builds completed.

Completed checks:

- **1,002 passed** in the sequential regression run below. This includes all
  ASTx tests and IRx semantic-analysis tests, all 45 descriptor families, ABI
  declaration/export conformance, canonical capability metadata, the updated
  ABI/feature-version harness, Arx descriptor integration and translate paths.

  ```bash
  TMPDIR="$PWD/.tmp" pytest -q \
    packages/irx/tests/analysis packages/astx/tests \
    packages/irx/tests/test_descriptor_execution.py \
    packages/irx/tests/test_arrow_abi_manifest.py \
    packages/irx/tests/test_arrow_abi_conformance.py \
    packages/irx/tests/test_arrow_capability_matrix.py \
    packages/irx/tests/test_arrow_runtime.py::test_arrow_runtime_reports_stable_abi_and_feature_versions \
    packages/arx/tests/python/test_descriptors.py \
    packages/arx/tests/python/test_codegen_ast_output.py
  ```

- **ASan/UBSan passed:**
  `TMPDIR="$PWD/.tmp" python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`
  exercises the native harness and six generated LLVM ownership programs. New
  cases cover descriptors in class fields, replacement, projection, owned
  field-name strings, bounds-failure cleanup and suspended locals on
  exhaustion/early close/failure. LSan was deliberately disabled; no successful
  LSan run is claimed.
- `mypy src` passed in `packages/arx`, `packages/astx` and `packages/irx` (29,
  55 and 144 source files respectively). Package-configured Ruff checks and
  formatting passed on the touched Python files; native additions pass Google
  clang-format verification. Douki's complete rerun was idempotent (33 checked
  files; generated declarations are excluded by its own configuration).
- ABI generation `--check`, compatibility with the 1.0 baseline, capability
  matrix generation `--check`, lexical manifest JSON validation, API
  documentation generation and `git diff --check` passed.
- An initial ABI symbol-parity test missed the new included implementation file;
  its source inventory now includes it. An outdated feature-version assertion
  was updated to 1.2.0 (with 1.3.0 rejected). A sanitizer harness assertion-only
  expectation was generalized to accept the _specific expected_ descriptor
  runtime diagnostic. Their focused reruns passed; errors were not suppressed.

Unrun gates: full repository CI/lint, Quarto rendering, a fresh-dependency wheel
isolation run, successful LSan and the Python 3.10–3.13 matrix. The interrupted
full-suite attempts must not be used as evidence for these gates.

Additional focused results:

- `pytest -q packages/irx/tests/test_arrow_allocation_failures.py -k cpp_allocation_failure_sweep`:
  **1 passed** in the final combined edge run (the two accompanying new Unicode
  tests initially expected the wrong error phase). Type/field import-copy
  allocation failures preserve producer callbacks, publish no output, and allow
  retry; the existing Array/Tensor finish sweeps also execute in this harness.
- `pytest -q packages/arx/tests/python/test_descriptors.py -k source_metadata_rejects_invalid_unicode`:
  **2 passed** after asserting the existing `SourceError` boundary, not
  inventing a parser encoding check. ArxIO already rejects invalid UTF-8 before
  lexing.
- `TMPDIR="$PWD/.tmp" arx test packages/arx/tests/arx/test_schema_descriptors.x`:
  **2 passed**, including mutable class fields for all three descriptor owner
  types.
- `python scripts/test_wheels.py --audit-only`: **passed**, including the new
  native descriptor include. The installed-wheel smoke now also compiles and
  runs a native descriptor source program from the installed packages.

Final delivery checks:

- The sequential `python scripts/test_wheels.py --current-environment` retry
  **passed**, including native descriptor execution and installed asset/header
  checks. The earlier timeout is no longer an outstanding local smoke failure.
  This mode reuses existing third-party dependencies and is not the isolated
  fresh-environment release gate. Wheel/source byte comparisons found no
  mismatches in Arx, ASTx or IRx packaged files.
- `TMPDIR="$PWD/.tmp" arx --run examples/schema_descriptors.x` exited **0**.
- Vulture (`--min-confidence 80`) passed on the touched Python files. Bandit's
  high-confidence/high-severity gate (`-iii -lll`) passed; its inventory still
  includes lower-severity findings, so this is not a zero-findings claim. The
  McCabe probe reports complexity **11** for the new descriptor parameter
  parser; it is advisory, not a zero-warning result.

### 2026-09-18 — Primitive nullable scalar foundation (M4-001, done)

- Preserve `T | none` source syntax and normalize it to reusable ASTx
  `NullableType(T)` semantic types. Begin with numeric and Boolean payloads;
  reject managed payloads and nested value wrappers before lowering.
- Represent an immediate nullable value as a language-owned LLVM
  validity/payload pair, not an Arrow C++ layout or a heap-allocated Arrow
  Scalar. Arrow extraction will use separate status, validity and typed payload
  slots. Alternative: opaque Arrow Scalar owners for every value, with
  additional allocation costs.
- Implement `is_null`, `is_valid` and checked `expect_valid` as ambient
  builtins. Do not pretend ordinary nullable operators or predicate flow
  narrowing are implemented; these stay explicit M4-002 work.
- The initial Arx spellings are existing Boolean, signed integer and float
  types. IRx additionally supports unsigned 8/16/32/64-bit payloads.
  Alternative: expose unsigned aliases in this slice; deferred to avoid claiming
  unrelated frontend numeric support without its own lexer/parser/literal
  coverage.
- Source nullable locals require explicit initialization; direct ASTx locals
  without an initializer use initialized null storage. Alternative: synthesize
  `none` for source locals too, after a broader default-initialization decision.
- Bare returns now use ASTx `FunctionReturn(value=None)`, distinct from an
  explicit `LiteralNone` return. Existing void execution remains unchanged.
  Alternative: add a separate return-presence flag or statement class; using the
  existing downstream optional-value checks is the smaller reusable contract.
- Nullable class/struct fields, container elements and C FFI signatures fail
  before lowering. They need separate layout/lifetime and interchange tests; the
  internal aggregate is not a public C ABI or an Arrow C++ object layout.
  Alternative: implement primitive aggregate fields immediately, but that would
  expand this local/parameter/return slice into static/module initialization.
- `expect_valid` is an explicit fatal checked unwrap. It performs current-frame
  cleanup before reporting `ARX-RUNTIME-NULL-001`; it does not claim recoverable
  exceptions or caller-frame unwinding. Alternatives: a recoverable result type,
  pattern matching, or proven flow narrowing; all require additional semantics.
- A passing `is_valid` condition does not narrow a variable's type. Alternative:
  flow-sensitive refinement with invalidation on assignment and aliasing, kept
  as M4-002 rather than an unsafe syntactic special case.
- Nullable examples exposed two pre-existing core gaps: scalar unary `+`/`-`
  passed analysis without general lowering, and `if` parsing consumed the next
  line marker even without a matching `else`. This slice repairs both with
  resolved-operator lowering, numeric operand validation, and indentation-aware
  branch lookahead. Integer negation follows existing modular arithmetic;
  floating negation uses LLVM `fneg` rather than subtraction from positive zero.
  Alternative: avoid these forms in examples; rejected because they are basic
  prerequisites for useful nullable control flow and signed payloads.
- Added a generated sanitizer program that owns a schema descriptor and a
  dynamic string before failing `expect_valid`, so the existing native ownership
  gate also exercises nullable fatal-path cleanup.

#### M4-001 verification record

Checks were run sequentially on the available Python 3.14/Linux toolchain:

- `pytest -q packages/astx/tests`: **538 passed**.
- `pytest -q packages/irx/tests/analysis packages/irx/tests/test_nullable_runtime.py packages/irx/tests/test_none.py`:
  **322 passed**, including native storage for twelve primitive payload types.
- `pytest -q packages/arx/tests/python/test_nullable_syntax.py packages/arx/tests/python/test_parser*.py packages/arx/tests/python/test_codegen_ast_output.py packages/arx/tests/python/test_descriptors.py packages/arx/tests/python/test_lexer*.py`:
  **663 passed**, including nullable example execution, scalar sign lowering,
  branch/dedent regressions, failure diagnostics and current-frame cleanup.
- `pytest -q packages/irx/tests/test_descriptor_execution.py -k 'wrappers or inferred'`:
  **6 passed**, 56 deselected. Descriptor nullable wrappers still fail in
  analysis, now through the primitive-payload support boundary.
- `TMPDIR="$PWD/.tmp" arx test packages/arx/tests/arx/test_nullable_scalars.x`:
  **1 compiled-language test passed**.
- `mypy src` from each of `packages/astx`, `packages/irx`, `packages/arx`,
  `packages/arxjit`, `packages/arxpy`, and `packages/aix`: **all passed** (56,
  147, 29, 10, 5 and 21 source files respectively).
- `TMPDIR="$PWD/.tmp" python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`:
  **passed** the native harness and all seven generated programs, including
  `nullable_failure`. LLVM ASan instrumentation is checked by the harness;
  native artifacts are built with ASan/UBSan. LSan was explicitly disabled
  because of the previously recorded sandbox/ptrace limitation; this does not
  close the leak-detection gate.
- The ASTx descriptor docstrings from M3 contained inherited `loc`/`type_`
  attribute stubs that prevented a subsequent Douki run. Explicit annotations
  and synchronized documentation repair those stubs; no descriptor runtime
  behavior changed.

- Ruff checks and formatting checks passed for the changed Python files using
  the owning package configurations; Douki synchronization is idempotent.
- `python scripts/gen_arrow_capability_matrix.py --check` and
  `python scripts/gen_arrow_abi.py --check` passed. The capability matrix
  records primitive nullable support without upgrading the full null/container
  rows.
- Prettier checks passed for the changed nullable documentation and JSON
  manifests; `python -m json.tool packages/arx/src/arx/lexer/syntax.json` and
  `git diff --check` passed.

M4-002 through M4-004 remain **NOT STARTED**. M4 and combined Gate B remain
incomplete. This slice does not claim nullable operators, flow narrowing,
managed payloads, general Arrow array construction/extraction, public C nullable
ABIs, installed-wheel verification, full repository CI, Quarto builds, or the
Python 3.10–3.13 matrix.

### 2026-09-19 — M4 nullable operations and primitive arrays (partial)

This continuation implements additional end-to-end foundations, **not the whole
M4 exit criteria**. M4-002 and M4-003 remain partial; M4-004 remains not
started. Descriptor coverage is not value-execution coverage.

#### Implementation tracking

- **DONE (bounded subtask):** primitive nullable arithmetic, comparisons, unary
  signs/not, short-circuit Kleene logic, direct predicate narrowing, mutation
  invalidation and conservative branch/loop joins.
- **DONE (bounded subtask):** ASTx array expressions, Arx typed
  constructors/annotations, IRx resolved signatures and managed opaque owners;
  nullable extraction, length/null count/offset, slice, concat, copy and
  equality.
- **Pending M4-002:** managed nullable payload lifetime/destruction, aggregate
  fields, richer compound-predicate proofs and explicit nullable casts.
- **Pending M4-003:** public dynamic builders, buffer and source C Data
  constructors, half-float storage, chunked arrays and rechunking.
- **Pending M4-004:** variable-width and recursive nested values, typed batch/
  table construction and transformations, static/dynamic projection, metadata,
  expanded DataFrame/Series values and explicit batch/row/column iteration.

#### Decisions and top three alternatives

1. **Decision:** keep immediate nullable operators builtin and unboxed;
   propagate null before payload work and short-circuit decisive Kleene
   Booleans. Reject explicit fast-math/FMA/unsigned modifiers rather than
   silently ignoring them. **Top three alternatives:** (1) call Arrow Compute
   for each scalar operation; (2) allocate an opaque Arrow Scalar for every
   intermediate; (3) require explicit validity handling for all arithmetic. The
   chosen representation preserves the primitive storage foundation without heap
   allocation or Python.
2. **Decision:** refine direct local/argument predicates with symbol-identity
   facts, invalidate on assignment, intersect at joins, and discard inherited
   facts at loop backedges. Guarded Boolean RHS reads also receive direct facts;
   arbitrary compound branch facts are not inferred. **Top three alternatives:**
   (1) full SSA/path-sensitive proof analysis; (2) immutable-bindings-only
   refinement; (3) checked unwraps exclusively. Conservative rejection is
   preferred to stale proofs or alias assumptions.
3. **Decision:** expose immutable `array[T]` and `array[T | none]` as ambient
   language values, not `stdlib.arrow` wrappers. Constructors require explicit
   element types; nullable extraction always returns a validity/payload pair.
   **Top three alternatives:** (1) overload existing mutable list literals; (2)
   expose builders before array values; (3) implement arrays only in a
   namespaced standard library. Existing ASTx logical types remain reusable.
4. **Decision:** use shared opaque array owners, zero-copy slices, explicit
   buffer-rebuilding copies, and concatenation through Arrow C++ primitives.
   Preserve bit-packed Booleans and use offset-aware typed accessors only after
   validity checks. Native ABI 1.2.0 adds symbols; array capability 1.3.0 gates
   their use without changing existing symbol signatures or ELF version nodes.
   **Top three alternatives:** (1) expose raw Arrow buffers directly to LLVM;
   (2) eagerly materialize every slice; (3) convert arrays to mutable Arx lists.
   The chosen design keeps C++ layouts private and child lifetimes independent.
5. **Decision:** expose unsigned scalar spellings to make unsigned array values
   usable in source. Preserve existing explicit-cast and whole-domain lossless
   assignment rules; narrow/signed-to-unsigned literals require explicit casts.
   **Top three alternatives:** (1) keep unsigned execution IRx-only; (2) add
   context-sensitive integer literals now; (3) implicitly truncate or
   reinterpret integers. Context-sensitive checked literals are the strongest
   follow-up; silent truncation is not an acceptable default.
6. **Decision:** keep unsupported managed/nested execution fail-closed and keep
   M4 open. General iteration and DataFrame/Table naming are not settled by the
   primitive array API. **Top three alternatives:** (1) prioritize dynamic
   builders and managed scalar destruction next; (2) implement opaque nested
   Scalar values before native language payloads; (3) prioritize typed batches
   over additional scalar syntax. No Python fallback or descriptor-only model is
   counted as native value support.

Additional implementation notes: `array[...]` now denotes a native typed
columnar owner, not the removed legacy raw-array representation. A parser
regression asserts this intentional new meaning. Arrays exposed a pre-existing
ASTx `LiteralNone.get_struct()` failure: structural primitive values now include
`None`, allowing nullable ASTs to render without bypassing runtime validation.
Failure-only Arrow error cleanups are removed after successful calls so sibling
branches never reference undominated output slots. Array builder owner slots are
initialized in the function entry block, and typed finish validates nullability
before consuming the builder.

7. **Decision:** include genuine null in ASTx structural primitive values,
   rather than special-casing array rendering. **Top three alternatives:** (1)
   override only `LiteralNone.get_struct`; (2) serialize null as a string token;
   (3) replace it with the existing undefined sentinel. The chosen contract
   preserves the distinction between a null value and absent/undefined data.
8. **Decision:** register native error ownership only through its failure guard,
   removing that cleanup on success, where the ABI guarantees an empty error
   slot. **Top three alternatives:** (1) hoist every error slot to function
   entry; (2) release errors directly inside a new shared failure helper; (3)
   introduce general branch-scoped cleanup regions. The targeted approach fixes
   dominance without expanding the lifetime representation in this slice.

9. **Decision:** reject generic scalar unary/binary operators on array and
   descriptor owners, and on the existing DataFrame/Series owners. Use typed
   operations (`array_equal` or `descriptor_equal` where applicable). This
   closes a lowering hazard where opaque `i8*` handles could enter string
   comparison or pointer arithmetic. **Top three alternatives:** (1) overload
   equality with Arrow value semantics; (2) expose a distinct explicit
   owner-identity predicate; (3) introduce comparison traits/methods. Closed
   typed operations avoid prematurely choosing elementwise versus
   whole-container equality.

#### M4 continuation verification

The following checks passed on the available Linux/Python 3.14 toolchain:

- `pytest -q packages/astx/tests`: **540 passed**.
- `pytest -q packages/irx/tests/analysis packages/irx/tests/test_nullable_runtime.py packages/irx/tests/test_none.py packages/irx/tests/test_arrow_abi_manifest.py packages/irx/tests/test_arrow_abi_conformance.py packages/irx/tests/test_array_value_runtime.py`:
  **355 passed**. This includes ABI declaration/export parity and compatibility.
- `pytest -q packages/arx/tests/python/test_nullable_syntax.py packages/arx/tests/python/test_nullable_operations.py packages/arx/tests/python/test_array_values.py packages/arx/tests/python/test_codegen_ast_output.py packages/arx/tests/python/test_parser*.py packages/arx/tests/python/test_lexer*.py`:
  **630 passed**, including verified LLVM, native execution and failure paths.
- A subsequent
  `pytest -q packages/irx/tests/test_nullable_runtime.py packages/irx/tests/test_descriptor_execution.py packages/irx/tests/test_arrow_allocation_failures.py packages/irx/tests/test_arrow_capability_matrix.py packages/irx/tests/test_array_value_runtime.py`:
  **163 passed**. This overlapping follow-up includes the missing nullable
  operator sidecar regression and strengthened nonzero offsets for all eleven
  primitive array storage types; do not add it to the earlier counts as unique
  test coverage.
- A further
  `pytest -q packages/arx/tests/python/test_array_values.py packages/arx/tests/python/test_descriptors.py packages/arx/tests/python/test_nullable_operations.py packages/irx/tests/test_descriptor_execution.py`:
  **164 passed**, including seven new rejections of scalar operations on opaque
  array/descriptor owners. This is overlapping regression coverage.
- `pytest -q packages/arx/tests/python/test_array_values.py packages/arx/tests/python/test_dataframe.py`:
  **34 passed** after extending the scalar-operator guard to existing
  DataFrame/Series owners. IRx strict mypy and the rebuilt installed-wheel smoke
  were then rerun successfully. An initial attempt also named a nonexistent IRx
  analysis test glob and collected no tests; the corrected command above is the
  executed coverage, not that failed invocation.
- `pytest -q packages/arx/tests/python/test_nullable_operations.py`: **12
  passed** after adding native call/return, valid addition and null propagation
  coverage for all eleven numeric nullable payload widths, including half-float
  and unsigned integers. Boolean Kleene coverage also remains in this
  overlapping suite.
- `TMPDIR="$PWD/.tmp" arx test packages/arx/tests/arx/test_columnar_arrays.x`:
  **1 passed**, including functions returning independently owned slices.
- `mypy src` in ASTx, IRx, Arx, ArxJIT, ArxPy and AIX: **all passed** (57, 153,
  30, 10, 5 and 21 source files).
- `TMPDIR="$PWD/.tmp" python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`:
  **passed** the native harness and all **nine** generated programs, including
  successful array owners and fatal nullable extraction with array cleanup. LSan
  was explicitly disabled; no leak-detection completion is claimed.
- Ruff checks and formatting passed on all **74** modified/new Python files;
  Douki synchronization was idempotent. Generated ABI and capability checks,
  syntax JSON validation, Prettier and `git diff --check` passed.
- Rebuilt ASTx/IRx/Arx wheels and sdists locally using
  `poetry.core.masonry.api.build_wheel` / `build_sdist` (no dependency
  resolution). The first artifact-only audit correctly found an old IRx wheel
  missing the new native include. After rebuilding,
  `python scripts/test_wheels.py --audit-only` **passed**.
- `TMPDIR="$PWD/.tmp" python scripts/test_wheels.py --current-environment`:
  **passed**, including installed-package primitive array and nullable operator
  execution. This reuses installed third-party dependencies; it is not the
  isolated fresh-environment release gate.

Native ABI **1.2.0** now exposes **101** manifest functions; the eight additive
array symbols are gated by array feature **1.3.0**. Existing C signatures and
ELF compatibility nodes remain unchanged.

**M4 is PARTIAL, not complete.** The pending work listed above remains required.
No full repository CI, Quarto build, isolated release installation, LSan run, or
Python 3.10–3.13 matrix was performed. Previous milestone/Gate B blockers remain
open where not explicitly discharged by these checks.

### 2026-09-19 — M4 continuation: reusable builders and chunked arrays

**Implemented and verified (bounded continuation):** source-visible unique
primitive builders and immutable chunked arrays, including explicit chunk
iteration, slicing, concatenation, copying, equality, and combine-chunks. This
continuation also adds nullable shared array/descriptor owners and half-float
array storage. This entry does not claim that modeled nested types execute.

- **Decision:** public `builder_finish` resets a borrowed unique builder for
  reuse rather than consuming its local binding. The internal consuming finish
  ABI remains unchanged. **Top three alternatives:** (1) statically consume the
  binding with move analysis; (2) return a builder/array tuple; (3) freeze the
  builder permanently and diagnose subsequent mutation at runtime.
- **Decision:** expose `chunked_array[T]`, `chunk_count`, `chunk_at`, and
  `combine_chunks` as ambient builtins. Scalar access resolves across chunks; no
  implicit rechunking or iteration is introduced. **Top three alternatives:**
  (1) silently combine at every array operation; (2) erase physical chunks from
  the type system; (3) expose chunking only through `stdlib` wrappers.
- **Decision:** preserve the existing shared chunked-owner lifecycle in the
  registered DataFrame runtime feature, while array primitives use the array
  feature. The semantic sidecar activates both for chunked values. **Top three
  alternatives:** (1) move existing lifecycle symbols to core immediately; (2)
  duplicate lifecycle implementations across capability objects; (3) introduce a
  new independently packaged chunk runtime feature.

#### Additional decisions and top three alternatives

- **Decision:** represent nullable immutable shared owners with a reserved null
  pointer. Empty valid Arrow arrays still have a non-null handle. Guard retains
  of absent owners, reuse null-safe slot release, and preserve borrowed
  extraction plus retained copy/return boundaries. This applies to primitive
  arrays, chunks and runtime datatype/field/schema descriptors, not unique
  builders or strings. **Top three alternatives:** (1) use a validity/payload
  aggregate for every managed optional; (2) allocate an opaque optional-owner
  wrapper; (3) prohibit nullable owners and expose only nullable scalar cells.
  Primitive nullable values retain their independent validity/payload ABI.
- **Decision:** reuse IRx's failure-atomic snapshot builder and reset only after
  successful snapshot and metadata publication. Ordinary Arrow Finish is not a
  substitute for this retry guarantee. **Top three alternatives:** (1) consume
  builders on finish; (2) switch to destructive Arrow Finish and document lost
  state after allocation failure; (3) copy the entire builder before every
  mutation. Allocation-failure tests must verify retry data and reset timing.
- **Decision:** implement binary16 arrays numerically through Arrow's Float16
  conversion and the existing double scalar ABI. Half bits are never exposed as
  unsigned integer values. Do not enable half-float tensor/buffer views without
  their own buffer ABI contract. **Top three alternatives:** (1) expose a new
  half-bit scalar C ABI; (2) expand buffer dtype and tensor contracts in this
  change; (3) promote all half arrays to float32 storage, losing physical type
  identity. Half-float adds stable primitive type ID 12; existing IDs remain.
- **Decision:** keep `chunked_array[T]` and the legacy `series[T]` distinct for
  now, rejecting silent cross-conversion. The former carries ASTx logical types
  and nullability; the latter is the existing DataFrame projection surface.
  **Top three alternatives:** (1) migrate Series to logical element descriptors
  immediately; (2) add explicit lossless Series/chunk conversion builtins; (3)
  expose chunks only through Series methods. An explicit unification or
  conversion design remains M4-004 work, not an accidental alias.

#### Implementation tracking for this continuation

- **DONE:** reusable primitive builder construction, append, reserve, length and
  reset-on-success finish; unique-owner copy rejection and borrowed operations.
- **DONE:** primitive chunked construction, length/null count, cross-chunk
  scalar access, strict slicing, concat, copy, equality, chunk access/count and
  explicit combine. Constructors check logical type/nullability; native paths
  check shape/size bounds and preserve independently owned child storage.
- **DONE:** nullable immutable array, chunked array and descriptor owners,
  including defaults, calls, return, borrowed unwrap, aliasing, replacement,
  null retention guards, failure cleanup and logical descriptor validation.
- **DONE:** half-float array storage, snapshot builders, scalar extraction,
  chunking and C Data/PyArrow interchange. Tensor half-float remains
  unsupported.
- **PENDING M4-002:** unique/string nullable payloads, class/struct fields,
  richer compound predicate proofs and explicit nullable casts.
- **PENDING M4-003:** source buffer and source C Data constructors. Native
  interchange evidence must not be counted as Arx source constructor support.
- **PENDING M4-004:** variable-width and recursive nested values, full typed
  batches/tables, dynamic/static projection and schema transformations,
  DataFrame/Series expansion and explicit batch/row/column iteration APIs.

Native ABI **1.3.0**, array capability **1.4.0**, **117** manifest functions.
The sixteen additive builder/chunk functions leave existing signatures and ELF
compatibility nodes unchanged. No Python execution fallback was introduced.

#### Verification for reusable builders, chunking and nullable owners

Available toolchain: Linux and Python 3.14. Final checks below passed; counts
from separate runs overlap and should not be summed as unique test coverage.

- `pytest -q packages/astx/tests`: **540 passed**.
- `pytest -q packages/irx/tests/analysis packages/irx/tests/test_nullable_runtime.py packages/irx/tests/test_arrow_abi_manifest.py packages/irx/tests/test_arrow_abi_conformance.py packages/irx/tests/test_array_value_runtime.py packages/irx/tests/test_chunked_value_runtime.py packages/irx/tests/test_arrow_allocation_failures.py packages/irx/tests/test_arrow_capability_matrix.py packages/irx/tests/test_tensor.py`:
  **439 passed**. Includes source-independent semantics, twelve primitive array
  storage families, C Data/PyArrow offsets, chunk parent/child lifetimes,
  allocation-failure retry/reset, ABI parity and legacy tensor regressions.
- `pytest -q packages/arx/tests/python/test_nullable_syntax.py packages/arx/tests/python/test_nullable_operations.py packages/arx/tests/python/test_nullable_owners.py packages/arx/tests/python/test_array_values.py packages/arx/tests/python/test_chunked_values.py packages/arx/tests/python/test_codegen_ast_output.py packages/arx/tests/python/test_parser*.py packages/arx/tests/python/test_lexer*.py packages/arx/tests/python/test_dataframe.py`:
  **662 passed**, including LLVM verification and linked native execution.
- `TMPDIR="$PWD/.tmp" arx test packages/arx/tests/arx/test_columnar_builders.x`:
  **1 passed**. The example also tests returning chunks after parent scope exit.
- `mypy src` in ASTx, IRx, Arx, ArxPy, ArxJIT and AIX: **all passed** (57, 154,
  30, 5, 10 and 21 source files respectively).
- Ruff check and format checks passed on all **81** modified/new Python files.
  Douki synchronization was idempotent, including the final signature changes.
- `TMPDIR="$PWD/.tmp" python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`:
  **passed**, native harness plus **11** generated programs. Added nullable
  chunk owners and unique builders on success and fatal null extraction paths.
  LSan was explicitly disabled and is not claimed.
- Built ASTx/IRx/Arx wheels and sdists with
  `poetry.core.masonry.api.build_sdist` / `build_wheel`.
  `python scripts/test_wheels.py --audit-only` **passed**.
- `TMPDIR="$PWD/.tmp" python scripts/test_wheels.py --current-environment`:
  **passed**, including installed builder reset, chunk scalar access, nullable
  owner alias/replacement and half-float execution. This is not the isolated
  fresh-environment release gate.
- A final
  `pytest -q packages/irx/tests/test_arrow_capability_matrix.py packages/irx/tests/test_arrow_runtime.py::test_arrow_runtime_reports_stable_abi_and_feature_versions`:
  **12 passed**, after the documentation-only foundation update.
- Generated ABI/capability checks, syntax JSON validation, Prettier and
  `git diff --check` passed. Intermediate runs found stale ABI expectations and
  a matrix invalidated by manifest formatting; regeneration and final reruns
  above are the verified results. A void-query test assertion pattern was also
  corrected to match the existing actionable diagnostic.

**M4 remains PARTIAL, not complete.** The pending M4-002/003/004 work above is
still required. No full repository CI, Quarto build, LSan, isolated release
installation or Python 3.10–3.13 matrix was run in this continuation.

### 2026-09-21 — M4 continuation: nullable foundations and typed tabular values

**Overall M4 status: PARTIAL.** This entry supersedes earlier pending lists only
for the items explicitly completed below. The milestone's all-core-types exit
criterion has **not** been met; descriptor coverage and native-only imported
nested-container transformations do not imply Arx source value support.

| Subitem                                                                   | Status          | Implementation / remaining boundary                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Repair native include formatting                                          | **DONE**        | Three committed handwritten `.inc` files were formatted as HTML/prose and failed native compilation. Restored their local wheel sources only after reproducing the committed bytes exactly with the formatter; all native `.inc` files now excluded from Prettier. |
| Compound nullable predicate facts                                         | **DONE**        | Set-based AND/OR/negation proofs, conservative joins and side-effect exclusions; assignment invalidates facts. Mutable fields are not refined.                                                                                                                     |
| Explicit primitive nullable casts                                         | **DONE**        | Preserve validity, convert only present payloads, permit explicit injection, reject implicit unwrap and managed casts. Numeric conversion behavior follows existing primitive `cast`.                                                                              |
| Nullable unique array builders                                            | **DONE**        | Optional construction, borrowing, replacement and moved local returns; copying unique owners remains rejected.                                                                                                                                                     |
| Nullable instance fields                                                  | **DONE**        | Primitive and implemented opaque-owner fields default to absence, support initialization/replacement, and use existing class destruction. Field extraction borrows; escaping shared owners retain.                                                                 |
| Primitive nullable struct fields                                          | **DONE**        | By-value validity/payload layout, default absence, assignment and extraction. This is an ASTx/IRx path, not a claim of new Arx `struct` syntax.                                                                                                                    |
| Nullable strings, other managed payloads and managed struct fields        | **NOT STARTED** | Strings need storage-class-aware ownership; other aggregate/collection payloads need explicit lifetime contracts; managed structs need recursive copy/destruction. Static nullable fields remain explicitly rejected.                                              |
| Source buffer / external C Data constructors                              | **NOT STARTED** | Native interchange exists; a safe typed Arx producer/consumer boundary remains required.                                                                                                                                                                           |
| Typed primitive RecordBatch/Table values                                  | **DONE**        | Ambient `record_batch`/`table`, explicit row count, static schemas, nullable primitive columns, empty schemas, calls/returns, optional shared owners.                                                                                                              |
| Checked projection and structural transforms                              | **DONE**        | `column`, `column_as`, rows/columns/schema inspection, slice, select/reorder, rename, add/replace/remove, combine chunks, batch/table conversion; metadata retained.                                                                                               |
| Variable-width, temporal, decimal, dictionary and recursive source values | **NOT STARTED** | Native imported nested batch/table views are tested, but source construction and scalar extraction for these families are not implemented.                                                                                                                         |
| General row selection and legacy DataFrame/Series adapters                | **NOT STARTED** | Contiguous row slicing and explicit indexed iteration work. Noncontiguous selection and intentional compatibility adapters remain pending.                                                                                                                         |

#### Decisions, assumptions, and top three alternatives

1. **Native include formatting belongs to C++ tooling, not Prettier.** Local
   wheel recovery was byte-verified against a reproduction of the corruption; no
   remote tree was consulted and no implementation changes were inferred.
   Alternatives: (1) rename includes to C++-recognized suffixes; (2) restrict
   the Prettier hook to a positive extension allowlist; (3) move each included
   implementation to a separate translation unit.
2. **Nullable numeric casts preserve nullability rather than implicitly
   unwrapping.** Narrowing has the existing scalar cast semantics; this is not a
   new checked Arrow Compute cast API. Proofs are conservative set algebra over
   side-effect-free conditions and direct local/argument predicates.
   Alternatives: (1) checked/saturating casts with an error result; (2) explicit
   `map_valid` application; (3) a separate nullable conversion intrinsic for
   each numeric family.
3. **Optional unique builders keep unique ownership.** They reserve null
   pointers for absence, just like shared opaque owners, but may not be copied.
   Managed nullable instance fields reuse class cleanup; primitive nullable
   struct fields require no owner cleanup. Nullable string/storage-class support
   and recursive managed struct destruction are not silently approximated.
   Alternatives: (1) validity-plus-owner aggregates for every handle; (2)
   consume optional builders on `builder_finish`; (3) disallow nullable
   resources in fields until a generalized drop system.
4. **Tabular constructors take row count first.** `record_batch[](5)` preserves
   five zero-column rows. RecordBatch columns are arrays; Table columns are
   chunked arrays. Construction validates shape, logical type and nullability
   before publishing an owner. Tables are not aliases for legacy DataFrames; the
   latter's existing grammar and semantics remain unchanged. Alternatives: (1)
   infer rows and restrict empty schemas to zero rows; (2) infer rows except for
   a dedicated empty-schema constructor; (3) introduce a mandatory builder for
   every tabular container.
5. **Static projection resolves names in analysis; dynamic projection checks a
   complete expected field at runtime.** `runtime_schema` explicitly erases the
   static schema; `column_as(value, index, field[...])` checks name, type,
   nullability and metadata before producing a typed child. There is no unsafe
   downcast based only on an opaque handle or a requested scalar width.
   Alternatives: (1) dynamic variant/scalar results; (2) schema-pattern matching
   that refines the whole container; (3) projection by expected datatype alone,
   discarding name/metadata checks.
6. **Transforms are immutable and preserve independent ownership.** Slices and
   projections may share Arrow buffers; column edits create new containers;
   rechunking/materialization is explicit. Selection names are unique, metadata
   survives transforms, bounds are strict rather than clamped. Iteration stays
   explicit: indexed rows via slices, columns via checked projection, scalars
   via array access. No default row/batch iteration is introduced. Alternatives:
   (1) mutable in-place tables; (2) copy-on-write containers; (3) lazy
   relational/query-plan nodes, deferred to later compute work.
7. **The tabular ABI extends the existing registered DataFrame capability.** ABI
   **1.4.0**, DataFrame contract **1.1.0** add 23 status-returning operations;
   existing signatures and the historical compatibility baseline are unchanged.
   Batch lifecycle still belongs to the RecordBatch feature. Compiler sidecars
   carry symbol, feature, minimum version, operands and projection indices;
   lowering performs no schema/name resolution. Alternatives: (1) a new tabular
   feature/artifact; (2) split every operation between RecordBatch and DataFrame
   features; (3) move all tabular and chunked operations into the array feature.

#### Verification

Final checks executed for this continuation (Linux, Python **3.14**):

- `pytest -q packages/astx/tests`: **542 passed**.
- IRx analysis plus tabular, nullable, array/chunk, struct, descriptor and ABI
  manifest/conformance tests: **448 passed**. Exact target set:
  `packages/irx/tests/analysis`, `test_tabular_runtime.py`,
  `test_nullable_runtime.py`, `test_arrow_abi_manifest.py`,
  `test_arrow_abi_conformance.py`, `test_array_value_runtime.py`,
  `test_chunked_value_runtime.py`, `test_struct_definition.py`, and
  `test_descriptor_execution.py` under `packages/irx/tests/`.
- Arx nullable syntax/operators/owners/refinement/fields, array/chunk/tabular,
  codegen AST output, parser, lexer and DataFrame regressions: **698 passed**.
  Exact Python targets: `test_nullable_syntax.py`,
  `test_nullable_operations.py`, `test_nullable_owners.py`,
  `test_nullable_refinement_casts.py`, `test_nullable_fields.py`,
  `test_array_values.py`, `test_chunked_values.py`, `test_tabular_values.py`,
  `test_codegen_ast_output.py`, `test_parser*.py`, `test_lexer*.py`, and
  `test_dataframe.py` under `packages/arx/tests/python/`.
- Additional descriptor/runtime ABI-version/capability-matrix checks: **73
  passed** (overlaps the descriptor tests above).
- `arx test packages/arx/tests/arx/test_columnar_tables.x`: **1 passed**. Direct
  `pytest` does not collect `.x` files; the successful compiled-language check
  used the repository's Arx test runner.
- Six-package strict mypy: **passed** (ASTx 58, IRx 157, Arx 31, ArxPy 5, ArxJIT
  10, AIX 21 source files).
- Ruff check/format on **43** changed/new Python files: **passed** with each
  owning package's configuration (ASTx/tools use the root configuration). Douki
  synchronization: **0 updated**, idempotent.
- `python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`:
  native harness and **13 generated programs passed** under ASan/UBSan,
  including tabular success/failure and nullable class-owner destruction.
  LeakSanitizer detection was explicitly disabled, not claimed as passed.
- ASTx/IRx/Arx wheels and sdists rebuilt with local Poetry Core;
  `python scripts/test_wheels.py --audit-only` and
  `python scripts/test_wheels.py --current-environment`: **passed**, including
  installed-wheel tabular source compilation/execution. This reuses installed
  third-party dependencies; it is not the isolated release-install gate.
- ABI and capability generators `--check`, syntax JSON validation and builtin
  manifest parity, Prettier checks and `git diff --check`: **passed**. Prettier
  reports the new native include as ignored, preventing the original corruption.

The initial regression runs exposed obsolete negative expectations for now-valid
nullable builders/descriptors/fields and a parser diagnostic wording mismatch;
these were corrected and the relevant complete target sets rerun green. The
native include compilation failure was fixed rather than skipped.

Not run: full repository CI, Quarto build, Python 3.10–3.13, non-Linux
toolchains, LeakSanitizer detection, or an isolated fresh dependency
installation. The remaining M4 implementation gaps are listed above; none has
been marked done based on this verification.

### M4 continuation — logical scalar and nested value paths (2026-09-21)

M4 remains **PARTIAL**, not complete. This continuation implements the major
non-primitive value paths; it does not redefine the milestone exit criteria or
count schema descriptors as executable extension values.

| Subitem                                                                       | Status      | Implementation / remaining boundary                                                                                                                     |
| ----------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Typed owned logical scalars                                                   | **DONE**    | `scalar[T]`, nullable scalar owners, checked text/byte constructors, equality, owned child/byte/string results                                          |
| Variable-width, temporal, decimal and interval values                         | **DONE**    | Native construction and array/chunk/table storage; exact decimal scale/precision and UTF-8 validation                                                   |
| Recursive list/view, struct, map, dictionary, union and run-end values        | **DONE**    | Typed scalar children, recursive arrays/builders, independent child owners and deep copies; no arbitrary kernel dispatch                                |
| Optional managed class values                                                 | **DONE**    | Null-pointer niche with class-specific pointer type, copy/return retains and replacement cleanup                                                        |
| Rank-one numeric source buffer construction                                   | **DONE**    | `array_from_buffer(tensor)` and IRx typed buffer views copy independently, validate rank/dtype/overflow and handle offsets/negative strides/empty views |
| Explicit noncontiguous row selection                                          | **DONE**    | `take_rows` accepts nonnullable `array[i64]`, supports reorder/repetition/empty results and preserves zero-column row counts                            |
| External C Data adoption and explicit validity-buffer source constructors     | **DONE**    | Completed in C2: owned C Data carriers and checked packed-buffer/bitmap construction                                                                    |
| Nullable C strings, general language collections and managed by-value structs | **PARTIAL** | C4/C6 add owned nullable strings and legacy DataFrame/Series owners; arbitrary language aggregates and recursive by-value drops remain rejected         |
| Extension value codecs and legacy DataFrame/Series adapters                   | **DONE**    | Completed in C1/C3: native registered/opaque storage codecs and explicit retaining adapters                                                             |

**Implementation contracts at this slice's landing.** ABI **1.5.0**, Array
feature **1.5.0**, DataFrame feature **1.2.0**; the closure below advances the
ABI and Array feature to **1.6.0**. Existing ABI signatures and the 1.0
compatibility baseline are preserved. New objects stay behind opaque handles.
Semantic sidecars contain normalized scalar arguments and array descriptors;
LLVM does not infer schemas or select logical conversions. Native operations
clear outputs first and publish only after successful validation. Nested field
metadata participates in native type equality. Union/run-end null counts inspect
logical children; dictionary validity follows its index, matching scalar
extraction. The current source failure policy remains fatal diagnostics; native
builders remain available for retry after failures.

**Decisions and assumptions (each with the top three alternatives):**

1. **Use built-in `scalar[T]` shared owners for non-primitive Arrow values.**
   Numeric language scalars keep their existing LLVM representation. Arrow
   strings are not silently interchangeable with nullable C-string `str`.
   Alternatives: (1) inline every Arrow layout in LLVM (ABI/lifetime coupling),
   (2) separate language classes for every logical family (duplicated rules),
   (3) standard-library-only wrappers (conflicts with the core-language design).
2. **Use typed textual atomic constructors, with exact decimal validation, and
   length-delimited byte-array constructors for string/binary data.** Nested
   inputs are typed scalar/array values, not serialized strings. Literal
   C-string inputs with embedded NUL are rejected; dynamic inputs retain the
   existing NUL-terminated `str` semantics. `scalar_bytes` preserves arbitrary
   bytes. Alternatives: (1) new temporal/decimal literal grammar, (2) generic
   Compute casts (premature M6 dependency), (3) Python/PyArrow construction (not
   native).
3. **Make generic builders failure-atomic by retaining immutable scalar inputs
   and materializing a separate snapshot before clearing state.** Primitive
   builders keep their optimized existing path. Generic finishing currently
   allocates one-element arrays and concatenates them; it is correct but not a
   high-throughput nested-builder implementation. Alternatives: (1) specialized
   transactional builder per family, (2) cloning mutable Arrow builders before
   finish, (3) destructive finish with no retry guarantee. Prefer specialization
   later if profiling justifies it.
4. **Deep copies detach nested/dictionary buffers; views retain immutable
   storage.** Concatenation alone is insufficient for a dictionary deep copy, so
   generic copies recursively use Arrow's CPU memory-manager copy path.
   Alternatives: (1) shallow copy renamed as clone, (2) IPC serialization, (3)
   handwritten recursive buffer copying. The chosen path uses the existing
   runtime memory pool and avoids a serialization dependency.
5. **Copy rank-one numeric buffers rather than guessing safe external storage
   adoption.** Input allocation lifetime is borrowed for the call only. The
   low-level view ABI assumes readable storage; it has no allocation-size field.
   Bitmap-bearing, Boolean-packed and half-float views are rejected.
   Alternatives: (1) owner-aware zero-copy adoption with explicit extents, (2)
   unsafe raw-pointer constructors, (3) convert via Python. Extent-aware
   ownership envelopes are the preferred future external C Data design.
6. **`take_rows` is a focused structural primitive, not a query engine.** Table
   selections share per-row chunk slices; batch selections materialize columns.
   It preserves ordering, repetition, metadata and empty/zero-column shapes.
   Alternatives: (1) Arrow Compute Take after the M6 registry exists, (2)
   implicit row iteration, (3) always combine/materialize tables first.
7. **Keep nullable managed class pointers typed and reuse resolved ownership.**
   This permits nullable aggregate owners without pretending by-value structs
   have recursive copy/drop semantics. Mutable field flow facts stay
   conservative. Alternatives: (1) box all nullable payloads, (2) add a validity
   aggregate around every pointer, (3) permit unmanaged nullable structs and
   leak nested owners.
8. **Do not erase extension logical semantics or alias legacy DataFrames.**
   Extension value types, including nested occurrences, remain rejected until
   storage/codec execution is registered. Legacy adapters remain explicitly
   pending rather than silently expanding old numeric-only operators.
   Alternatives: (1) registered extension codecs plus explicit typed adapters
   (preferred next work), (2) erase extension metadata and make DataFrame a
   Table alias (behavior loss), (3) duplicate complete implementations (future
   drift).

#### Verification for the logical-value continuation

Executed on Linux, Python **3.14**, with PyArrow **24.0.0**:

- `pytest -q packages/astx/tests`: **544 passed**.
- Final focused IRx suite: **447 passed**. Exact targets under
  `packages/irx/tests/`: `analysis/`, `test_logical_scalar_runtime.py`,
  `test_array_value_runtime.py`, `test_chunked_value_runtime.py`,
  `test_tabular_runtime.py`, `test_nullable_runtime.py`,
  `test_arrow_abi_manifest.py`, `test_arrow_abi_conformance.py`,
  `test_arrow_runtime.py::test_arrow_runtime_reports_stable_abi_and_feature_versions`,
  and `test_arrow_capability_matrix.py`. Includes strict nested metadata,
  dictionary deep-copy buffer independence, logical builder failure atomicity,
  buffer offsets/negative strides/overflow and row-selection bounds/type/null
  rejection with cleared outputs and reusable input owners.
- Arx regression targets under `packages/arx/tests/python/`: **712 passed**.
  Exact targets: `test_logical_scalar_values.py`, `test_nullable_syntax.py`,
  `test_nullable_operations.py`, `test_nullable_owners.py`,
  `test_nullable_refinement_casts.py`, `test_nullable_fields.py`,
  `test_array_values.py`, `test_chunked_values.py`, `test_tabular_values.py`,
  `test_codegen_ast_output.py`, `test_parser*.py`, `test_lexer*.py`, and
  `test_dataframe.py`. After strengthening the examples, the complete
  `test_logical_scalar_values.py` and the new
  `test_codegen_ast_output.py::test_repeated_unicode_literals_have_unique_llvm_globals`
  regression were rerun: **15 passed** (overlaps the broad regression run).
- `arx test packages/arx/tests/arx/test_logical_values.x`: **1 passed**.
- `python scripts/check_arrow_ownership_sanitizers.py --skip-leak-detection`:
  **15 generated ownership programs plus the native harness passed** under
  AddressSanitizer/UndefinedBehaviorSanitizer. Failure-path programs produced
  their expected runtime diagnostics. Leak detection was explicitly disabled;
  this is not a LeakSanitizer pass. Subsequent native edits were C++ formatting
  only; native regressions and installed-wheel execution were rerun afterward.
- `mypy --config-file packages/<package>/pyproject.toml packages/<package>/src`
  passed for **all six packages**: ASTx (59 source files), IRx (160), Arx (31),
  ArxPy (5), ArxJIT (10), AIX (21).
- Rebuilt ASTx/IRx/Arx sdists and wheels using
  `poetry.core.masonry.api.build_sdist` / `build_wheel` in each package.
  `python scripts/test_wheels.py --audit-only` and
  `python scripts/test_wheels.py --current-environment`: **passed**. The latter
  installs all six wheels into a clean target, uses existing third-party
  dependencies, and executes the added logical-scalar/table/buffer smoke program
  alongside the existing programs. This is not a fresh dependency resolution
  test.
- Ruff lint and format checks passed for changed Python files with the owning
  package configurations (root configuration for ASTx and scripts). `douki sync`
  is idempotent: **0 updated, 41 unchanged**, followed by **0 updated, 1
  unchanged** for the added native row-selection tests.
- `makim arx.check-syntax`, `python scripts/gen_arrow_abi.py --check`,
  `python scripts/gen_arrow_capability_matrix.py --check`, Prettier checks and
  `git diff --check`: **passed**. The new native include is ignored by Prettier;
  its formatting uses ClangFormat instead.

The first broader IRx run exposed five stale expectations: formerly unsupported
string arrays, the incremented ABI/feature versions, native-symbol discovery
missing the new include, and a future-consumer version that was no longer in the
future. These were corrected; the complete affected target set was rerun. The
repeated-string LLVM global collision was fixed with module-unique names and a
translate/LLVM-verify regression rather than a frontend workaround. Adding the
row-selection regressions shifted evidence line anchors in the generated
capability matrix; its freshness check failed once, the matrix was regenerated,
and the complete 447-test target set above then passed.

Not run: full repository CI, Quarto build, Python 3.10–3.13, non-Linux
toolchains, leak detection, or an isolated fresh dependency installation. M4
remains **PARTIAL** with the explicit implementation gaps listed above.

### M2–M4 closure continuation (2026-09-21)

Implementation order (statuses updated as each slice is verified):

| Slice | Milestone items    | Status      | Scope                                                                                             |
| ----- | ------------------ | ----------- | ------------------------------------------------------------------------------------------------- |
| C1    | M4-004             | **DONE**    | Explicit DataFrame/Series adapters and logical DataFrame literals                                 |
| C2    | M4-003             | **DONE**    | Safe C Data owner boundary and explicit packed-buffer construction                                |
| C3    | M3-006, M4-004     | **DONE**    | Registered extension storage/value execution                                                      |
| C4    | M2-013, M4-002     | **PARTIAL** | Nullable string/collection and aggregate lifecycle policies                                       |
| C5    | M2-009/010, M3-006 | **PARTIAL** | Allocator-failure and ownership verification; 19-program ASan/UBSan passed, LSan ptrace-blocked   |
| C6    | M4-002             | **DONE**    | Nullable DataFrame/Series owners and runtime-schema declaration contexts; 37 focused tests passed |

These slices do not mark the earlier milestones complete before their exit
criteria and verification gates are satisfied.

C1 verification: DataFrame/adapter frontend, analysis, translate and native
execution regressions: **22 passed**. DataFrame literal lowering now consumes
the same resolved typed-table plan rather than rebuilding schema facts. Dynamic
DataFrame values cannot claim static columns without checked projection.

C1 decision: conversions retain independent owners; legacy DataFrame erases
static schema facts, not runtime metadata. Alternatives: (1) extend the legacy
type with a second schema model; (2) alias DataFrame to Table; (3) silently
discard metadata during conversion. Explicit checked projection is preferred.

C2 implementation: owned `c_data` carriers bridge checked arrays and native
producer callbacks. `array_from_buffers` validates packed/fixed-width extents;
`array_with_validity` supports every executable logical array without ever
reviving an existing null. Native interchange/extent tests: **6 passed**; source
checks passed in the ABI regression run. The stale C ABI version expectations
were corrected and their targeted rerun passed. C Data producers must provide
readable standard-compliant storage; source programs never manufacture or
dereference raw Arrow pointers.

C2 decision: import moves both callbacks after preflight and owner reservation;
failures before that point preserve both producer callbacks, later failures
consume both exactly once. Alternatives: (1) deep-copy only imports; (2) opaque
IPC serialization; (3) raw address casts in Arx. Independent C Data owners
retain field metadata; conversion to array values carries datatype/validity
rather than a top-level field name. Packed buffer constructors copy bounded
storage.

C3 verification: native extension/interchange tests **16 passed**; the pure-Arx
extension example passed. Registered codecs retain their identity and
validation; unknown non-reserved extensions use an opaque storage codec. Tests
include metadata mismatch, binary metadata, storage-type mismatch, parent
release, callback-consumption failures and allocator rollback. Additional
canonical extension coverage and broad regressions passed as recorded below.

C3 decision: native storage execution is independent of domain-specific Compute.
Alternatives: (1) preserve-only unknown extensions; (2) erase extensions to
their storage type; (3) require Python callbacks for every extension. Native
codecs avoid a Python execution dependency; unknown reserved `arrow.*` names
fail closed.

C4 verified string slice: **61 focused regressions passed**, followed by **3
nullable-string/accounting tests passed**. Local and instance-field `str` values
own independently cloned storage; `str | none` uses the null-pointer niche and
keeps empty text distinct from absence. Allocation accounting covers normal
cross-call execution and 32 failpoint positions inside one generated function.
It does **not** establish cross-frame fatal unwinding: an exploratory cross-call
OOM sweep reproduced the already tracked M2-015 caller-owner gap.

C4 decision: add an explicit COPYABLE ownership capability for immutable
strings, not a fictional pointer retain. Alternatives: (1) refcounted string
headers with a changed C-string ABI; (2) borrow-checker-only string lifetimes;
(3) require manual cloning everywhere. Static strings remain available at
unmanaged boundaries; nullable collections and managed by-value aggregates
remain pending.

C5 gate: LeakSanitizer was retried and failed before the generated programs with
its explicit ptrace incompatibility (exit 23). This is a **blocked verification
gate**, not a pass. ASan/UBSan without leak detection passed all 19 generated
programs and the native harness. General operation-wide allocator sweeps,
cyclic/static aggregate policies and cross-frame fatal cleanup must not be
marked complete on the strength of the new bounded regressions.

### Closure verification and remaining work

- The serial Arx regression set passed **727 tests**. Exact targets:
  `test_logical_scalar_values.py`, `test_nullable*.py`, `test_array_values.py`,
  `test_chunked_values.py`, `test_tabular_values.py`,
  `test_codegen_ast_output.py`, `test_parser*.py`, `test_lexer*.py`,
  `test_dataframe*.py`, `test_columnar_interchange.py`, and
  `test_extension_values.py` under `packages/arx/tests/python/`.
- IRx analysis, nullable runtime and extension/interchange targets passed **353
  tests**. Generator/extension/interchange regressions then passed **35 tests**
  after fixing extension logical validity over run-end storage. These sets
  overlap; do not add their counts as unique tests.
- The new generator checks cover both absent and present nullable string
  captures. Captures guard null before cloning/retaining; extension scalar
  extraction and null counts consult storage validity rather than assume a
  parent bitmap. Additional chunk/mask assertions passed in the broad IRx run.
- Strict mypy passed for all six packages (ASTx 59, IRx 162, Arx 31, ArxPy 5,
  ArxJIT 10, AIX 21 source files); IRx was rerun after the generator fix.
- ASTx/IRx/Arx sdists and wheels were rebuilt and the artifact audit passed.
  Installed-wheel execution passed using
  `scripts/test_wheels.py --current-environment`, including all four new
  examples. This uses existing third-party dependencies, not fresh dependency
  resolution. The concurrent broad test/sanitizer attempts were interrupted
  under memory pressure; their partial dots are **not** successful test reports.

M4 is still **PARTIAL**. Remaining implementation scope is not an environment
blocker: general nullable language collections/aggregates, managed by-value
struct retain/drop, cyclic class ownership and static-managed lifetime policy,
cross-frame fatal unwinding, and the remaining native/legacy-IPC allocation
sweeps. LSan, separately, remains blocked by this sandbox's ptrace restriction.
M4-003 and M4-004 are complete slices, not completion of M4-002 or Gate B.

Additional extension assumption: opaque codecs are registered by name in Arrow's
process-wide registry; existing codecs and concurrent registration winners are
honored. This is not a per-session registry or automatic domain-codec upgrade.
Alternatives: (1) require explicit codec registration and preserve unknowns
only; (2) implement an import-scoped registry/bridge; (3) require host
callbacks.

Unmanaged language list/tuple storage does not gain implicit string destruction.
Owned/borrowed dynamic strings are rejected at insertion/construction until
recursive element drop exists; static literals remain valid. This avoids
dangling pointers when newly owned local or class strings escape into an
unmanaged aggregate. Alternatives: (1) recursive item retain/drop functions; (2)
explicit lifetime-checked borrows; (3) copy strings into an aggregate-owned
arena. The current conservative boundary is not completion of M4-002.

Final broad IRx run: **732 passed, 1 failed** across `analysis/`,
`test_logical_scalar_runtime.py`, `test_array_value_runtime.py`,
`test_chunked_value_runtime.py`, `test_tabular_runtime.py`,
`test_nullable_runtime.py`, `test_arrow_abi_manifest.py`,
`test_arrow_abi_conformance.py`, `test_descriptor_execution.py`,
`test_schema_interop.py`, `test_arrow_runtime.py`, `test_string.py`,
`test_aggregate_ownership.py`, `test_dataframe.py`, `test_extension_values.py`,
`test_interchange_values.py`, and `test_generators.py`. The only failure was the
C harness still asserting ABI minor 5 and using 1.6 as a future requirement;
these expectations were corrected to minor 6/future 1.7; the targeted
`test_arrow_runtime_reports_stable_abi_and_feature_versions` rerun passed **1
test**. The full 733-test set was not rerun after that expectation fix. The
broad run verifies all seven canonical extension storage families, opaque binary
metadata, run-end extension nulls, chunk extraction and masking.

Follow-up checks after the unmanaged-string guard and unique default-string LLVM
global fix: **18 IRx aggregate/list tests passed** and **10 Arx
nullable-string/adapter tests passed**. The latter includes the new negative
legacy scalar-nullability check and same-named default locals in two functions.

ASTx schema, schema-expression, scalar, tabular, nullable and array modeling
targets passed **68 tests**. Ruff checks/formatting passed for all changed
Python files; Douki was idempotent (**0 updated, 56 unchanged** before C6).

C6 decision: optional legacy DataFrame/Series values reuse their existing
immutable table/chunked-array owners and reserved null-pointer niche. Runtime
DataFrame schemas are no longer parameter-only: locals, returns and instance
fields have the same safe opaque representation. Nullable Series element
annotations and the ASTx `nullable` flag compare using one canonical column
storage contract; owner absence remains separate from element nullability.
Alternatives: (1) require conversion to nullable table/chunked_array everywhere;
(2) add boxed nullable legacy wrappers with extra allocation; (3) replace legacy
types with public aliases, losing their distinct surface contract. General
language lists/tuples/structs are not opaque pointers and still require separate
aggregate validity and recursive retain/drop; they are not enabled by this
change.

C6 focused verification: **37 passed** across the Arx DataFrame/adapters tests
and IRx analysis DataFrame/ownership tests. Coverage includes absent/default
owners, present empty DataFrames, borrowed returns, copies after parent field
replacement, self-assignment, class destruction, flow refinement, null unwrap
failure and rejection of dynamic-to-static schema claims. General collection and
by-value aggregate work remains open rather than treated as an environment
blocker.

#### Final closure verification after C6

- **944 tests passed:** `packages/irx/tests/analysis/`, Arx
  `test_parser*.py`/`test_lexer*.py`, and the six ASTx modeling files listed
  above. This overlaps earlier reported sets; counts are not additive.
- **20 tests passed:** `test_arrow_capability_matrix.py` and
  `test_arrow_abi_manifest.py`. The inventory now classifies executable
  extension storage as core/array rather than preserve-only. Its validator
  permits transitional classifications to become empty without inventing a
  placeholder module, while still validating every entry's classification.
- The updated `dataframe_adapters.x` program passed instrumented ASan/UBSan
  execution after C6. This supplements the earlier full 19-program/native
  harness pass. An explicit `clang++` override failed native compilation in this
  environment; the rerun using the repository's default `c++` compiler
  succeeded. Leak detection remained disabled; the separate LSan retry was
  ptrace-blocked, not passed.
- Strict `mypy src` passed again in all six packages. Owning-config Ruff
  check/format and idempotent Douki checks passed for changed Python files.
- ASTx/IRx/Arx sdists and wheels were rebuilt after C6;
  `python scripts/test_wheels.py --current-environment` passed the artifact
  audit and installed-wheel compilation/execution, including the updated
  optional DataFrame/Series example and the other three new source examples.
- ABI/capability generator freshness, `makim arx.check-syntax`, and
  `git diff --check` passed. Markdown/JSON formatting was checked with the
  repository's cached Prettier version.

Not run: full repository CI, Quarto documentation build, Python 3.10–3.13,
non-Linux verification, or isolated fresh dependency resolution. **This is not
completion of M4 or all previous milestones**: the remaining implementation and
verification tasks above stay PARTIAL rather than being hidden by the new
passing slices.

### 2026-09-22 — Remaining aggregate ownership work

| Slice | Milestones     | Status   | Scope                                                                                           |
| ----- | -------------- | -------- | ----------------------------------------------------------------------------------------------- |
| C7    | M4-002, M2-006 | **DONE** | Nullable by-value list and tensor/buffer-view owners with explicit validity and payload cleanup |

C7 assumption: nullable aggregates cannot use the opaque-pointer null niche. Use
a validity bit plus a payload and carry aggregate cleanup shape in semantic
ownership metadata. Unique lists remain affine; shared tensor/buffer views
retain independent owners. Alternatives: (1) heap-box all nullable aggregates;
(2) change all collection ABIs to opaque handles; (3) add a borrow-checker-only
representation. Existing nested-element and by-value struct destruction limits
remain explicit until their own lifecycle implementation is verified.

C7 implementation decisions:

- Aggregate validity is explicit even when a list has no backing allocation.
  Semantic ownership records carry the nullable cleanup shape through moves,
  class fields and suspended frames; payload extraction clears that wrapper
  shape. Copies of shared tensor views retain only present payloads.
- Appending to a proven-present list changes its contents, not the owner or its
  validity. Replacement still invalidates the proof. Loop proof invalidation
  remains conservative; recheck validity within a loop body when needed.
- Refined tensor single-index expressions are resolved to existing ASTx tensor
  indexing in IRx analysis. The declared shape proves rank/extents; lowering
  reads actual runtime strides and never invents a contiguous layout.
- Failed list growth and indexing clean the current generated frame before
  reporting structured `ARX-RUNTIME-LIST-*` diagnostics. IRx comprehensions
  register partial output ownership before the first allocation, including
  outputs that transfer ownership on successful construction. This does not
  claim Arx source comprehension syntax or cross-frame exception unwinding.

For cleanup, the top three alternatives are (1) propagate statuses through a new
generated-function ABI, enabling cross-frame cleanup; (2) register runtime
cleanup frames and unwind them on fatal errors; (3) use a process-wide arena
with bulk teardown. This slice uses existing local cleanup metadata to avoid an
unverified calling-convention change; cross-frame cleanup remains pending.

C7 preserves the existing tensor indexing policy: static out-of-bounds indices
are rejected, but dynamic tensor bounds checks remain M5 work. Owner validity is
not a proof that a runtime index is in bounds. No Arrow ABI or C++ object layout
is changed by the language-owned nullable aggregate representation.

#### C7 verification — 2026-09-22

- **30 passed**: Arx nullable collection and translate-path regressions plus the
  IRx partial-comprehension allocation-accounting regression. Covers empty
  versus absent lists, borrowed tensor returns and copies, field replacement,
  unique-list copy rejection, guarded indexing/append, absent unwrap, scope
  cleanup, and current-frame failure cleanup. GNU wrapping accounts for
  `malloc`, `realloc` and `free`: four class/list allocation-failure positions
  and six partial-comprehension allocation-failure positions return to zero live
  owners. Comprehension tests construct ASTx directly, not unsupported Arx
  source syntax.
- **899 passed**: IRx analysis, Arx parser/lexer, Arrow capability matrix and
  ABI manifest tests, after the tensor-shape refinement fix.
- **275 passed**: IRx nullable runtime, dynamic/list-struct/literal-list,
  collection methods, aggregate ownership, generators, strings, buffer indexing,
  buffer views, tensors, iterables and list-failure cleanup, plus all Arx
  `test_nullable*.py` tests. The first broad run had three stale LLVM-text
  expectations for native fail-fast calls/whole-function destroy counts; updated
  tests check cleanup-aware errors and distinguish fatal blocks from
  moved-return paths. The complete set was rerun successfully.
- Strict `mypy src` passed in all six packages. Changed Python files passed
  owning-config Ruff checks/formatting; Douki was idempotent (72 unchanged,
  followed by the three list-test files unchanged). ABI/capability generator
  freshness, `makim arx.check-syntax`, Markdown/JSON formatting and
  `git diff --check` passed. Test counts overlap and are not additive.
- ASTx, IRx and Arx wheel/sdist builds passed. The native ownership harness and
  **all 20 generated programs passed ASan/UBSan** using `c++` and `clang`,
  including nullable collections. Leak detection was explicitly disabled; the
  previously recorded local ptrace/LSan limitation is not a passing LSan result.
  `python scripts/test_wheels.py --current-environment` also passed the artifact
  audit and installed-wheel smoke, including nullable collections. This uses
  current installed dependencies, not fresh dependency resolution.

- **1,494 passed:** the complete `packages/irx/tests` suite, rerun after all C7
  implementation changes and the nullable diagnostic wording update (**686.89
  seconds**). This includes the previously corrected ABI-version harness, all
  current runtime/interop tests and the expanded list cleanup tests. It
  supersedes the earlier incomplete 733-test runtime verification for the
  current working tree, without substituting for unimplemented lifecycle
  policies or the remaining LSan/fault-sweep gates.

Remaining work is not marked complete by C7:

1. **M4-002:** nullable nested language collection elements, recursive managed
   aggregates and by-value struct destruction.
2. **M2-013:** supported cyclic-class and static-managed lifetime policies.
3. **M2 / M3 Gate B:** cross-frame fatal cleanup, complete allocator-failure
   sweeps and an actual passing LSan run.

Full repository CI, the Quarto build, Python 3.10–3.13 and non-Linux execution
have not been run for C7. M4 and the earlier partial milestones remain PARTIAL;
this is a completed ownership slice, not completion of every requested item.
