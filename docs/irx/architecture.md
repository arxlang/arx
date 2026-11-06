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

### Explicit call-handler composition

Table I/O is the first composed handler family. Normal symbol lookup selects a
trusted operation; its registered analysis handler produces a typed call plan.
LLVM call lowering dispatches on that plan, not the source name. Handlers use
small phase-owned service interfaces rather than inheriting the entire compiler.
Other visitor families have not yet migrated.

Analysis and builders accept explicit, immutable phase configurations.
Derivation names replacements; duplicate signatures and unavailable invocation
dependencies are rejected. Each compiler instance builds fresh Plum
dispatch/cache state, so derived configurations do not mutate parents or live
compilers. Providers must not capture compilation state. Recursive dispatch is
supported; concurrent use of one mutable compiler instance is not.

Built-in call providers are discovered from direct modules in
`irx.extensions.builtin`. Each module exports a lightweight `descriptor()`; its
`FeatureDescriptor` names dependencies, supported backends, contract revision,
and phase factory references with promised handler identities. Add the
descriptor and phase-owned implementations, not another central registry entry.
Dependency closure and phase composition reject conflicts before the selected
phase compiles an AST. Factories load only for enabled phases. There is no
filesystem plugin scan or third-party entry-point loading.

Composition inspection is a programmatic IRx facility, not a public Arx CLI
command. It describes migrated call handlers, **not all language support**.
Native activation is unknown until a compilation requests runtime symbols;
selection never implies activation. CLI exposure is deferred until a concrete
diagnostic workflow justifies it.

Python hosts inspect the same `default_feature_configuration()` used by the
compiler. For an explicit selection, construct
`FeatureConfiguration(discover_builtin_features(), selected=("irx.table_io",))`,
then pass its `phase("analysis")` and `phase("lowering")` catalogs to the
existing analyzer/builder configuration arguments. An empty selection disables
all composed call providers; required disabled dependencies are errors.
`inspect()` returns a fresh metadata snapshot. For a loaded phase,
`explain(value_type, context_type)` uses Plum to select the actual contribution,
including explicit replacements, without executing it.

Lightweight contribution metadata imports neither LLVM, PyArrow, nor Arx.
Analysis providers do not import the backend. Registering a handler does not
activate native code; emission still requests registered runtime symbols.

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
- `BaseVisitor`: a concrete Plum-dispatch scaffold with explicit
  `NotImplementedError` defaults for the current ASTx node surface

This keeps typing and runtime behavior separate:

- protocols define what visitor-like objects must expose
- the concrete base class defines what happens for unsupported nodes

In practice:

- `SemanticAnalyzer` inherits `BaseVisitor`
- `BuilderVisitor` inherits `BaseVisitor`
- native symbol factories use a separate minimal LLVM representation protocol

## Builder Architecture

IRx now exposes a single builder package at `packages/irx/src/irx/builder/`. The
package path identifies the concrete LLVM builder, while the public classes
inside it use short generic names.

For example, `packages/irx/src/irx/builder` exposes:

- `Builder`
- `Visitor`

`VisitorCore` remains an internal implementation class.

This keeps the public API concise without reintroducing legacy class prefixes.

## Builder Package Layout

The LLVM backend is split into first-class modules instead of one monolithic
builder:

- `../packages/irx/src/irx/base/visitors/`: shared visitor protocol and runtime
  scaffold
- `backend.py`: public backend entry points
- `core.py`: compilation orchestration and backend lifecycle
- `protocols.py`: minimal LLVM representation contract for runtime declarations
- `services/`: explicit representation, conversion, addressing, and exit
  services
- `types.py`, `casting.py`, `vector.py`, `strings.py`, `runtime/`: shared IR
  infrastructure
- `lowering/`: ordinary concern implementations, typed dependency records, and
  the per-compilation composition graph
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

## Composed Analysis and Lowering

`visit(node)` remains the traversal boundary. Analysis and lowering each build
ordinary concern objects with explicit, typed dependency records. Their local
Plum `visit` overloads are exported through nominal node contributions into a
fresh `ScopedNodeDispatch` with compiler-owned bindings and resolution cache.
Identical nominal signature shapes share immutable Plum selection metadata,
never handlers or compilation state: Plum retains constructed functions globally
and supplies no public disposal API. Selection remains Plum-owned, with no
parallel specificity algorithm. Imports do not register handlers on a shared
analyzer or backend visitor. Unknown nodes retain phase-specific failing
fallbacks; a modeled AST node is not proof of support.

The composition modules wire concrete dependencies and typed callback edges for
recursive concerns. They are construction roots, not service locators passed to
handlers. Native symbol factories receive only LLVM representations and the
destination module. Immutable call-provider metadata remains separate from bound
node implementations and mutable compilation state; programmatic feature
inspection still describes the configured call-handler catalog, not all nodes.

LLVM services consume semantic types, identities, layouts, and conversion plans.
They do not repeat name resolution or promotion policy. String globals and
helper caches belong to their LLVM module. Module declarations, function values,
cleanup/exception regions, and generator frames have distinct state records;
scoped function emission restores bindings, result stacks, control transfer
state, fast-math settings, and generator state even after failure. No runtime
ABI or Arrow object-layout boundary changes are implied.

To extend a concern, add its typed local overload and explicit node
contribution. A new concern supplies only its required dependency record and is
wired once in the owning phase's composition root. Do not reintroduce visitor
multiple inheritance, global registration, or a universal compiler context.

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
