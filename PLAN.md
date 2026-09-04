# Native Apache Arrow C++ Support Plan

NOTE: DON'T TRACK THIS BY GIT, IT SHOULD BE KEPT IGNORED BY .gitignore

**Status:** active implementation roadmap

**Repository snapshot:** 2026-09-03

**Target:** make Apache Arrow C++ a complete, native, first-class data runtime
for the Arx language.

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

| Milestone                               | Status          | Gate or dependency |
| --------------------------------------- | --------------- | ------------------ |
| M0 — contracts and design decisions     | **DONE**        | None               |
| M1 — one native Arrow runtime and ABI   | **IN PROGRESS** | M0, Gate A         |
| M2 — semantic ownership and cleanup     | **NOT STARTED** | M1, Gates A-B      |
| M3 — complete logical types and schemas | **NOT STARTED** | M1-M2, Gate B      |
| M4 — first-class containers             | **NOT STARTED** | M1-M3, Gate B      |
| M5 — tensors and multidimensional data  | **NOT STARTED** | M1-M4              |
| M6 — compute                            | **NOT STARTED** | M1-M4, Gate C      |
| M7 — streaming, IPC, and file formats   | **NOT STARTED** | M1-M4, Gate D      |
| M8 — datasets and Acero                 | **NOT STARTED** | M6-M7, Gate D      |
| M9 — packaging and distribution         | **NOT STARTED** | M0-M8, Gate E      |
| M10 — hardening and support declaration | **NOT STARTED** | M0-M9, Gate E      |

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

| Date       | Item   | Transition                 | Evidence                                                       |
| ---------- | ------ | -------------------------- | -------------------------------------------------------------- |
| 2026-09-03 | M0-001 | NOT STARTED -> DONE        | Plan is no longer ignored and now carries tracked states.      |
| 2026-09-03 | M0-002 | NOT STARTED -> IN PROGRESS | Capability manifest and generated matrix started.              |
| 2026-09-03 | M0-002 | IN PROGRESS -> DONE        | `makim irx.check-arrow-capabilities`; two tests pass.          |
| 2026-09-03 | M0-003 | NOT STARTED -> IN PROGRESS | Validated foundation readiness rows started.                   |
| 2026-09-03 | M0-003 | IN PROGRESS -> DONE        | 18 owners, states, test targets, and blockers validate.        |
| 2026-09-03 | M0-004 | NOT STARTED -> DONE        | Builtin-first, unqualified naming is fixed in Section 2.1.     |
| 2026-09-03 | M0-005 | NOT STARTED -> IN PROGRESS | Public operation placement catalog started.                    |
| 2026-09-03 | M0-005 | IN PROGRESS -> DONE        | 52 families cover every capability and approved layer.         |
| 2026-09-03 | M0-006 | NOT STARTED -> IN PROGRESS | Existing `T \| none` syntax selected for the null contract.    |
| 2026-09-03 | M0-006 | IN PROGRESS -> DONE        | Type, flow, operator, container, and ABI rules recorded.       |
| 2026-09-03 | M0-007 | NOT STARTED -> IN PROGRESS | Static and runtime schema contract started.                    |
| 2026-09-03 | M0-007 | IN PROGRESS -> DONE        | Static identity and checked dynamic access rules recorded.     |
| 2026-09-03 | M0-008 | NOT STARTED -> IN PROGRESS | Native handle ownership and value semantics started.           |
| 2026-09-03 | M0-008 | IN PROGRESS -> DONE        | Share, move, borrow, view, and cleanup rules recorded.         |
| 2026-09-03 | M0-009 | NOT STARTED -> IN PROGRESS | Unified status and language error policy started.              |
| 2026-09-03 | M0-009 | IN PROGRESS -> DONE        | ABI status and recoverable/fatal policies recorded.            |
| 2026-09-03 | M0-010 | NOT STARTED -> IN PROGRESS | Native runtime wheel strategy started.                         |
| 2026-09-03 | M0-010 | IN PROGRESS -> DONE        | Dedicated core and optional runtime artifacts fixed.           |
| 2026-09-03 | M0-011 | NOT STARTED -> IN PROGRESS | Unified C ABI v1 compatibility policy started.                 |
| 2026-09-03 | M0-011 | IN PROGRESS -> DONE        | ABI 1.0.0 layout and compatibility rules recorded.             |
| 2026-09-03 | M0-012 | NOT STARTED -> IN PROGRESS | Local Arrow 24 module tree classification started.             |
| 2026-09-03 | M0-012 | IN PROGRESS -> DONE        | 29 groups cover all seven declared product scopes.             |
| 2026-09-03 | M0     | IN PROGRESS -> DONE        | All 12 contract items and 11 focused checks complete.          |
| 2026-09-03 | M1-001 | NOT STARTED -> IN PROGRESS | Packed Arrow ABI version query implementation started.         |
| 2026-09-03 | M1-001 | IN PROGRESS -> DONE        | C harness and ctypes verify the native ABI 1.0.0 query.        |
| 2026-09-03 | M1-002 | NOT STARTED -> IN PROGRESS | Stable status categories and error codes started.              |
| 2026-09-03 | M1-002 | IN PROGRESS -> DONE        | Native ABI and 44 runtime tests use stable Arx statuses.       |
| 2026-09-03 | M1-003 | NOT STARTED -> IN PROGRESS | Owned, thread-safe error detail implementation started.        |
| 2026-09-03 | M1-003 | IN PROGRESS -> DONE        | Owned snapshots pass isolation, lifetime, and 64 regressions.  |
| 2026-09-03 | M1-004 | NOT STARTED -> IN PROGRESS | Unified opaque-handle ownership implementation started.        |
| 2026-09-03 | M1-004 | IN PROGRESS -> DONE        | ABI manifest and 50 Arrow ABI/runtime tests pass.              |
| 2026-09-03 | M1-005 | NOT STARTED -> IN PROGRESS | Cross-language ABI declaration generation started.             |
| 2026-09-03 | M1-005 | IN PROGRESS -> DONE        | 67 generated symbols have C/Python/LLVM parity; 55 tests pass. |

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

| Foundation                              | Current baseline                                                                              | Required completion                                                                                                                     |
| --------------------------------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Scalar numerics and Boolean             | Core signed/unsigned integers, floats, casts, and Boolean rules exist                         | Define exact Arrow cast, overflow, comparison, NaN, and non-finite behavior                                                             |
| Null values                             | `none` and finite unions exist; Arrow arrays expose validity metadata                         | Define first-class nullable scalar semantics, validity propagation, equality, ordering, casts, and pattern/branch behavior              |
| Strings and bytes                       | UTF-8 strings exist; Arrow RecordBatch supports UTF-8 internally                              | Add owned/borrowed binary values, large offsets, Unicode conversion, view lifetimes, and zero-copy rules                                |
| Decimal values                          | ASTx reserves decimal data-type kinds                                                         | Add Arx literals/types, precision and scale checking, 32/64/128/256-bit representation, arithmetic, casts, and ABI rules                |
| Temporal values                         | Date, time, timestamp, and datetime types/literals exist                                      | Add Arrow units, duration/interval types, timezone metadata, range checking, and conversion policy                                      |
| Parametric and structural types         | Templates, tensors, DataFrames, structs, and unions provide partial foundations               | Support recursive schema parameters, fixed sizes, dictionary/index types, union codes, field nullability, and canonical equality        |
| Compile-time values                     | Tensor dimensions and DataFrame fields carry selected static metadata                         | Provide checked type parameters for dimensions, decimal precision/scale, time units, fixed sizes, and schema fields                     |
| Ownership and destruction               | Strings and scalar dynamic lists have semantic ownership; Arrow handles expose retain/release | Generalize ownership to native handles, views, fields, calls, returns, temporaries, errors, classes, and generators                     |
| Buffer and bitmap model                 | `irx_buffer_view` models data, owner, dtype, shape, strides, offset, and flags                | Add checked dynamic bounds, validity bitmap operations, variable-width offsets, alignment, endianness, and large-buffer overflow checks |
| Collection sizes and indices            | Existing APIs mix static metadata and integer result widths                                   | Standardize Arrow lengths, row counts, offsets, and indices on checked `i64` semantics and narrow only explicitly                       |
| Methods, overloads, and intrinsics      | Typed calls and semantic sidecars exist                                                       | Add one typed builtin/intrinsic registry for container methods and kernels; lowering consumes only resolved entries                     |
| Error handling                          | Structured compile/link/runtime diagnostics and integer native statuses exist                 | Define one recoverable/fatal operation contract, error propagation, cleanup during failure, and stable user-visible categories          |
| Iteration and streaming                 | List iteration and initial generators exist                                                   | Define Array/Series iteration, batch-stream EOF, early close, cancellation, backpressure, and deterministic stream cleanup              |
| Classes and aggregate storage           | Struct/class support exists; general class destruction is incomplete                          | Add field destruction/move rules before Arrow owners may be stored in classes or other owning aggregates                                |
| FFI and opaque handles                  | C externs and opaque handles exist                                                            | Add nullability, ownership annotations, C Data/C Stream contracts, callbacks only where required, and ABI conformance checks            |
| Modules, builtins, and standard library | Ambient builtins, bundled builtin modules, and a small stdlib exist                           | Define stable intrinsic registration and public facades without exposing an `arrow` import or internal module paths                     |
| Execution context                       | Runtime features can add native artifacts and linker flags                                    | Add memory pool, allocator, thread count, cancellation, resource limits, and optional device selection                                  |
| Native packaging                        | Runtime sources build on demand from Arrow/PyArrow metadata                                   | Provide matched headers/libraries, platform discovery, clean-wheel execution, and cross-platform CI                                     |

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

| ID     | Item                                                          | Status          | Evidence or blocker                       |
| ------ | ------------------------------------------------------------- | --------------- | ----------------------------------------- |
| M1-001 | Add the packed ABI 1.0.0 constants and version query          | **DONE**        | C harness and ctypes tests pass           |
| M1-002 | Define stable status categories and error codes               | **DONE**        | Native header/runtime; 44 tests pass      |
| M1-003 | Unify thread-safe error-detail retrieval                      | **DONE**        | Snapshot, lifetime, and thread tests pass |
| M1-004 | Define every opaque handle and its ownership operations       | **DONE**        | ABI manifest; 50 Arrow tests pass         |
| M1-005 | Generate C, Python, LLVM, and symbol declarations             | **DONE**        | 67-symbol generated ABI; 55 tests pass    |
| M1-006 | Add the versioned runtime-feature query                       | **DONE**        | 68-symbol ABI; 56 Arrow tests pass        |
| M1-007 | Delegate legacy `irx_rb_*` symbols through compatibility      | **DONE**        | 74-symbol ABI; 81 batch tests pass        |
| M1-008 | Enforce executable transitive runtime-feature dependencies    | **DONE**        | 17 registry tests; 978 IRx tests pass     |
| M1-009 | Split runtime artifacts and linking by activated capability   | **NOT STARTED** | Link-input and clean-build tests          |
| M1-010 | Add installed-header, layout, symbol, and version conformance | **NOT STARTED** | C11/C++20 and cross-version CI            |

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
has an independent contract version packed as `0xMMMMmmpp`; all five current
contracts are 1.0.0. The generator emits the IDs and versions into the installed
C header, Python ctypes metadata, LLVM metadata, and the native lookup table so
those surfaces cannot silently disagree.

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
translate-path test proves that a RecordBatch-backed extern activates `array`,
includes both native translation units, deduplicates the shared unified Arrow
runtime source, and emits the requested symbol. The runtime-feature suite passes
17 tests and the complete IRx suite passes 978 tests. ABI/capability generation,
strict type checking, lint, and the IRx package build also pass. ABI generation
now renders empty feature-symbol tuples canonically so its freshness check stays
idempotent with the repository formatter.

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
