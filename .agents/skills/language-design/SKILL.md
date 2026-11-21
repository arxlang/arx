---
name: language-design
description: Design minimal and coherent Arx syntax, builtins and stdlib behavior using Python ergonomics without assuming compatibility. Use for language proposals.
---

# Arx language and library design

Use when changing `.x` syntax, builtin behavior, protocols, type-system surface, standard-library APIs, or user-facing diagnostics.

Prioritize a simple, predictable, Python-familiar experience, but do not treat Python compatibility as Arx's specification. Evaluate common-case usage before choosing a public name or shape. Favor a small universal builtin set, explicitly imported shared stdlib modules, and value-specific methods where natural. Ensure safe defaults, typed options, clear return and error contracts.

Arx is general-purpose and Arrow-first for data; maintain the distinction between language semantics and Arrow physical representations. An ASTx type is not proof of parser, analysis, or lowering support. Check the current syntax manifest and tests before asserting that a construct exists; preserve significant two-space indentation and Douki module docstrings.

Prefer one canonical call shape. Avoid speculative protocol layers, duplicate aliases, silent conversion, undocumented unsupported options, or premature complexity. Before Arx 2.0 intentional API changes may be breaking: update affected consumers consistently, without unrequested deprecation shims.

Use [api-design](../api-design/SKILL.md), [compiler-design](../compiler-design/SKILL.md), and [minimal-change](../minimal-change/SKILL.md). Implement only the approved useful slice; suggest unrelated ideas separately.
