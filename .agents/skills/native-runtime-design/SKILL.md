---
name: native-runtime-design
description: Design and review IRx native runtime features, Arrow opaque C ABI, statuses, ownership, cleanup and sanitizer verification. Use for native features.
---

# Native runtime and ABI safety

Use when changing IRx native features, Arrow C++ glue, linking, FFI, allocation, or released artifact dependencies. Follow [arrow-first-design](../arrow-first-design/SKILL.md) and [cpp-code-style](../cpp-code-style/SKILL.md).

Only activate native code via registered runtime features. Never embed Arrow C++ layouts in LLVM: use opaque handles behind existing `irx_arrow_*` and `irx_rb_*` C ABI APIs. Reuse typed operation catalogs and the shared dispatcher rather than adding a new handwritten wrapper for each kernel.

For every native call specify: which party owns each input/output, whether a handle is borrowed/transferred, its permitted lifetime, how it is released on success/failure, status codes, output-slot initialization and success-only reads. Treat C++ exceptions and failure statuses explicitly at the ABI boundary; preserve cleanup and avoid use-after-free or double releases.

A new operation must account for relevant null/empty cases, type and shape mismatch, overflow, validities, and PyArrow interchange. Reuse the existing native tests; for affected ownership and UB cases run `makim irx.test-sanitizers` where toolchain permits. Verify IR and linked execution for new feature dependencies.

Never rewrite unrelated native build wiring, update the lockfile by hand, introduce implicit toolchain requirements, or claim a new Arrow version is deployed without checking the current manifests.
