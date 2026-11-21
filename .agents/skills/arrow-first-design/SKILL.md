---
name: arrow-first-design
description: Choose Arrow-first types, data representations and compute operations while preserving IRx language semantics and ABI safety. Use for data and numeric feature design.
---

# Arrow-first data and computation design

Use before adding a data type, storage layout, numerical operation, collection kernel, or interoperability feature.

**Arrow first, not Arrow only.** Investigate Arrow's logical types, scalar/array/record-batch representations, validity/null semantics, `Datum`, compute kernels, memory model, and C Data/C Stream interchange. Reuse an Arrow construct when it implements the approved Arx semantics and has a safe native integration. Do not invent parallel data representations or per-operation C++ wrappers without a concrete incompatibility.

Distinguish three layers: IRx owns language-level type meaning; ASTx models relevant syntax/types; Arrow is the preferred data representation and computation engine. Not every semantic type (functions, generics, control-flow types) should be forced into an Arrow storage layout. Register concrete runtime capabilities and resolve typed operation plans in IRx analysis, not via unchecked string kernels in lowering.

Check signedness/width, overflow, null propagation, empty inputs, shapes, IEEE floating values and signed zero, ownership, conversions, errors, and scalar versus Series behavior. Reuse the shared typed compute dispatcher. Arrow kernels do not constitute a general query engine.

When Arrow lacks a compatible semantic contract, document the specific gap in the PR and use a reviewed LLVM/native/pure-Arx implementation; do not impose Arrow as a language capability ceiling. Keep the single-version Arrow/PyArrow/source ABI policy synchronized with manifests/lockfile, not stale prose. Consult [native-runtime-design](../native-runtime-design/SKILL.md) for handles and statuses.
