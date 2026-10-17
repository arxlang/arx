# Runtime Ownership Inventory

## Status and purpose

This inventory was checked against the local IRx lowering and native runtime on
2026-10-15. It is the starting point for the Arx resource model, not yet a
complete production ownership specification. Scalar dynamic lists, immutable
strings, text files, and acyclic class references have bounded enforced
ownership slices. A resource may be promoted to the stable language only after
its create, borrow, transfer, escape, release, and failure paths are represented
here and enforced by semantic metadata and lowering.

## Required vocabulary

- **owner**: must perform exactly one final release unless ownership is moved;
- **borrow**: may access a value only while its documented owner is alive;
- **move**: transfers the release obligation and invalidates the old owner;
- **shared**: multiple handles retain a shared native owner;
- **view**: non-owning data/shape metadata with an explicit owner handle;
- **output slot**: caller-provided storage that is readable only after a
  successful status result.

The final Arx 1 model must choose which of these operations source programs can
observe. LLVM lowering must consume the ownership decision from semantic
metadata; it must not infer ownership again from AST shape.

## Current inventory

| Resource                                    | Creation/allocation                                 | Current release path                                                                | Current ownership state                                                | Required work                                                                                            |
| ------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Scalar values and literal aggregate storage | LLVM values, globals, or stack allocation           | Function/stack lifetime                                                             | Non-owning values                                                      | Specify overflow and invalid-operation behavior.                                                         |
| Dynamic list backing bytes                  | `realloc` in `irx_list_append`                      | Semantic owners call idempotent `irx_list_destroy` on lexical exits and replacement | One scalar-list owner; return transfers ownership                      | Add nested owning elements, generator/object-field lifecycle, and sanitizer/fault proof.                 |
| Literal-list runtime view                   | Stack descriptor over stack/literal data            | Stack lifetime                                                                      | Static/non-owning sidecar                                              | Escape and mutation are rejected; retain conformance coverage as literal representation evolves.         |
| Concatenated string                         | Checked `malloc` in generated `strcat_inline`       | Semantic owner calls `free` on lexical exit/replacement                             | One owner; return moves to caller                                      | Add sanitizer/fault-injection and long-running leak proof.                                               |
| Numeric/string formatting result            | Checked `malloc` in `_snprintf_heap`                | Consuming print frees immediately; string values follow semantic cleanup            | Temporary or transferred owner                                         | Add injected `snprintf` failure and allocator-fault execution tests.                                     |
| String literals, empty strings, type names  | LLVM global constant                                | No release required                                                                 | Static/non-owning sidecar                                              | Retain negative coverage so static pointers never reach `free`.                                          |
| Class instance                              | Checked zeroed `irx_class_create`                   | Last `irx_class_release` invokes concrete drop then frees payload/token             | Acyclic reference-managed identities; strings/files/class fields owned | Cycles, concurrency, general container/generator/global/external ownership deferred.                     |
| Generator frame                             | `malloc` in generator factory                       | No matching free found                                                              | Escaping opaque pointer                                                | Add close/exhaustion/drop operation, cleanup captured owners, allocation checks, and double-close rules. |
| Buffer owner                                | Native `malloc`; optional external release callback | `irx_buffer_owner_release`                                                          | Reference-counted owner                                                | Add sanitizer/fault tests and prove all retain/release/status paths, including interpreter/FFI failures. |
| Buffer view                                 | Native view plus owner handle                       | `irx_buffer_view_release`                                                           | Shared owner with borrowed byte range                                  | Enforce view lifetime and status checks at every lowering path.                                          |
| Arrow schema                                | C++ handle owning shared Arrow schema               | `irx_arrow_schema_release`                                                          | Opaque owner                                                           | Audit every create failure and output slot; keep Python wrappers idempotent.                             |
| Arrow array builder                         | C++ unique builder handle                           | finish consumes or builder release                                                  | Opaque owner with consuming finish                                     | Prove exactly-once consume/release on success and failure.                                               |
| Arrow array                                 | C++ handle with shared Arrow array                  | `irx_arrow_array_release`                                                           | Opaque shared-data owner                                               | Document borrow/transfer for C Data Interface export/import.                                             |
| Arrow tensor builder                        | C++ unique builder handle                           | finish consumes or builder release                                                  | Opaque owner with consuming finish                                     | Prove cleanup for append/shape/finish failures.                                                          |
| Arrow tensor                                | C++ handle with shared buffer                       | `irx_arrow_tensor_release`                                                          | Opaque shared-data owner                                               | Specify Arx return/argument/view ownership and shape validation.                                         |
| Arrow table/DataFrame                       | C++ table handle                                    | `irx_arrow_table_release`                                                           | Opaque owner                                                           | Ensure all lowered construction paths release intermediate arrays and table results.                     |
| Arrow Series/chunked array                  | C++ chunked-array handle                            | `irx_arrow_chunked_array_release`                                                   | Opaque owner                                                           | Define whether field selection returns an owned handle or borrow; test parent release ordering.          |
| RecordBatch type descriptor                 | C++ allocated descriptor                            | `irx_type_release`                                                                  | Opaque owner                                                           | Keep local descriptor cleanup on every nested schema failure.                                            |
| RecordBatch schema                          | C++ schema handle                                   | `irx_rb_schema_release`                                                             | Python wrapper owner                                                   | Partial-construction safety is implemented; add context-manager and explicit closed-state checks.        |
| RecordBatch builder                         | C++ builder handle                                  | finish consumes native builder; wrapper release                                     | Python wrapper owner                                                   | Specify wrapper behavior after finish and reject reuse deterministically.                                |
| RecordBatch batch                           | C++ shared RecordBatch handle                       | `irx_rb_batch_release`                                                              | Python wrapper owner                                                   | Retain idempotent release and reject access after release.                                               |
| RecordBatch stream writer                   | C++ writer and sink                                 | close plus `irx_rb_stream_writer_release`                                           | Python wrapper owner                                                   | Define close failure versus unconditional release; test both file and buffer errors.                     |
| RecordBatch stream reader                   | C++ reader                                          | `irx_rb_stream_reader_close`                                                        | Python wrapper owner                                                   | Clarify whether close deletes the handle and make repeated close/access rules explicit.                  |
| PyArrow interchange capsules                | Arrow C Data Interface callbacks                    | Arrow release callbacks                                                             | Transferred/shared by protocol                                         | Test both release orders, partial imports, and abandoned capsules.                                       |

## Current status and output-slot rules

The Arrow and RecordBatch C APIs generally return integer statuses and place new
handles or values in caller-owned output slots. The required rule is:

1. initialize the output slot to null/zero;
2. invoke the ABI function;
3. if status is not success, do not read or release the output as a valid value;
4. translate the native error into a structured diagnostic or API exception;
5. on success, immediately record the resulting ownership obligation.

The dynamic list append API returns a status, and current lowering immediately
passes it to the fail-closed `irx_list_require_ok` runtime check. Dynamic
indexing still returns a pointer and terminates the process on invalid input.
The index interface and language-level error model need a consistent
status/output-slot design before list ownership is stable.

## Enforced scalar dynamic-list contract

IRx semantic analysis attaches a typed `ResourceOwnership` sidecar to list
expressions, declarations, arguments, calls, assignments, and returns. The
current contract is deliberately move-only:

- `ListCreate`, list comprehensions, and list-returning calls produce owned
  values;
- a local declaration consumes a fresh owned value, while a list parameter and
  an identifier expression are borrows;
- a list-valued assignment consumes a fresh owner and destroys the target's
  previous storage before replacement;
- returning a fresh owner or an owned local moves it to the caller; returning a
  borrowed parameter or static literal storage is rejected with `IRX-S013`;
- append is allowed only through a locally owned list binding;
- literal-list storage is static, supports direct indexing and iteration, and is
  never passed to the dynamic-list destructor; and
- local aliases, borrowed/static-to-owned copies, static list call arguments or
  defaults, owned list locals in generators, and owning list elements remain
  unsupported and fail closed.

Lowering consumes these sidecars. It registers `irx_list_destroy` for owned
locals and non-transferred temporaries, emits cleanup on normal block
fallthrough, return, `break`, and `continue`, excludes an owner moved through a
return, and retains cleanup for the caller that receives the result.

## Enforced string contract

IRx uses `ResourceKind.STRING` sidecars to distinguish immutable global pointers
from heap owners even though both lower to the current C-string pointer ABI.
Concatenation, numeric-to-string formatting, and defined Arx string-returning
calls are owners; literals, empty defaults, and type names are static; function
parameters and identifier expressions borrow.

Owned locals and temporaries call `free` on all ordinary control-flow exits.
Owned replacement frees the old generation first. Returning an owner moves it to
the caller, while returning static storage performs a checked copy so the call
result has one unambiguous release obligation. Allocation and formatting failure
emit structured `ARX-RUNTIME-STRING-001` or `ARX-RUNTIME-STRING-002` records and
terminate before a null pointer is used.

Bindings cannot change between static and owned storage. Borrowed parameters
cannot initialize owned locals or escape through returns. Owning struct fields,
generator locals, external string results without an ownership ABI, and identity
casts that would obscure an owner fail closed with `IRX-S013`.

## Cleanup control flow

IRx has typed `cleanup_stack` actions used by context managers, list owners, and
string owners. Resource cleanup extends this mechanism only after semantic
analysis states whether a value is an owner, borrow, move, or escape. Required
control-flow cases include:

- normal block fallthrough;
- every explicit and implicit return;
- both sides of a conditional and only the paths that acquired a resource;
- loop `break`, `continue`, and normal exit;
- allocation or native-status failure after earlier resources were acquired;
- transfer into a returned value, field, container, FFI output, or Python
  wrapper;
- generator suspension, exhaustion, explicit close, and abandoned generator.

Cleanup emission must never occur after an LLVM terminator and must never
double-release a moved value.

## Enforcement and verification backlog

1. Extend the ownership sidecar model beyond acyclic classes to generators and
   native handles.
2. Add sanitizer, allocator-fault, and bounded-growth proof for list and string
   cleanup.
3. Decide whether the stable ABI keeps compile-time-classified C-string pointers
   or adopts a tagged string value before compatibility freeze.
4. Add class and generator lifecycle operations before stabilizing either ABI.
5. Make Python wrappers reject use after release and support deterministic
   context management where useful.
6. Add allocator fault injection for every create/append/finish path.
7. Run compiled ownership programs under ASan, LSan, and UBSan.
8. Add long-running create/use/release loops with bounded memory growth.
9. Test output slots remain unread on all injected non-success statuses.
10. Document any intentionally immortal allocation; process-lifetime leakage is
    not an implicit ownership policy.

## Enforced file contract

Public File objects use `ResourceKind.CLASS` reference ownership. Their private
native field retains `ResourceKind.FILE` unique ownership; existing low-level
IRx handle locals/fields keep their original no-copy/no-escape contract.
`ParsedModule.native_file_class` is an explicit host capability referring to a
validated declaration in that module, not a privilege inferred from its name or
origin string. IRx never discovers/parses frontend builtin source.

Both public factory forms share a `ResolvedClassConstruction` with a typed
`native_file` initialization descriptor containing the bound operands and native
field. Creation checks the native status in the caller before publishing the
handle and completing the phase, preserving active construction rollback.
Native-backed method metadata records the private receiver field so the backend
can pin the class receiver, check emptiness, and preserve real call-site I/O
locations without rediscovering class rules. Ordinary cleanup releases the raw
field once. Public references may alias, cross normal function boundaries, and
live in class fields; existing class aggregate/global/generator limits remain.

The optional registered file runtime still uses the opaque `irx_file_*` C ABI.
Every output slot is read only after successful status checking. Explicit close
is idempotent; final class release also frees the native wrapper. This does not
add catchable exceptions or general cross-frame fatal-error unwinding.

## Acyclic Class References

The class slice uses `ResourceKind.CLASS`, analyzed retain/move decisions,
slot-based mutable cleanup, argument/receiver pins, and concrete final-drop
callbacks. Three pointer header slots carry lifetime token, field descriptor,
and dispatch. The opaque native token stores reference count, phase progress,
and callback; LLVM never models its C layout. Each owned reference releases
once. Nullable field references allow retain/release of null, but access is
checked. Last release always consumes payload/token even on callback error.

Owned string/file/class fields drop in reverse canonical storage phases, after
each completed phase's `__del__`. Partial construction skips incomplete hooks
but releases all initialized fields. Native field-release errors preserve the
first status and continue other field releases. Source hook bodies cannot
escape/resurrect `self`; fatal called code still does not unwind callers.
String-field reads take owned snapshots so later expression effects cannot
invalidate an evaluated string pointer. Reference counts are non-atomic, and
cyclic schemas (including subtype edges) are rejected. General containers,
generator capture, global owners, and external class ownership remain out of
scope.

## Named Calls And Default Arguments

Named operands receive the same borrow/escape checks and lifetime pins as
positional operands. Calls evaluate/pin the receiver, evaluate supplied values
in source order, then fill omitted defaults in declaration order using resolved
parameter symbols. The completed values are emitted in positional ABI order.
Class and string-field snapshots must survive later keyword/default effects.
Public File method lowering consumes this same binding plan while retaining
caller-side native status checks and locations. No new native ABI, implicit
unwinding, cyclic ownership, or raw file-handle escape is introduced.
