---
name: cpp-code-style
description: Apply Arx native C++20 style, RAII, ownership and opaque ABI boundary rules. Use when editing C++ sources, headers or C interfaces.
---

# C++ native implementation conventions

**Use for native C++ and C ABI changes**, including `irx_arrow_*`/`irx_rb_*` integration. Apply [minimal-change](../minimal-change/SKILL.md). Read [native-runtime-design](../native-runtime-design/SKILL.md) when changing C ABI, ownership/lifetime, status/output or native feature registration/linking contracts.

## Before editing

Locate the existing native implementation and closest comparable operation. Inspect its header signatures, error/status conventions, feature registration, caller in LLVM lowering, and existing sanitizer coverage. Follow source-local naming/formatting and configured C++20 rather than introducing a new style or tooling dependency.

## Style and safety

- Prefer minimal functions with one responsibility and clear ownership boundaries. Use RAII, scoped cleanup, explicit `const` references and checked narrowing. Avoid raw owning allocations when a managed type already exists.
- Prefer early validation and early exit to deep conditional chains; preserve scopes when necessary for C++ resource lifetime.
- Avoid global mutable state, unnecessary templates, dynamic polymorphism, vague status enums, and generic catch-all behavior that hides failures.
- Add comments for ownership and non-obvious ABI invariants, not mechanical restatements of code.
- Keep exceptions from leaking across `extern "C"` boundaries; translate failures to the established status contract and initialize outputs safely.

## Native ABI checklist

For each new or changed callable, answer all questions before lowering:

| Question | Required answer |
| --- | --- |
| Inputs | Borrowed or owned? Can they be null or empty? |
| Outputs | Who allocates and releases? What is output state on error? |
| Ownership | Is transfer explicit and atomic? What handles remain valid? |
| Status | What does success mean? Does the caller inspect before reading output? |
| Exceptions | Is C++ failure safely converted to a status? |
| Data | How do validity bits, shape/type mismatches, overflow and empty arrays behave? |
| Feature | Which registered runtime feature makes the symbols linkable? |

**Never** embed Arrow C++ object layouts, vtables, or offsets in LLVM IR. Pass opaque handles through the established C ABI. Prefer registered typed Arrow compute dispatch over handwritten wrappers per kernel. C Data/C Stream is an interchange contract, not arbitrary foreign-call support.

## Verification

Use existing native ABI tests and `makim irx.test-sanitizers` for affected ownership/UB paths. Test success, null/empty, invalid arguments, error status and release paths as applicable. Avoid creating a new C++ test harness or benchmark unless the requested change actually requires one.

If the ABI changed, verify both producer **and** LLVM consumer, exported symbols, and linking. Report toolchain constraints rather than claiming sanitizers ran.
