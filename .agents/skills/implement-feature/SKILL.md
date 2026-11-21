---
name: implement-feature
description: Implement a scoped Arx feature across the necessary frontend, ASTx, semantic, LLVM and native boundaries. Use for approved feature implementations.
---

# Implement an Arx feature

Apply [minimal-change](../minimal-change/SKILL.md), [implementation-planning](../implementation-planning/SKILL.md) for nontrivial work, and [arx-architecture](../arx-architecture/SKILL.md).

1. Confirm the user-visible behavior and narrow acceptance criteria. Compare existing API/syntax and support before proposing anything new.
2. Identify the **minimum complete vertical slice**. Add a new ASTx node only if reusable modeling truly requires it.
3. Update lexical syntax manifest/parser when syntax changes. Resolve meaning, types, symbols, conversions, imports and native needs in IRx analysis.
4. Lower using semantic sidecars/compilation session only. Register native features and use Arrow-first mechanisms where the operation requires them. Do not claim that lexer or ASTx support alone is an implemented feature.
5. Update only affected callers/exports and required source docstrings. Extend existing tests rather than create redundant suites; add a representative executable boundary check when needed.
6. Run the narrowest applicable checks first, then tests on changed boundaries; verify LLVM IR and native ownership/status where relevant.
7. Stop at the accepted feature slice. Report supported and unsupported cases and exact validation.

Do not spin up a future-oriented abstraction, broad migration, benchmark suite, documentation page, or new CI job unless it is directly necessary or explicitly requested. When genuinely required, explain why.
