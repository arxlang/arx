# Arx Preview Contracts

These safety and compatibility decisions describe the non-stable `2026-preview`
edition (language draft `0.1.0`). They are not a complete language
specification. The [capability matrix](capability-matrix.md) is the single
support summary; executable conformance lives in the compiler tests.

## Arithmetic and evaluation

### Boolean evaluation

- `&&` and `||` require Boolean operands.
- The left operand is evaluated first.
- For `lhs && rhs`, `rhs` is evaluated only when `lhs` is `true`.
- For `lhs || rhs`, `rhs` is evaluated only when `lhs` is `false`.

`packages/arx/tests/arx/test_datatypes.x` contains the black-box conformance
case: the skipped operand deliberately asserts false. IRx also verifies that
lowering uses conditional blocks and a merge value rather than eager LLVM
`and`/`or` instructions.

### Fixed-width integer overflow

Fixed-width signed and unsigned 8–64-bit integer `+`, `-`, `*`, negation, and
supported increment/decrement operations are checked in every build. IRx
fixed-width range induction is checked too; the stdlib `range` helper uses wider
endpoint arithmetic to terminate safely on an overshooting step. Overflow fails
before storing or publishing a result; an unused expression is still checked.
Provably evaluated invalid constant operations are semantic errors. Untaken
branches and short-circuited operands do not execute checks.

Implicit numeric conversions preserve the **entire source type's domain**. Mixed
operands use the smallest supported lossless common domain: `i32 + u32` computes
in `i64`, and `i32 + f32` in `f64`; `i64 + u64` and `i64 + f64` require an
explicit conversion. A destination annotation never widens a computation
retroactively. Same-type templates keep their selected type; widen operands or
select `math.square<i64>(narrow)` before multiplication, not afterward.

Source integer literals use the declared/argument/peer type when representable,
otherwise default to `i32`, then `i64`. Uncontextualized floating literals
default to `f32`. Decimal literals retain their exact value until type
selection, then round directly to the chosen binary format, nearest with ties to
even. Explicitly typed ASTx literals are never recontextualized. Generic
inference uses concrete arguments before contextualizing literal arguments,
independently of argument order; literals do not make conflicting concrete
same-`T` arguments compatible.

`cast(value, Type)` checks integer range, including equal-width signedness
changes. Float-to-integer casts truncate toward zero, then require a finite,
representable result. Explicit integer-to-float and float-narrowing casts may
round; finite input must not become infinity. Existing floating NaN, infinity,
signed zero, and ordinary IEEE floating arithmetic are preserved. Implicit
integer-to-float conversions may not discard integer precision.

Intentional modulo arithmetic requires `wrapping_add`, `wrapping_sub`,
`wrapping_mul`, or `wrapping_cast(value, IntegerType)`. Binary wrapping operands
must have the same integer type, or an explicit lossless specialization such as
`wrapping_add<i64>(narrow, 1)`. Boolean and floating operands are rejected.
These forms do not change surrounding expressions' checked behavior.

### Integer division and remainder failures

Signed integer division truncates toward zero. Division and remainder reject
zero divisors and signed minimum with negative one before LLVM executes the
operation. Integer SIMD lowering checks every supplied active lane; no masked
source-vector API is implied. Floating-point division follows IEEE behavior.

Dynamic integer zero divisors raise `ZeroDivisionError`; out-of-range arithmetic
and conversions raise `OverflowError`, at every optimization level. Diagnostic
codes remain `ARX-RUNTIME-ARITHMETIC-001` and `ARX-RUNTIME-CONVERSION-001`.
These failures propagate through generated cleanup edges and can be caught;
uncaught exceptions produce structured reports and a nonzero exit status.
Statically invalid expressions remain compile-time diagnostics. See the
[exception support boundary](../support-matrix.md#exception-capability-boundary).

[Nullable and Series arithmetic](collections.md#nullable-scalars-and-series-expressions)
retains checked Arrow kernels, status checking, null propagation, and checked
reduction accumulators. Nullable scalar casts skip invalid payloads entirely.
Tensor element operations use scalar checks; bulk tensor arithmetic and
nonidentity Series/tensor casts are rejected rather than reinterpreting storage.
List length/search results must fit their public `i32` domain. Numeric runtime
unions require lossless shared storage; generic union bounds are membership
constraints and need no runtime storage. Raw FFI internals and external native
functions remain outside these language guarantees.

## Ownership

The [runtime ownership contract](../irx/runtime-ownership.md) owns the detailed
create/borrow/move/release rules for lists, strings, files, and class
references. Dynamic lists are move-only and cleaned up on ordinary lexical
exits, not process-lifetime allocations. Shared class references follow a
different model. Use the [class lifecycle guide](classes.md) for construction
and field ownership, and the [file guide](file-io.md) for shared cursor and
close behavior.

IRx cleanup paths for `break`/`continue` or generators do not establish Arx
source support for those constructs. Fatal errors do not generally unwind caller
frames. Do not depend on automatic cleanup to confirm successful writer
finalization; follow the [CSV](csv.md) or [Parquet](parquet.md) close contract.

## Modules and failures

### Module graph failures

One entry module identifies a compiler-owned, canonical dependency graph.
Missing modules are `IRX-S011` failures and import cycles are `IRX-S012`
failures; a cycle is never executed or initialized partially. A canonical module
is resolved and analyzed once per compilation session. Module-level runtime
initialization order remains outside the stable subset until Arx admits and
specifies executable module-level statements.

### Compiler and process failures

Expected source/compiler failures exit the CLI with status 1, CLI usage failures
use status 2, and sanitized internal compiler failures use status 70.
`--traceback` is an explicit developer opt-in. Compiled assertions raise
`AssertionError`. Uncaught exceptions emit `ARX_EXCEPTION` records with stable
operation codes and `ARX_EXCEPTION_FRAME` records for recorded call sites, then
exit nonzero. The test runner and ArxPy decode these reports without treating
completed subprocess failures as Python compiler errors. Unrecoverable native or
exception-machinery allocation failures retain the `ARX_RUNTIME_FAIL` fallback;
they do not promise recovery or cleanup.

### Compatibility identifiers

- language draft: `0.1.0`;
- source edition: `2026-preview`;
- compiler diagnostic JSON schema: `1`;
- RecordBatch native C ABI: `2`.

The language draft and preview edition do not grant source compatibility. Before
Arx 2.0, replace APIs within the requested scope and update callers, tests,
source contracts, and necessary guides together. Record intentional breaking
changes in concise release notes rather than parallel deprecated API
documentation. Native ABI producers and consumers must remain aligned.

## Diagnostics contract

Stable compiler failures will have a code, phase, message, and a trustworthy
optional source location. Normal CLI use renders expected Arx and IRx failures
without a Python traceback and exits nonzero. Unexpected internal failures are
not relabeled as user errors.

The source loader emits `ARX-SOURCE-*`, the lexer emits `ARX-LEX-*`, the parser
emits `ARX-PARSE-*`, and IRx formats its diagnostic families as `IRX-*`.
`--diagnostic-format json` emits schema version 1 for structured compiler-phase
failures. The complete stable-code catalog remains GA work; schema versions must
be checked rather than inferred.

## Decisions still required

A stable specification still needs floating-point non-finite/NaN and narrowing
rules, broader Unicode operations, general resource/error propagation, FFI and
artifact guarantees, and a versioned conformance suite. Do not promote a preview
behavior to a compatibility promise without that evidence.

At Arx 2.0, explicitly define source/package/native ABI compatibility, edition
changes, any deprecation policy, supported toolchains, and release support
periods. The pre-2.0 policy must not silently continue afterward.
