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

Non-nullable scalar integer addition, subtraction, and multiplication use modulo
`2^N` arithmetic for an `N`-bit result. Scalar integer narrowing discards high
bits and therefore uses the same modulo rule. These operations do not trap on
overflow and optimization must not assume that signed overflow is impossible.
The compiled datatype conformance module covers signed boundary wrap,
subtraction wrap, multiplication wrap, and narrowing.

[Nullable and Series arithmetic](collections.md#nullable-scalars-and-series-expressions)
instead uses checked integer operations and explicit null propagation.

### Integer division and remainder failures

Signed integer division truncates toward zero. Integer division or remainder
fails before executing the LLVM operation when the divisor is zero. Signed
minimum divided by or reduced modulo negative one also fails because its
quotient is not representable. Failure emits the machine-readable
`ARX_RUNTIME_FAIL` record with code `ARX-RUNTIME-ARITHMETIC-001` and exits with
status 1. The same guards apply to signed and unsigned scalar widths supported
by the compiler. Floating-point division and vector division remain outside this
rule until their non-finite and per-lane behavior is specified.

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
`--traceback` is an explicit developer opt-in. Compiled assertion failure uses
the versioned `ARX_ASSERT_FAIL` stderr record and exits nonzero. Fatal checked
runtime operations use the versioned `ARX_RUNTIME_FAIL` record and an
operation-specific stable code. Allocation failure and general language-level
panic propagation remain undecided and are therefore not yet stable semantics.

### Compatibility identifiers

- language draft: `0.1.0`;
- source edition: `2026-preview`;
- compiler diagnostic JSON schema: `1`;
- RecordBatch native C ABI: `1`.

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
