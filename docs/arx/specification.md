# Arx Language Specification Status

## Status

This page is the starting point for the normative Arx 1 specification. It is a
**working draft**, not a stability promise. The checked-in compiler and the
[capability matrix](capability-matrix.md) remain the executable evidence for
current behavior until every section below is complete and covered by the
versioned conformance suite.

Package release numbers and the language specification version are separate. The
current packages report `1.24.1`. This document is specification draft `0.1.0`
for the non-stable `2026-preview` edition; no stable Arx 1 language
specification or edition has been published yet.

## Candidate production scope

The initial production candidate is a statically typed, ahead-of-time compiled
language for native command-line and data-oriented applications. The first
support target will be selected from the tested platform matrix; platforms not
in that matrix are experimental even when they happen to compile.

The candidate stable package surface is:

| Component                                        | Candidate tier                                                                                          |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Arx source syntax, frontend, and CLI             | stable after the GA gates pass                                                                          |
| ASTx nodes required by Arx 1                     | stable cross-package contract                                                                           |
| IRx semantic and lowering APIs required by Arx 1 | stable internal compiler contract; public Python stability remains separately scoped                    |
| ArxPy compiler façade                            | pre-stable parse/check/compile/run API; cancellation, targets, queries, and compatibility freeze remain |
| ArxJIT                                           | experimental until decorated calls compile and dispatch natively                                        |
| AIX                                              | excluded toy experiment                                                                                 |

Self-hosting, every ASTx node, a general query engine, and an interactive shell
are not requirements for the first production release.

## Lexical contract already enforced

- Source is Unicode text supplied through the Arx input layer.
- Files must be valid UTF-8 and source is limited to 4 MiB of UTF-8 bytes.
- Indentation is significant and uses two ASCII spaces per nesting level.
- Tab characters outside quoted literal contents are rejected by the lexer.
- The lexical manifest is `packages/arx/src/arx/lexer/syntax.json`; a manifest
  entry only reserves or tokenizes a form and does not prove parser or backend
  support.
- Every committed `.x` module starts with a valid line-one Douki YAML module
  docstring. Docstrings are validated but are not currently emitted into ASTx or
  IRx.
- Token start locations use one-based lines and Unicode code-point columns.
- The lexer rejects nesting deeper than 256 delimiters, numeric tokens longer
  than 4,096 characters, and inputs exceeding 250,000 non-EOF tokens. These
  resource limits are compiler-version contracts until the language
  compatibility policy is frozen.

See [Lexical Syntax](syntax.md) and [Docstrings](docstrings.md) for the current
descriptive reference.

## Candidate core language

The candidate subset is limited to constructs with an end-to-end row in the
capability matrix:

- typed functions, arguments, defaults, returns, extern declarations, and the
  currently supported template subset;
- explicit typed variables and assignments;
- scalar Boolean, integer, floating-point, character, and string forms that have
  semantic and lowering coverage;
- `if`/`else`, `while`, count-based `for`, and supported list iteration;
- modules and compiler-owned import resolution from one entry module;
- the currently documented class subset;
- lists, fixed-shape numeric tensors, and static-schema DataFrames only to the
  extent explicitly marked in the capability matrix;
- assertions and compiled test functions.

Reserved declarations such as general `const` and operator declarations are not
part of this candidate unless their complete pipeline rows are closed.

## Normative decisions still required

The following are specification blockers. Current implementation behavior must
not be promoted to a compatibility promise until each decision is made,
implemented consistently, and represented in conformance tests:

1. floating-point-to-integer overflow and non-finite narrowing behavior;
2. floating-point division/remainder by zero and non-finite results;
3. floating-point mode, NaN comparison, and fast-math guarantees;
4. Unicode character and string indexing, length, equality, and formatting;
5. left-to-right evaluation and Boolean short-circuit rules;
6. module initialization order, cycles, and repeated imports;
7. allocation failure, assertion failure, panic/status, and process exit rules;
8. copy, move, borrow, escape, and destruction behavior for owning values other
   than the scalar dynamic-list subset specified below;
9. class identity, layout, construction, destruction, inheritance, and ABI;
10. foreign calling conventions, supported FFI types, and ownership transfer;
11. tensor shape compatibility and runtime validation;
12. source, package API, runtime C ABI, and artifact compatibility policy.

Each decision must be recorded next to its tests. Lowering consumes semantic
metadata for the decision and must not rediscover it.

## Decided preview semantics

The following rules are normative for draft `0.1.0` and have executable
coverage. They may still change through the preview compatibility process, but
the implementation and this document must change together.

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

Fixed-width integer addition, subtraction, and multiplication use modulo `2^N`
arithmetic for an `N`-bit result. Narrowing to an integer discards high bits and
therefore uses the same modulo rule. These operations do not trap on overflow
and optimization must not assume that signed overflow is impossible. The
compiled datatype conformance module covers signed boundary wrap, subtraction
wrap, multiplication wrap, and narrowing.

### Integer division and remainder failures

Signed integer division truncates toward zero. Integer division or remainder
fails before executing the LLVM operation when the divisor is zero. Signed
minimum divided by or reduced modulo negative one also fails because its
quotient is not representable. Failure emits the machine-readable
`ARX_RUNTIME_FAIL` record with code `ARX-RUNTIME-ARITHMETIC-001` and exits with
status 1. The same guards apply to signed and unsigned scalar widths supported
by the compiler. Floating-point division and vector division remain outside this
rule until their non-finite and per-lane behavior is specified.

### Scalar dynamic-list ownership

Dynamic lists with one scalar element type use a move-only ownership model. List
creation, list comprehensions, and list-returning calls produce an owner. A
local declaration consumes that owner. Function list parameters and ordinary
identifier expressions borrow storage and do not acquire a release obligation.

Assignment to an owned local consumes a fresh owner and releases the previous
storage first. Returning a fresh list or an owned local moves the release
obligation to the caller. Returning borrowed parameter storage or a static list
literal, copying a borrowed list into a local, and appending through borrowed or
static storage are `IRX-S013` semantic errors.

Owned local and non-transferred temporary storage is destroyed on normal block
fallthrough, scalar return, `break`, and `continue`. Storage moved through a
return is excluded from callee cleanup and becomes the caller's obligation.
Literal-list storage is static and is never dynamically destroyed. It may be
indexed or iterated directly, but it cannot initialize a dynamic local, cross a
function-call boundary, or serve as a list parameter default. Owning list
elements, owned list locals in generators, object-field ownership, and a
user-visible copy operation are outside this preview rule.

### String storage and ownership

String literals, default empty strings, and `type(...)` results point to
immutable process-lifetime storage. Concatenation, numeric-to-string casts, and
calls to defined Arx functions returning `str` produce owned heap storage.
String parameters and ordinary identifier expressions borrow their source
binding for the duration of an expression or call.

An owned local consumes a fresh heap result and releases it on lexical
fallthrough, `return`, `break`, and `continue`. Replacing an owned local
releases the previous pointer before storing a fresh owner. Returning an owned
local moves the release obligation to the caller; returning static storage
copies it into checked heap storage so every string-returning Arx call has one
caller-owned result. Concatenation and formatting allocations fail with a
versioned `ARX_RUNTIME_FAIL` record instead of dereferencing a null pointer.

Static bindings may alias or replace other static strings without cleanup.
Changing a binding between static and owned storage, aliasing a borrowed
parameter into an owned local, returning a borrowed parameter, identity-casting
an owned string, storing owned strings in object fields or generator frames, and
accepting string results from an external function without an explicit ownership
ABI are `IRX-S013` errors in this preview.

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
Arx 1, a package release may revise them only with updated conformance tests,
capability documentation, and migration notes. Stable-edition deprecation
duration and the non-RecordBatch runtime ABI remain release gates.

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

## Compatibility and editions

Before the first stable language release, the project will define:

- the language specification version and edition identifier;
- which source changes require a new edition;
- the deprecation window and warning behavior;
- package API and native C ABI versioning;
- the supported compiler/toolchain and artifact matrix;
- the lifetime and security support period for a release line.

Until then, the language remains pre-production and source compatibility may
change between lockstep package releases with documented migration notes.
