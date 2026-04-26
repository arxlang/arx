# IRx

IRx provides the semantic analysis, lowering, runtime support, and LLVM-backed
code generation layer for the Arx ecosystem.

In this monorepo, IRx is developed alongside ASTx, ASTx Transpilers, and the Arx
language frontend. Arx owns surface syntax and CLI behavior; IRx owns semantic
analysis and lowering behavior consumed by Arx.

## Key areas

- Semantic analysis and validation
- AST facade nodes used by Arx
- LLVM lowering and code generation helpers
- Runtime features for collections, buffers, tensors, assertions, and FFI

See the architecture and semantic contract pages for design details.
