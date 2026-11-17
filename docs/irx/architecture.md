# Architecture

IRx is organized as a small compiler pipeline with a deliberate boundary between
semantic meaning and backend-specific lowering. The goal is to keep the codebase
easy to extend without letting semantic rules slowly drift into code generation.

## Design Goals

The current architecture is shaped by a few practical goals:

- Keep parsing, semantic analysis, and code generation as distinct phases.
- Make semantic analysis the authority for meaning and program validity.
- Keep backend packages focused on emission, not interpretation.
- Preserve method-based multiple dispatch for visitor-driven lowering.
- Use package structure to communicate architecture instead of large utility
  modules or generic `helpers/` folders.

## Pipeline Overview

IRx currently follows this high-level flow:

`ASTx parser output -> semantic analysis -> resolved semantic sidecars -> backend code generation`

The parser produces raw ASTx nodes. Those nodes are still close to surface
syntax and may not yet have enough information for direct lowering. The
semantic-analysis phase walks that tree, resolves symbols and types, validates
program rules, and attaches a structured `node.semantic` sidecar to the nodes
that backend code needs.

By the time a backend starts lowering, it should not need to infer meaning from
raw syntax or re-run language validation from scratch.

## Semantic Analysis

The semantic-analysis package lives in `packages/irx/src/irx/analysis/` and is
intentionally independent from LLVM or `llvmlite`.

It is responsible for:

- symbol resolution
- lexical scope tracking
- mutability and assignment validation
- function and return validation
- loop-control legality such as `break` and `continue`
- expression typing and promotion policy
- operator normalization
- semantic flag normalization such as unsigned and fast-math intent
- diagnostics collection and semantic error reporting

The public entry points are:

- `irx.analysis.analyze(node)`
- `irx.analysis.analyze_module(module)`
- `irx.analysis.analyze_modules(root, resolver)`

These entry points return the same AST root after attaching semantic sidecars.
If semantic validation fails, analysis raises `SemanticError` before codegen
begins.

### Semantic Contract

The host-facing semantic boundary is now explicit in code through
`irx.analysis.get_semantic_contract()`. That contract names the stable semantic
phases, the `SemanticInfo` and `CompilationSession` metadata that must exist
before codegen, and the boundary between semantic, lowering, and linking/runtime
failures.

See [Semantic Contract](semantic-contract.md) for the concise contract summary.

### Static call visitors

Table I/O uses fixed, phase-owned Plum visitors. Ordinary symbol lookup selects
an explicitly trusted nominal operation; analysis produces a validated typed
call plan. LLVM lowering visits that plan, not the source function name. Unknown
operation/plan types fail at their responsible phase instead of falling through
to ordinary FFI. Small typed service interfaces preserve the analysis/lowering
boundary and existing checked native calls and resource cleanup.

The concrete analyzer and LLVM visitor construct their call visitors directly.
There is no provider discovery, configurable handler catalog, feature selection,
or per-builder handler replacement API. Ordinary visitor inheritance and mixins
compose supported behavior; compilation state stays with the analyzer/builder or
the per-call service bundle, not a shared mutable visitor catalog. Analysis
remains independent of LLVM and the Arx frontend. Importing analysis does not
activate or compile native code.

Separate compiler instances keep independent compilation state. Recursive visits
are supported; simultaneous use of one mutable analyzer/builder is not.

Typed call facts retain validation, dependency traversal, and invalidation on
reanalysis. The separate native runtime feature registry still owns native
symbol activation, artifacts, and linker dependencies; static visitor support
never activates all native dependencies eagerly. Source identity and semantic
bindings remain available to future source-debug emission without requiring
compiler-provider inspection or tracing infrastructure.

The shared visitor now has one typed rejecting fallback. Analysis explicitly
registers supported scalar literals and structural traversal; a `type_` field
does not make arbitrary syntax supported. Intentionally breaking pre-2.0
behavior: unknown nodes now produce semantic `S016` diagnostics instead of
receiving generic type metadata; bypassing analysis with a missing LLVM handler
produces internal lowering `L002`. No node-specific base rejection stubs remain.

### Why sidecars instead of a separate HIR?

For the current size of IRx, attaching explicit semantic sidecars to AST nodes
is the lightest approach that still creates a clean boundary. It gives codegen
resolved information without introducing a second full tree structure before it
is needed.

If the language grows to the point where a true HIR becomes useful, the current
phase split still leaves room for that evolution.

### Multi-Module Boundary

IRx now also supports a parser-agnostic multi-module path for imports.

The boundary is explicit:

- the host compiler parses source text into `astx.Module` objects
- the host compiler decides how an import specifier maps to a module
- IRx receives `ParsedModule` objects plus an `ImportResolver`
- IRx expands the reachable dependency graph, performs cross-module semantic
  analysis, and lowers the reachable graph into one LLVM module for the MVP

Import-from resolution remains symbol-first, but it also supports child-module
namespace sugar: `import stats from sciarx` may bind `sciarx.stats` as a local
module namespace when `sciarx` does not already expose an importable symbol
named `stats`.

IRx does not parse source text, search the filesystem, or implement package
discovery. Those responsibilities stay outside the library.

### Template Specialization Metadata

IRx also carries semantic-only template metadata for compile-time
specialization. The current scope is bounded template functions and methods.

Semantic analysis preserves:

- template parameters attached to callable definitions
- finite union bounds used as specialization domains
- unresolved template type variables inside generic signatures
- explicit template arguments attached to call sites
- stable specialization identities and generated concrete callables

During analysis, template bodies are validated over every admissible bound
substitution. Successful specializations are materialized as generated concrete
functions so backend lowering can continue to operate mostly on ordinary
non-template callables. That generated specialization set is treated as
per-analysis state and is cleared before rerunning semantic analysis on the same
AST module.

For v1, template methods lower only as direct concrete specializations. They do
not participate in class dispatch slots or virtual-style dispatch tables.

### Compilation Session

The multi-module path is centered on `CompilationSession` in
`packages/irx/src/irx/analysis/session.py`.

That session owns:

- the root parsed module and resolver callback
- the cache of reachable parsed modules
- the import dependency graph and stable load order
- cycle diagnostics
- per-module visible top-level bindings used for direct imports and module
  namespace aliases
- semantic-only module namespace values and namespace-member lookup metadata

Semantic identity for top-level functions and structs is module-aware. Backend
lowering consumes that semantic identity rather than raw source names, which is
what keeps same-named declarations in different modules from colliding in LLVM.

## Shared Visitor Foundation

IRx also has a shared visitor layer in `packages/irx/src/irx/base/visitors/`.

It currently provides:

- `BaseVisitorProtocol`: the minimal typing contract shared by visitor-style
  classes
- `BaseVisitor`: a concrete Plum-dispatch scaffold with one typed
  `NotImplementedError` fallback for unsupported nodes

This keeps typing and runtime behavior separate:

- protocols define what visitor-like objects must expose
- the concrete base class defines what happens for unsupported nodes

In practice:

- `SemanticAnalyzer` inherits `BaseVisitor`
- `BuilderVisitor` inherits `BaseVisitor`
- builder-specific protocols such as `builder.VisitorProtocol` extend
  `BaseVisitorProtocol`

## Builder Architecture

IRx now exposes a single builder package at `packages/irx/src/irx/builder/`. The
package path identifies the concrete LLVM builder, while the public classes
inside it use short generic names.

For example, `packages/irx/src/irx/builder` exposes:

- `Builder`
- `Visitor`
- `VisitorProtocol`
- optional `VisitorCore` as a module-private implementation class

This keeps the public API concise without reintroducing legacy class prefixes.

## Builder Package Layout

The LLVM backend is split into first-class modules instead of one monolithic
builder:

- `../packages/irx/src/irx/base/visitors/`: shared visitor protocol and runtime
  scaffold
- `backend.py`: public backend entry points
- `core.py`: shared mutable lowering state and backend lifecycle
- `protocols.py`: typing contract used by mixins and runtime features
- `types.py`, `casting.py`, `vector.py`, `strings.py`, `runtime/`: shared IR
  infrastructure
- `lowering/`: concern-grouped `visit(...)` overloads
- `../packages/irx/src/irx/buffer.py`: the canonical low-level buffer owner/view
  semantic substrate that Arx can target without exposing an array API

Foundational modules stay at the package root because they are architectural
components, not incidental helpers.

## Buffer/View Indexing

IRx treats first-class indexing as a low-level operation over the canonical
buffer/view descriptor in `packages/irx/src/irx/buffer.py`. It is the stable
memory/container path that Arx can target for element access such as `a[i]`,
`a[i, j]`, and the corresponding stores. It is not a NumPy-like array API and
does not define slicing, broadcasting, fancy indexing, masks, or shape
inference.

Indexed access has an explicit IRx node surface for reads and stores. Semantic
analysis validates the descriptor base, the number of indices, index scalar
types, mutability for stores, static bounds when descriptor shape and literal
indices make the answer provable, and the scalar element type used by lowering.
The MVP requires static descriptor metadata for rank validation. Dynamic-rank
runtime checks are intentionally deferred.

Backend lowering keeps address computation separate from load/store emission.
The address helper extracts descriptor fields through
`BUFFER_VIEW_FIELD_INDICES`, starts from `data`, includes `offset_bytes`, loads
byte strides from `strides`, and computes:

`effective_byte_offset = offset_bytes + sum(index_k * stride_k)`

The result is cast to the resolved element pointer type. Indexed reads emit a
load from that pointer; indexed stores cast the right-hand side to the resolved
element type and emit a store. The default bounds policy means semantic static
bounds rejection when provable and no emitted runtime bounds helper yet. Future
checked and unchecked runtime modes can reuse the same element-pointer helper.

## Dynamic List Construction

IRx also exposes one intentionally small list-building surface for frontend-
emitted AST:

- `ListCreate(element_type)` creates an empty list value with explicit element
  type
- `ListAppend(base, value)` grows a mutable list variable or field
- regular `SubscriptExpr` lowering may read from produced list values

This is deliberately narrower than a full collection API. The goal is to let
frontends author pure source routines that accumulate list results inside loops
without moving collection policy into the frontend. The runtime owns
append/growth, indexed reads, and idempotent destruction. Semantic ownership
sidecars drive lexical cleanup and return moves for scalar dynamic lists.
Copying borrowed storage, generator-owned lists, nested owning elements, and
object-field ownership remain outside this initial contract.

## String Ownership

IRx classifies string expressions with the same typed `ResourceOwnership`
sidecar used for lists. Literals and type-name results are static, parameters
and identifiers are borrows, and concatenation, numeric formatting, and defined
Arx string-returning calls produce owners. Lowering consumes copy/move/return
metadata, checks every string allocation, frees owned locals and temporaries,
and leaves immutable globals untouched. The raw C-string ABI remains
deliberately narrow: owned object fields, owned generator slots, borrowed
parameter escape, and external string returns without an ownership contract fail
during semantic analysis.

## Common Collection Methods

IRx also exposes backend-neutral query nodes for common collection operations:

- `CollectionLength(base)` returns the logical length as `Int64`
- `CollectionIsEmpty(base)` returns a Boolean emptiness check
- `CollectionContains(base, value)` checks list, tuple, or set values and dict
  keys
- `CollectionIndex(base, value)` returns the first list/tuple index or `-1`
- `CollectionCount(base, value)` returns the number of list/tuple matches

Semantic analysis validates the receiver kind, probe type, and result type and
attaches a `ResolvedCollectionMethod` sidecar. Lowering consumes that sidecar
instead of re-resolving the collection operation from raw AST shape.

Literal lists, tuples, sets, and dictionaries support common length, emptiness,
and containment queries. Dynamic IRx lists also support length, emptiness,
contains, index, and count by reusing the existing list runtime and emitting
small search loops where needed. Dynamic set and dictionary method lowering
remains intentionally deferred until those runtime representations exist.

## Iterable Semantics

IRx now models iteration as a semantic capability instead of as backend-specific
collection probing. Semantic analysis resolves known iterable expressions into a
`ResolvedIteration` sidecar that records the adapter kind, yielded element type,
ordering contract, and loop/comprehension target symbol. Backend lowering
consumes that sidecar instead of rediscovering whether an expression is a list,
set, or dict.

The executable MVP supports `ForInLoopStmt` and `ListComprehension` over list
iterables, including literal lists and dynamic IRx lists. List iteration follows
index order and evaluates the iterable once when that loop or comprehension
clause is entered. Dict and set literals are recognized semantically as
iterables as well: dict iteration yields keys, while set iteration order remains
unspecified. Their dynamic lowering is intentionally guarded until IRx has
runtime-backed dynamic dict and set construction APIs.

## Generator Semantics

IRx models named generator functions as functions returning `GeneratorType(T)`.
Semantic analysis validates top-level `yield` sites against the declared yielded
element type and exposes generator values through the same `ResolvedIteration`
sidecar used by `ForInLoopStmt`.

The initial executable lowering supports straight-line named generator functions
with top-level `YieldStmt` nodes. Calls create a small generator object
containing an opaque frame pointer and an internal resume function pointer.
For-in lowering calls the resume function until it reports exhaustion. More
Python-compatible behavior such as nested-control-flow suspension, `yield from`,
generator expressions, `send`, `throw`, and `close` remains deferred.

## Tensor Layering

IRx now treats `Tensor` support as a distinct semantic layer aligned with Apache
Arrow's homogeneous tensor model:

- the builtin Arrow C++ backed tensor runtime provides dtype, shape, stride, and
  data-buffer ownership for homogeneous N-dimensional values through
  `arrow::Tensor`
- the canonical `irx_buffer_view` substrate remains the lowering descriptor for
  indexing, byte-offset calculation, ownership, and layout flags

That split keeps the data-container roles explicit:

- `tensor` is the homogeneous N-dimensional semantic abstraction
- `array` remains the one-dimensional Arrow array/runtime abstraction for
  low-level columnar values
- `DataFrame` wraps heterogeneous named columns backed by Arrow C++
  `arrow::Table`, while `Series` uses `arrow::ChunkedArray`
- `record_batch` provides a separate Arrow RecordBatch and IPC streaming bridge
- `buffer/view` remains the low-level layout and ownership substrate

Current tensor lowering stays intentionally conservative:

- literals build Arrow C++ tensor handles through `irx_arrow_tensor_*`, then
  wrap borrowed tensor buffers in external-owner buffer views
- indexing and byte-offset queries reuse buffer/view stride arithmetic
- view construction is shallow and metadata-driven
- fixed-width numeric element types are supported in this phase
- Arrow C++ backed `Tensor` values remain readonly in this phase

## Why `visit(...)` Remains the Public Lowering Boundary

The codegen layer continues to use method-based Plum multiple dispatch:

- `visit(self, node: ...)`

This remains the only public dispatch boundary for backend lowering. IRx does
not use a free-function dispatch registry or a second public API like
`lower(...)` or `build_node(...)`.

That choice keeps backend code readable and local:

- AST-family-specific lowering remains attached to the visitor class.
- Mixins can group overloads by concern without changing the public surface.
- Shared lowering state stays on the visitor instance instead of moving into a
  registry-driven design.

## Core Class and Protocol

`VisitorProtocol` and `VisitorCore` serve different purposes:

- `VisitorProtocol` defines the stable interface that mixins and runtime feature
  declarations depend on for typing, building on `BaseVisitorProtocol`.
- `VisitorCore` is the concrete implementation center that owns mutable state,
  module setup, helper methods, and backend lifecycle.

`VisitorCore` is still internal to the backend package. IRx uses
`from public import private` for module-level internal helpers and internal
implementation classes when a clear non-underscored name reads better than an
underscore-prefixed export. That keeps internal names readable without making
them part of the intended public surface.

The protocol is not a replacement for the core class. It exists so backend
subsystems can depend on a narrow contract instead of the full concrete type.

## Visitor Mixins

The final backend visitor is composed from concern-specific mixins plus the
shared core. Each mixin should contain:

- `@dispatch def visit(self, node: ...)` overloads for one concern
- a small number of private helpers local to that concern

Examples of concern boundaries include:

- literals
- variables
- unary and binary operators
- control flow
- functions
- runtime or domain-specific lowering

This keeps dispatch organization aligned with language structure while still
sharing one lowering state object.

## Canonical Loop Lowering

IRx now treats loop lowering as one small shared control-flow contract instead
of three ad hoc visitors:

- `while`: `cond -> body -> exit`, with `continue` targeting `cond`
- `for-count`: `cond -> body -> update -> exit`, with `continue` targeting
  `update`
- `for-range`: `cond -> body -> step -> exit`, with `continue` targeting `step`

Loop variables remain semantic symbols rather than backend-only temporaries.
For-count initializers are visible only within the loop. For-range induction
variables are body-visible, loop-scoped, and restored after lowering so outer
shadowed bindings remain stable. Mutable post-loop state reconciles through the
existing variable-slot model instead of accidental value-stack state.

## Contributor Guidelines

When extending IRx, these rules help preserve the architecture:

- Put semantic meaning and validation in `analysis/`, not in a backend.
- Let codegen consume normalized semantic information instead of re-deriving it.
- Keep buffer/view support framed as a low-level memory/container substrate, not
  as NumPy-like user-facing array behavior.
- Keep shared visitor dispatch defaults in `packages/irx/src/irx/base/visitors/`
  so semantic and backend visitors fail consistently for unsupported ASTx nodes.
- Add new backend-wide infrastructure at the package root, not under `helpers/`.
- Keep mutable lowering state instance-local.
- Prefer explicit code over clever abstractions.
- Use the package name, not class prefixes, to identify the backend.

## If Another Backend Ever Returns

IRx currently standardizes on a single builder package. If another backend is
ever introduced again, keep the public class names generic and make the package
split an explicit architecture decision instead of quietly rebuilding a plural
builders namespace.

## Arrow-first decision (M0)

**Status: direction approved; exact Arrow pins deployed; full CI/native
qualification pending.** Maintainer direction selects Arrow Scalar where
supported, Arrow 26, the existing CI stack, `stdlib.math` and operation-specific
IEEE/ULP conformance. This supersedes the roadmap's proposed Arrow 24 freeze.
The local implementation baseline remains
`b631d9075569b78ed9fac5b336b6a9aaf2726e35`; matching exact Arrow dependencies
are now pinned, but the future math API remains unimplemented. Primitive LLVM
transport is approved without mandatory persistent boxing; residency and
lifetime details remain measurement-driven. Each operation's measured tolerance
needs review before implementation. No backend switch is part of M0.

### Meaning and representation

Arx is a general-purpose native-compiled language with data-intensive computing
at its core: **Arrow-first, not Arrow-exclusive**. Arx owns source values,
types, lossless promotions, checked arithmetic, nulls, failures and ownership.
Arrow supplies compatible storage, compute and interchange implementations; it
does not determine language semantics. The existing
[semantic contract](semantic-contract.md) remains authoritative: analysis
resolves meaning and lowering consumes the resolved sidecars and compilation
session. A new compute plan belongs in `irx.analysis`, not the frontend or ASTx.

| Value or operation                                                      | Representation / implementation decision                                                                                                                                 |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Supported scalar operations                                             | Prefer Arrow Scalar and the corresponding Arrow compute family whenever it satisfies Arx semantics; LLVM/custom implementations are fallbacks for unsupported contracts. |
| Scalar transport and temporaries                                        | Primitive LLVM transport is allowed without permanent boxing; measure Arrow-resident chains and lifetime before selecting materialization policy.                        |
| Nullable scalar                                                         | Keep explicit validity separate from payload; do not read invalid payloads or substitute NaN for null.                                                                   |
| DataFrame / Series                                                      | Reuse opaque Arrow Table / ChunkedArray handles, preserving types, offsets, chunks and nulls.                                                                            |
| Arrow compute boundary                                                  | Adapt scalar bits and validity to Scalar/Datum in C++; an owned result must survive release of its inputs.                                                               |
| Tensor                                                                  | Arrow Tensor storage with a separate shape/stride adapter, not an implicitly valid Compute Datum.                                                                        |
| Control flow, classes, lists, files, future synchronization/concurrency | Native Arx facilities remain first class; no compulsory Arrow storage or linkage.                                                                                        |

For example, the existing integer count loop uses LLVM arithmetic while nullable
`frame.score + 0.5` uses the Series compute bridge. M0 preserves that baseline;
further measurement is deferred. Future scalar operations prefer Arrow when it
implements the checked contract; Arrow's unchecked default is not an acceptable
substitute. Classes and file operations retain their native implementations. An
owning list is not an Arrow Array merely because its elements are numeric. Arrow
objects stay behind `irx_arrow_*` / `irx_rb_*` opaque C handles; generated LLVM
must never encode C++ layouts. Construction and compute initialize outputs,
return typed status, and publish a result only on success. Retain/release,
borrow/move and failure cleanup follow the
[runtime ownership contract](runtime-ownership.md). New Scalar/Datum ABI
revision checks and failure-injection tests are M2/M3 work, not existing
guarantees of a public scalar ABI.

Activate only registered runtime features required by the resolved operation. Do
not add a second general compute dispatcher: extend the existing
`ColumnOperation` / `irx_arrow_column_compute` path. A proposed typed operation
identity must include input/output types and shapes, conversions, null/error
policy, feature dependencies and ownership; spelling alone is not identity.
Unsupported kernels and shapes fail closed at the responsible layer. Analysis
must receive typed compilation-scoped capabilities, not dynamically query an
unrelated globally cached lowering registry for operation meaning.

### Support and Arrow upgrade policy

Retain the interpreter floor in the
[package manifests](https://github.com/arxlang/arx/blob/main/pyproject.toml) and
the tested matrix in
[CI](https://github.com/arxlang/arx/blob/main/.github/workflows/main.yaml). The
older Python 3.10 expectation is deliberately **not** restored. An installable
future interpreter is not qualified merely because `requires-python` permits it.
The [support matrix](../support-matrix.md) distinguishes CI configurations from
best-effort targets: Ubuntu x86-64 is the qualification target; macOS, Windows,
other architectures and alternative compilers remain experimental until their
native/wheel gates run. C++20 is required; the qualification toolchain is the
Clang environment in
[conda/dev.yaml](https://github.com/arxlang/arx/blob/main/conda/dev.yaml). A
local run using a different toolchain must report that difference, not extend
the support claim.

The requested first-slice target is **Arrow 26**, with a matching exact
PyArrow/C++ patch pin (26.0.1 is the available patch release at this decision).
The
[IRx manifest](https://github.com/arxlang/arx/blob/main/packages/irx/pyproject.toml)
and root lockfile now pin matching exact PyArrow and `arx-arrowcpp-sources`
distributions. The installed source wheel's metadata, actual CMake version,
headers and license/notice assets have been checked against that pin. Retain the
companion source bundle; do not substitute another provider or mix old headers
with new libraries. Upgrades must regenerate the root lockfile using
`poetry lock`; failed resolution must leave the existing manifests and lock
consistent. Existing `arrowcpp_runtime_metadata`, native-cache fingerprints,
RecordBatch ABI checks and wheel-content tests are the starting safeguards, not
a universal mixed-version Scalar ABI detector. M2 must add that detector and
reject tests. The build helpers now reject disagreement between the source
bundle, its actual source tree, PyArrow, its packaged version header and linked
C++ version before returning build inputs. Missing/corrupt sources or headers
produce structured runtime-feature diagnostics. This preflight is not a
multi-version adapter or a loaded-handle ABI guarantee.

Use Arrow core and Compute for the first math slice. IPC, CSV and Parquet keep
their existing feature boundaries; no new Acero/Flight/Dataset query-engine
dependency is required. Existing Parquet transitive libraries are not removed by
this decision. No newer Arrow API may enter the slice incidentally: update the
matching headers/libraries together, regenerate the root lockfile, rebuild
native artifacts and wheels, and run the interpreter CI matrix, numerical
conformance, sanitizer, C Data/C Stream and fresh-wheel tests. Internal ABI
changes may break before 2.0 with coordinated producers/consumers and release
notes; standard Arrow interchange ownership contracts do not become optional.

### Proposed numerical and public API contract

Keep current checked integer/Boolean results, null validity and error categories
exact. Ordinary scalar IEEE arithmetic is unchanged in M0. If Arrow cannot
implement a supported contract, an LLVM/custom fallback must pass the same
per-operation conformance tests. Performance alone does not make an unsupported
fallback the default for an Arrow-supported operation. No fast-math,
reassociation or lossy cast is authorized by M0.

The first **proposed, unimplemented** operation is imported `sqrt(value)` from
`stdlib.math`, for `f64` and `series[f64]`, using the Arrow C++ `sqrt` family.
Python's `math.sqrt` and array-library ufunc call shapes are usability
references, not implementation dependencies. Unlike Python `math.sqrt`, the
proposed contract uses IEEE domain results, consistently across both shapes:

| Input                                    | Proposed result / required comparison                                                                          |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Finite nonnegative f64                   | f64 root, at most 4 ULP from an independent high-precision reference; no blanket relative tolerance near zero. |
| `+0.0`, `-0.0`, `+infinity`              | Same signed zero or positive infinity, checked exactly.                                                        |
| Negative nonzero value, `-infinity`, NaN | NaN classification; payload/sign preservation is not promised.                                                 |
| Null Series element                      | Null, distinct from NaN; payload is not inspected.                                                             |
| Empty or chunked Series                  | Same logical length/order/nulls; no output chunk-boundary guarantee.                                           |
| Unsupported dtype/shape                  | Analysis diagnostic, not an implicit f32/integer/Tensor conversion.                                            |
| Allocation/kernel/ABI failure            | Existing typed runtime failure; never a success value read from a failed output slot.                          |

The 4-ULP bound is a candidate operation-specific acceptance requirement to
review and verify against pinned Arrow 26, not an assertion that untested
kernels already satisfy it. Cross-shape results must have the same dtype,
validity and classification, and each satisfy the bound. There is no bitwise
promise across SIMD/CPUs, Arrow versions or language implementations. No
deterministic strict mode or checked/unchecked public alias is introduced. The
remaining candidate contracts use the following independently specified rules,
not whatever a default checked Arrow kernel happens to do:

| Proposed operation          | IEEE domain/limit contract                                                                                                                                                | Candidate finite budget |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `sqrt`                      | Preserve signed zero; negative nonzero inputs give NaN.                                                                                                                   | 4 ULP                   |
| `exp`                       | Both zero signs give 1; negative infinity gives +0; overflow gives +infinity and underflow rounds to a subnormal or +0.                                                   | 8 ULP                   |
| Natural `log`               | Both zero signs give -infinity; negative nonzero inputs give NaN; log(1) gives +0.                                                                                        | 8 ULP                   |
| Power (future source `pow`) | Negative finite bases with fractional exponents give NaN; zero-negative powers give signed infinity as appropriate; preserve odd-power signs, x**0 and 1**NaN identities. | 16 ULP                  |

`packages/irx/tests/test_arrow_math_contract.py` supplies independent 200-digit
Decimal references and explicit special-value expectations for all four
operations. Scalar, sliced-array, chunked/null and empty cases check type,
validity, IEEE class/sign and ULP error. Finite nonzero/subnormal references may
not be flushed to zero merely because that would fit a loose tolerance. These
tests can measure the historical build, but must pass again against exact Arrow
26 before approving its numerical contract. They do not establish an Arx call
path or implement the additional public functions.

Proposed common case (not executable on the baseline):

```text
import sqrt from stdlib.math
result: f64 = sqrt(value)
```

Proposed advanced case: the **same imported function**, `sqrt(frame.score)`,
accepts a nullable `series[f64]`, preserves nulls and leaves the input owner
valid. Unsupported options are rejected, not ignored. There is no builtin
`sqrt`, redundant Series method or public kernel-by-string escape hatch.
Imported aliases, shadowing, templates and explicit user `extern sqrt` calls
must resolve by callable identity, with independent C-FFI meaning.

### Pure-Arx library acceptance

An independently installed package containing only `.x` sources and declarative
metadata must consume supported Arrow operations through the same typed modules
as application code. Its author supplies no C/C++ adapter, native build hook,
raw-pointer plumbing or untyped kernel-string call. Analysis resolves canonical
callable identity, shapes/options, conversions, feature requirements, failures
and ownership through the imported module graph; lowering consumes that plan.
The shared IRx runtime uses an approved Arrow FunctionRegistry/CallFunction
boundary. Adding a second supported kernel must not add a second handwritten C++
shim or an independent operation catalog.

`packages/arx/tests/fixtures/pure-arx-package` and the wheel smoke tool provide
the **current-behavior scaffold**: an installed `demo_arx_math` package
reexports an imported scalar helper plus f64 Series addition/multiplication. It
tests aliases, local-name shadowing and an escaping result after its source
frame and intermediate owners leave scope. The package has no native section or
authored Python/C/C++ files. Its baseline operators are not a substitute for the
public math acceptance gate:

1. A clean installed environment compiles this independently packaged library
   calling `stdlib.math.sqrt` on f64 and Series, including invalid-call and
   structured failure/owner-lifetime cases.
2. A second approved typed kernel (candidate `exp`) uses the identical native
   dispatcher with no new per-kernel C++ shim.
3. The package passes exact-pinned Arrow 26, semantic, native ABI/sanitizer and
   compiled installed-wheel gates. No checkout-local compiler hooks count.

The first two math capabilities remain unimplemented and are M1–M4/A05b work. C
Data/C Stream exchanges arrays and streams, not arbitrary foreign functions.
External native kernel producers need trusted build metadata and explicit
registration; automatic C++ bindings and Arx UDF exports remain separate work.

### Delivery and test ownership

This inventory identifies existing extension points, not new supported APIs.
Paths below are relative to `packages/irx/` except where marked otherwise.

| Slice                           | Existing source owner                                                                                                                  | Earliest-layer / native ABI / compiled owner                                                                                                                                        |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A00/M0 policy                   | This decision; `docs/support-matrix.md`; `docs/apache-arrow.md`                                                                        | Documentation review; existing capability/example tests in `packages/arx/tests/python/test_documentation.py`.                                                                       |
| A01/M0 baseline                 | `scripts/benchmark_arrow_first.py` and versioned `scripts/benchmarks/arrow-first-v1.*` inputs                                          | `tests/test_arrow_baseline.py`; existing `tests/test_nullable_kernels.py` and `tests/test_arrow_interop.py`; no new source semantics.                                               |
| A02/M1 types and operation plan | `src/irx/analysis/{numeric_policy,nullable,arrow_conversion,resolved_nodes}.py`; existing `ColumnOperation`, `set_operation`           | `tests/analysis/test_nullable_columns.py`, `test_numeric_policy.py`, `test_numeric_semantics.py`; unsupported combinations tested before lowering.                                  |
| A03/M2 feature and ABI          | `src/irx/builder/runtime/{registry,arrowcpp}.py`, `array/feature.py`, `arrow/native/{irx_arrow_runtime.h,irx_native_status.h}`         | Runtime feature/ABI tests, `tests/native/arrow_interop.cpp`, sanitizer and `scripts/test_wheels.py`; compiled feature-selection regression.                                         |
| A04/M3 scalar adapter           | `arrow/native/irx_arrow_series.h` (`column_scalar`, `scalar_bits`, `irx_arrow_column_compute`), `src/irx/builder/lowering/nullable.py` | Extend `tests/test_nullable_kernels.py` for status/output/lifetime and LLVM verification; compiled regression in `packages/arx/tests/python/test_codegen_ast_output.py`.            |
| A05/M4 public sqrt              | `packages/arx/src/arx/stdlib/math.x`, IRx analysis/call facts and nullable lowering                                                    | Import/alias/shadowing analysis; native scalar/Series conformance; `.x` fixture under `packages/arx/tests/arx/` and translate/build/run test.                                       |
| A00a contributor rules          | Root `AGENTS.md`                                                                                                                       | Architecture review against this decision; native/compiled checks belong to the referenced implementation slices.                                                                   |
| A00b source bundle              | Companion `arx-arrowcpp-sources` version/bundle script, vendor metadata and licenses                                                   | Companion `tests/`; source/archive integrity and install checks; Arrow 26 native/wheel qualification before A00c.                                                                   |
| A00c exact upgrade              | IRx manifest, root lock, `builder/runtime/arrowcpp.py`                                                                                 | `tests/test_arrow_runtime.py` preflight failures; native sanitizer/interop; compiled clean-wheel source-package smoke.                                                              |
| A05b source-only proof          | Pure-Arx fixture and `scripts/test_wheels.py`                                                                                          | `packages/arx/tests/python/test_wheel_smoke_script.py` import/type negatives; shared ABI/conformance tests; installed compiled package with sqrt plus a second kernel.              |
| A06 additional math             | Typed operation catalog, call facts and stdlib                                                                                         | Extend `tests/test_arrow_math_contract.py` and analysis type/option tests; reuse shared ABI tests; source-only compiled examples.                                                   |
| A07 Series consolidation        | `analysis/nullable.py`, nullable lowering and `irx_arrow_series.h`                                                                     | `tests/test_nullable_lowering.py`; `tests/test_nullable_kernels.py`; `packages/arx/tests/python/test_nullable_series.py`.                                                           |
| A08 owned values                | `analysis/ownership.py`, lowering cleanup and native handles                                                                           | Ownership analysis tests; `tests/native/arrow_interop.cpp` plus sanitizer/failure injection; compiled escaping-owner/exception boundaries.                                          |
| A09–A11 rich families           | Column descriptors, `analysis/arrow_conversion.py`, native RecordBatch and selected stdlib                                             | `tests/analysis/test_nullable_columns.py` extensions; native schema/interop tests; extend `test_nullable_series.py` rich-schema compiled coverage for each new supported operation. |
| A12 interchange                 | `record_batch*` and native C Data/C Stream headers                                                                                     | Import validation tests; `tests/test_arrow_interop.py`; compiled `packages/arx/tests/python/test_arrow_interop.py` and Arrow examples.                                              |
| A13 performance                 | Versioned baseline harness and resolved execution profiles                                                                             | Oracle/profile analysis tests; shared ABI/conformance suites; compare A05/A05b compiled workloads on the same machine.                                                              |
| A14 release                     | Existing CI, manifests, release scripts and wheel tool                                                                                 | Artifact/manifest tests; native sanitizers and version rejection; clean installed-wheel source-only consumer.                                                                       |
| A15 optional Acero              | A future registered runtime feature only after a concrete workload                                                                     | New analysis capability rejection, native bounded-memory/error tests and compiled streaming scenario; no existing implementation is implied.                                        |

ASTx remains language-agnostic; add modeling there only if an existing reusable
node cannot express the operation. Arx owns parsing/import discovery, IRx owns
meaning/lowering/runtime, and ArxPy/ArxJIT are not alternate compute engines.
ArxJIT native dispatch remains unimplemented. Each later slice must preserve the
three test owners above rather than putting all failures in integration tests or
duplicating the complete numeric matrix at every layer.

The first public slice includes A05b: f64 Scalar/Series sqrt plus the second
typed-kernel proof through one dispatcher, verified LLVM, selective linking,
success-only outputs and lifetime tests, independent numerical oracles including
subnormals/domain/null/empty/chunks, compiled current-syntax examples, sanitizer
and fresh-wheel gates. No f32 or integer sqrt, universal public Scalar
constructor API, query engine or wholesale scalar-backend switch is included.

### Work-queue decisions

[PR #197](https://github.com/arxlang/arx/pull/197) was verified **closed without
merging** through read-only PR metadata on 2026-11-15. It is not a dependency of
A00–A05/M1–M5; no replacement libm-inference PR is planned.
[Issue #164](https://github.com/arxlang/arx/issues/164) stays deferred as
independent explicit C-FFI linking work: the current-syntax plain `extern exp`
reproducer still fails at linking. It is not fixed by Arrow math.

[PR #110](https://github.com/arxlang/arx/pull/110) and
[#111](https://github.com/arxlang/arx/pull/111) remain separate unmerged work.
Read-only patch comparison against the local baseline found a parallel
`irx_compute_*` RecordBatch ABI: unchecked `add/subtract/multiply/divide`,
Arrow-selected promotions, signed i64 transport for uint64 reductions, and
errors for empty/all-null sums. These conflict with the current checked
Series/type/validity contracts. #111 also preserves wrapping addition in a test;
that assertion must not be ported as an Arx contract. Reconcile useful
null/filter/sort cases with the owning current bridge, not a second catalogue;
Compute linking is already present in `arrowcpp_linker_flags`. The patches
target older package/lock state and are not merge-ready inputs. Their revised
implementations would need fresh review; no remote PR was rebased, split or
closed as part of M0.

Current-source triage: tensor construction/view/owner statuses from
[#82](https://github.com/arxlang/arx/issues/82) now go through
`check_tensor_status`; rank-one tensor/Series/list adapters requested in
[#149](https://github.com/arxlang/arx/issues/149) have numeric-sequence
coverage. Neither observation proves every historical failure resolved. Repeated
literal allocation [#175](https://github.com/arxlang/arx/issues/175) remains a
performance follow-up; buffer counters do not measure all C++ heap boxing.
Nullable syntax, print diagnostics and failed-auto recovery
([#184](https://github.com/arxlang/arx/issues/184),
[#185](https://github.com/arxlang/arx/issues/185),
[#193](https://github.com/arxlang/arx/issues/193)) must be reproduced with
name-first declarations and valid module docstrings, not copied legacy syntax.
Current-syntax probes still reproduce the scalar-union parser desynchronization,
the missing print location/secondary AnyType error, and local/field failed-auto
cascades respectively; `nullable[i64]` succeeds in the reduction probe. M0
audits these gaps; it does not expand into unrelated diagnostic fixes.

### Repeatable baseline

**Deferred:** existing benchmark artifacts are parked. No benchmark run or
performance report is an M0 or two-day implementation exit gate.

Run from the checkout with the development environment installed:

```bash
python scripts/benchmark_arrow_first.py --arrow-major 24 --output .tmp/arrow-before
# After the dependency upgrade, qualify Arrow 26 on the same host/toolchain:
python scripts/benchmark_arrow_first.py --output .tmp/arrow-after
```

JSON contains raw cold/warm samples, separate compilation/link/setup costs,
source/input hashes, Git dirty state, installed and manifest versions, compiler
flags, CPU/OS, native object/library sizes and peak RSS. Run `makim all.build`
before measuring wheel footprints; JSON records sizes and hashes of existing
wheels, or an empty list if wheel size was not measured. Markdown is generated
from those measurements, not hand-maintained evidence. `--samples`,
`--iterations`, `--case`, `--cxx` and repeatable `--cxx-flag=...` allow explicit
local qualification; changed settings must be reported in comparisons. Preserve
artifacts outside the temporary checkout for PR/CI comparison, not as a
checked-in machine-specific result log.

The default qualification target is exactly Arrow 26.0.1; another 26 patch is
not silently accepted. `--arrow-major 24` is explicitly the historical
before-upgrade measurement, not permission to ship the first slice on Arrow 24.
Installing/locking and qualifying Arrow 26 remains an M0 exit gate; an offline
Arrow 24 run cannot satisfy it.

The baseline measures **existing f64 addition**, not unimplemented sqrt: a
versioned unboxed LLVM loop, current scalar/Series C ABI and PyArrow checked
addition. Inputs include scalar, dense, nullable sliced chunks and empty data.
The oracle is independent exact dyadic arithmetic, not one backend's output.
Native inputs cross the standard C Stream boundary; handle release precedes
result checks. Every backend/case starts in a fresh subprocess. First-call
kernel time and warm allocation/release time are separate; cold does not mean
flushing OS/library page caches. LLVM preallocates its output, unlike Arrow;
these are representation costs, not a claim of equivalent allocation policy or
frontend/compiler throughput. Arrow pool allocation counters exclude C++
Scalar/handle and Python heap allocations; pool high-water marks and RSS include
inputs/setup. Whole-heap boxing instrumentation and the original list/tensor
hot-loop workload remain M9 follow-ups. A before/after result for a future
backend is not available in M0; no speedup or cross-platform support is inferred
from this harness.
