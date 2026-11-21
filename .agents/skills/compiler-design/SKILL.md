---
name: compiler-design
description: Implement and review Arx syntax, ASTx, IRx semantics, LLVM lowering, diagnostics and cross-stage compiler contracts. Use for compiler changes.
---

# Compiler design and cross-stage contracts

Use for parser, ASTx, IRx analysis, lowering, imports, diagnostics, or language-feature work. Follow [arx-architecture](../arx-architecture/SKILL.md).

Arx source syntax truth starts in `packages/arx/src/arx/lexer/syntax.json` and its lexer/parser implementation. Two-space indentation is significant. Update manifest, tokens, parser, tests, and relevant executable examples/editor consumers when syntax actually changes. Every committed `.x` begins with a valid Douki module docstring.

IRx analysis owns type checking, symbol resolution, conversions, class rules, imported call identity, typed native requirements, and semantic validity. Lowering must consume `node.semantic`/`CompilationSession`, never rediscover these facts or invent a generic fallback. Unsupported constructs should fail closed with phase-appropriate diagnostics and trustworthy source locations.

For LLVM: preserve result-stack discipline; do not synthesize values for statement-only or terminating branches, emit after terminators, or build invalid PHI nodes. Validate generated IR with `llvm.parse_assembly` where affected. Native code activates only through registered features.

For ArxJIT preserve `extract → validate → resolve_signature → lower`; `@jit` remains Python fallback. Preserve indentation, correct UTF-8-byte to Unicode location mapping, reject unsupported closures/globals or shadowed range, and prove the boundary with `analyze(lower(...))`.

Use existing semantic and compiled tests for changed contracts; do not multiply nearly identical tests.
