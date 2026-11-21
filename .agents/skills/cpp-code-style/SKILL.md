---
name: cpp-code-style
description: Apply Arx native C++20 style, RAII, ownership and opaque ABI boundary rules. Use when editing C++ sources, headers or C interfaces.
---

# C++ native engineering standards

Use when editing Arx native C++ sources or headers. Follow the local conventions and currently configured C++20 toolchain rather than introducing a new formatter or style system.

Prefer small, self-contained operations; explicit `const` and ownership, RAII, clear lifetime boundaries, checked conversions, and deterministic cleanup. Avoid unsafe casts, unchecked arithmetic, catch-all exception suppression, global mutable state, and unnecessary templates or polymorphic abstractions. Keep conditionals shallow using validation-first guards where clearer; do not force unnatural restructuring.

Arx's LLVM interface must never depend on Arrow C++ object layouts. Interact through registered native features, opaque handles, and existing `irx_arrow_*` / `irx_rb_*` C ABI entry points. Respect linkage/visibility conventions. Define caller-versus-callee ownership, borrowed handles, transfer, release behavior, return statuses, and output-slot initialization explicitly. Only read outputs after success; preserve safe cleanup on every error path and across exception boundaries.

Prefer Arrow APIs for supported storage and computation instead of reimplementing kernels; see [arrow-first-design](../arrow-first-design/SKILL.md) and [native-runtime-design](../native-runtime-design/SKILL.md). Test changed ABI edges and ownership/error/null paths using existing tests and `makim irx.test-sanitizers` when applicable.

Do not add unrelated C++ refactors, new native wrappers, build flags, dependencies, benchmarks, or documentation. If a naming or structure change is needed for safety or semantics, make the smallest coherent change.
