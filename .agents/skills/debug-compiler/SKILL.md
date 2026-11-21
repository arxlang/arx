---
name: debug-compiler
description: Investigate Arx lexing, parsing, semantic, LLVM or native compiler failures using minimal reproducers and phase-specific diagnostics. Use for compiler debugging.
---

# Debug an Arx compiler failure

Use [compiler-design](../compiler-design/SKILL.md) and [minimal-change](../minimal-change/SKILL.md).

1. Establish the failing invocation, exact source or test, toolchain, branch, and error. Capture the actual evidence rather than guessing.
2. Reproduce with the smallest meaningful `.x` program; preserve required Douki module docstring and two-space indentation. For ArxJIT reproduce the real Python extraction/signature boundary.
3. Identify the first failing phase: source/lexer → parser → ASTx → IRx analysis → LLVM lowering → native feature → linker/execution.
4. Inspect intermediate evidence with existing CLI options (`--show-tokens`, `--show-ast`, `--show-llvm-ir`) when applicable. For IR failures validate the generated module with LLVM parsing/verification. For native issues examine status/ownership and use sanitizers if available.
5. Determine root cause at its owning layer. Do not conceal unsupported constructs with generic nodes, broad exceptions, guessed types or invented locations.
6. Reuse existing focused tests; add or extend an assertion only for a distinct uncovered regression. Run narrow analysis/parser/codegen and cross-stage tests as necessary.
7. Review changed behavior and report exact checks, root cause, fix and remaining limitations.

Do not add debug-only code, diagnostic tooling, new benchmarks, or cleanup unrelated code in the submitted diff. If the error cannot be reproduced, describe what evidence is missing.
