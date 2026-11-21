---
name: api-design
description: Design minimal, consistent Arx public Python and .x APIs with clear semantics, typing, visibility and correct package exports. Use for new or changed public APIs.
---

# Arx and Python API design

Use when proposing or changing public functions, types, methods, builtins, protocols, or package exports. First inspect the nearest existing API and its callers; preserve existing behavior outside the request.

Use Python's common-case ergonomics as a reference, **not** as a compatibility specification. Prefer predictable names, safe defaults, well-typed options, clear return meanings, and consistent errors. Put broadly universal operations in a small builtin surface; use focused imported stdlib modules for shared algorithms and type methods for natural type-specific behavior.

Avoid redundant aliases and synonymous public entry points. Introduce interfaces or protocols only for a concrete supported use case. Distinguish runtime/semantic support from surface syntax and ASTx modeling. Check whether names conflict with existing symbols, imports, or generated exports.

Keep source Douki contracts accurate and provide a short common-case example in the PR or existing executable tests if needed. Do not create independent API catalog pages. Before changing a public name, establish its semantic reason and update actual affected callers; pre-2.0 Arx does not require compatibility shims by default. Keep native ABI producer/consumer consistency even for intentional breaking changes.

Follow [minimal-change](../minimal-change/SKILL.md) and [language-design](../language-design/SKILL.md).
