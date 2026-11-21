---
name: arrow-first-design
description: Choose Arrow-first types, data representations and compute operations while preserving IRx language semantics and ABI safety. Use for data and numeric feature design.
---

# Arrow-first types, storage and computation

**Use before adding a data type, column/Series representation, data kernel, math operation or interchange contract.** Consult [arx-architecture](../arx-architecture/SKILL.md) when package ownership or cross-package boundaries change, and [native-runtime-design](../native-runtime-design/SKILL.md) when C ABI, native ownership/status or feature registration/linking contracts change.

**Rule:** Arrow first, **not** Arrow only. Arx is a general-purpose LLVM language. IRx owns language type *meaning*, ASTx models reusable language-neutral types, Arrow is the preferred runtime data/compute representation when it satisfies Arx's semantics. Never force function/generic/control-flow types into physical Arrow storage.

## Type/operation design procedure

1. **Specify semantics before backend choice.** Determine logical type, widths, nullable/non-nullable behavior, scalar versus Series rules, operations, ownership, conversion, error behavior and public call shape.
2. **Check Arrow capabilities:** logical types, Scalar, Array, Datum, RecordBatch, validity, memory/pool behavior, compute kernel and C Data/C Stream interchange. Do not introduce a parallel implementation without demonstrating the gap.
3. **Compare semantics:** integer overflow, signedness/width, IEEE NaN/infinity/signed zero, floating error bounds, null propagation, shapes, conversion and errors. "Arrow has a kernel" is not proof it matches Arx's public contract.
4. **Resolve approved call in IRx analysis:** typed callable identity, allowed argument shapes/types, conversions/options, output type and required registered native feature. Reuse operation catalog/typed compute plan. No unchecked arbitrary kernel string dispatch from Arx source.
5. **Lower to existing shared native dispatcher:** opaque C ABI handles and status/out parameters only. A second kernel should not automatically require a second handwritten C++ glue wrapper.
6. **Verify applicable boundaries:** semantic analysis, compiled scalar and Series behavior, null and invalid shapes, ownership/error cleanup, PyArrow interchange and an independently installed `.x`-only consumer if the feature is public.

## Choice matrix

| Situation | Decision |
| --- | --- |
| Compatible Arrow logical/storage type exists | Reuse through an explicit Arx semantic mapping |
| Typed approved Arrow compute kernel matches contract | Use shared registered dispatcher |
| Arrow scalar boxing adds overhead | Measure before introducing a conformant specialized register path; LLVM primitive transport is already allowed |
| Arrow kernel differs in null/overflow semantics | Reject, adapt with checked semantics, or choose reviewed alternative; never silently change language behavior |
| No compatible Arrow contract | Explain concrete gap in PR; reviewed LLVM/native/pure-Arx implementation is allowed |
| New Arrow version requested | Verify exact paired PyArrow and `arx-arrowcpp-sources` versions, source headers, native caches, manifests and root lockfile; never guess a published artifact |

## Existing architecture and anti-patterns

See `packages/irx/src/irx/analysis/resolved_nodes.py`, semantic operation catalog/compute logic under IRx, runtime feature registration and `irx_arrow_*`/ `irx_rb_*` C ABI. Current `AGENTS.md` describes the single-version migration policy; **read current manifests** for deployed pins rather than copying a dated target.

**Avoid:** inventing an Arx-only data buffer by default, encoding C++ Arrow struct layouts in LLVM, treating Arrow kernels as a general query engine, scalar-only custom math without evaluation, compiling unsupported kernel names as strings, or promising native dispatch from ArxJIT.

**Exit:** semantically conformant representation choice with verified boundary tests, or a clear reason Arrow could not be reused.
