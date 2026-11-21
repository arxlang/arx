---
name: native-runtime-design
description:
  Design and review IRx native runtime features, Arrow opaque C ABI, statuses,
  ownership, cleanup and sanitizer verification. Use for native features.
---

# Native feature and C ABI implementation

**Use for Arrow C++ glue, resource lifetimes, C ABI, linker/native feature
changes.** Read [cpp-code-style](../cpp-code-style/SKILL.md) when editing C++
sources, headers or C interfaces, and
[arrow-first-design](../arrow-first-design/SKILL.md) when changing data
representations, compute semantics or interchange contracts.

## Work backward from the call contract

Find one existing typed native operation in the IRx runtime, its analyzed plan,
feature registration, LLVM call site and C++ symbol. Before changing signatures
write down:

| Contract      | Questions to resolve                                                    |
| ------------- | ----------------------------------------------------------------------- |
| Inputs        | Type/shape/nullable? borrowed or owned? valid until when?               |
| Return status | What codes mean success/error? Is there a diagnostic channel?           |
| Outputs       | Initial state on failure? when may caller read it? who releases?        |
| Transfer      | What consumes ownership? when is hand-off committed?                    |
| Cleanup       | On every error path, who releases each native handle?                   |
| Version       | Which exact Arrow C++ headers, libs, PyArrow and source artifact match? |
| Linking       | Which registered runtime feature provides the symbol?                   |

## Implementation boundaries

1. Make the semantic plan _closed_ in `irx.analysis` (call identity, exact
   conversions/options, null/overflow/error contract, required feature).
2. Use the registered feature mechanism. Do not add implicit C++ dependencies to
   general lowering.
3. Keep Arrow C++ behind opaque handles and stable `irx_arrow_*` / `irx_rb_*` C
   ABI functions. LLVM passes addresses/status/results; it never models Arrow
   `std::` types or object offsets.
4. Prefer typed catalog and existing compute dispatcher instead of a new wrapper
   per operation; C Data/C Stream exchanges data, not arbitrary C++ method
   calls.
5. Initialize output slots; check call status before loading any output. Handle
   C++ exceptions at ABI boundary, release resources deterministically, and
   prevent use-after-free/double-free.
6. Match any changed producer signature with **all** LLVM/Python/native
   consumers and release packaging.

## Failure probes

- Null handle and empty array, null element in valid array.
- Wrong dtype, width/shape mismatch and unsupported options.
- Arithmetic overflow or IEEE special-value behavior.
- Native failure _before_ output initialization, partial allocation failure, and
  cleanup after status error.
- Transfer, escaped owner, repeated release and concurrent usage where relevant.
- PyArrow interchange and independently installed consumers where public data
  path is affected.

Use existing native tests and `makim irx.test-sanitizers` with appropriate Clang
prerequisites. Verify LLVM module parsing and linked execution. Run only
affected tests first; expand when ABI change reaches multiple packages. Do not
create a generalized FFI or Arrow compatibility framework by default.

**Exit:** documented ownership/status contract in code, working feature
registration, verified producer/consumer, and precise report of sanitizer/ABI
checks run.
