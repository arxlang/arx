# Runtime Ownership Inventory

## Status and purpose

This inventory was checked against the local IRx lowering and native runtime on
2026-09-01. It is the starting point for the Arx resource model, not yet a
complete production ownership specification. A resource may be promoted to the
stable language only after its create, borrow, transfer, escape, release, and
failure paths are represented here and enforced by semantic metadata and
lowering.

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

| Resource                                    | Creation/allocation                                 | Current release path                                                         | Current ownership state                    | Required work                                                                                                                |
| ------------------------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| Scalar values and literal aggregate storage | LLVM values, globals, or stack allocation           | Function/stack lifetime                                                      | Non-owning values                          | Specify overflow and invalid-operation behavior.                                                                             |
| Dynamic list backing bytes                  | `realloc` in `irx_list_append`                      | Idempotent `irx_list_destroy` exists but cleanup is not inserted by lowering | Process-lifetime leak in compiled programs | Add semantic owner/move rules, cleanup on every exit, and nested element destruction.                                        |
| Literal-list runtime view                   | Stack descriptor over stack/literal data            | Stack lifetime                                                               | Borrowed view                              | Prohibit escape and distinguish it from an owning dynamic list in metadata.                                                  |
| Concatenated string                         | `malloc` in generated `strcat_inline`               | None                                                                         | Untracked heap pointer                     | Define owned string representation, null/OOM checks, copy/move/return rules, and cleanup.                                    |
| Numeric/string formatting result            | `malloc` in `_snprintf_heap`                        | None                                                                         | Untracked heap pointer                     | Release after consuming print/format output or transfer into an owned string value.                                          |
| String literals and empty strings           | LLVM global constant                                | No release required                                                          | Immortal borrowed storage                  | Mark as non-owning so it is never passed to heap release.                                                                    |
| Class instance                              | `malloc` in `ClassConstruct` lowering               | None                                                                         | Untracked heap pointer                     | Define constructors, object owner/reference model, field destruction order, inheritance lifecycle, null/OOM checks, and ABI. |
| Generator frame                             | `malloc` in generator factory                       | No matching free found                                                       | Escaping opaque pointer                    | Add close/exhaustion/drop operation, cleanup captured owners, allocation checks, and double-close rules.                     |
| Buffer owner                                | Native `malloc`; optional external release callback | `irx_buffer_owner_release`                                                   | Reference-counted owner                    | Add sanitizer/fault tests and prove all retain/release/status paths, including interpreter/FFI failures.                     |
| Buffer view                                 | Native view plus owner handle                       | `irx_buffer_view_release`                                                    | Shared owner with borrowed byte range      | Enforce view lifetime and status checks at every lowering path.                                                              |
| Arrow schema                                | C++ handle owning shared Arrow schema               | `irx_arrow_schema_release`                                                   | Opaque owner                               | Audit every create failure and output slot; keep Python wrappers idempotent.                                                 |
| Arrow array builder                         | C++ unique builder handle                           | finish consumes or builder release                                           | Opaque owner with consuming finish         | Prove exactly-once consume/release on success and failure.                                                                   |
| Arrow array                                 | C++ handle with shared Arrow array                  | `irx_arrow_array_release`                                                    | Opaque shared-data owner                   | Document borrow/transfer for C Data Interface export/import.                                                                 |
| Arrow tensor builder                        | C++ unique builder handle                           | finish consumes or builder release                                           | Opaque owner with consuming finish         | Prove cleanup for append/shape/finish failures.                                                                              |
| Arrow tensor                                | C++ handle with shared buffer                       | `irx_arrow_tensor_release`                                                   | Opaque shared-data owner                   | Specify Arx return/argument/view ownership and shape validation.                                                             |
| Arrow table/DataFrame                       | C++ table handle                                    | `irx_arrow_table_release`                                                    | Opaque owner                               | Ensure all lowered construction paths release intermediate arrays and table results.                                         |
| Arrow Series/chunked array                  | C++ chunked-array handle                            | `irx_arrow_chunked_array_release`                                            | Opaque owner                               | Define whether field selection returns an owned handle or borrow; test parent release ordering.                              |
| RecordBatch type descriptor                 | C++ allocated descriptor                            | `irx_type_release`                                                           | Opaque owner                               | Keep local descriptor cleanup on every nested schema failure.                                                                |
| RecordBatch schema                          | C++ schema handle                                   | `irx_rb_schema_release`                                                      | Python wrapper owner                       | Partial-construction safety is implemented; add context-manager and explicit closed-state checks.                            |
| RecordBatch builder                         | C++ builder handle                                  | finish consumes native builder; wrapper release                              | Python wrapper owner                       | Specify wrapper behavior after finish and reject reuse deterministically.                                                    |
| RecordBatch batch                           | C++ shared RecordBatch handle                       | `irx_rb_batch_release`                                                       | Python wrapper owner                       | Retain idempotent release and reject access after release.                                                                   |
| RecordBatch stream writer                   | C++ writer and sink                                 | close plus `irx_rb_stream_writer_release`                                    | Python wrapper owner                       | Define close failure versus unconditional release; test both file and buffer errors.                                         |
| RecordBatch stream reader                   | C++ reader                                          | `irx_rb_stream_reader_close`                                                 | Python wrapper owner                       | Clarify whether close deletes the handle and make repeated close/access rules explicit.                                      |
| PyArrow interchange capsules                | Arrow C Data Interface callbacks                    | Arrow release callbacks                                                      | Transferred/shared by protocol             | Test both release orders, partial imports, and abandoned capsules.                                                           |

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

## Cleanup control flow

IRx already has `cleanup_stack` support used by context managers and emits
active cleanups on returns, `break`, and `continue`. Resource cleanup should
extend this mechanism only after semantic analysis states whether a value is an
owner, borrow, move, or escape. Required control-flow cases include:

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

1. Add ownership/escape records to IRx semantic sidecars.
2. Insert dynamic-list destruction from semantic ownership metadata on every
   normal, terminating, and transfer path.
3. Introduce an owned string representation instead of mixing globals and raw
   heap pointers under the same LLVM pointer type.
4. Add class and generator lifecycle operations before stabilizing either ABI.
5. Make Python wrappers reject use after release and support deterministic
   context management where useful.
6. Add allocator fault injection for every create/append/finish path.
7. Run compiled ownership programs under ASan, LSan, and UBSan.
8. Add long-running create/use/release loops with bounded memory growth.
9. Test output slots remain unread on all injected non-success statuses.
10. Document any intentionally immortal allocation; process-lifetime leakage is
    not an implicit ownership policy.
