---
name: language-design
description: Design minimal and coherent Arx syntax, builtins and stdlib behavior using Python ergonomics without assuming compatibility. Use for language proposals.
---

# Arx language and standard-library design

**Use for syntax, builtin, stdlib, methods, types, protocols and user-facing diagnostics.** Apply [minimal-change](../minimal-change/SKILL.md). Consult [api-design](../api-design/SKILL.md) when public call contracts or exports change, and [compiler-design](../compiler-design/SKILL.md) when syntax or compiler-stage contracts change.

## Decide the smallest useful public behavior

1. Express the user's common task in short `.x` code using **currently supported** syntax; where proposed, label unimplemented constructs explicitly.
2. Look at Python and established library APIs for names, ergonomics and safe defaults. Familiarity is guidance, **not** a compatibility obligation.
3. Decide ownership: small broadly useful builtins (`print`, `len`, `cast`), focused imported stdlib modules (e.g. math reductions), or a natural method on a type. Don't create synonymous entry points.
4. Define return/error/null/overflow/ownership meaning, supported options and invalid forms before implementation. Reject unsupported combinations explicitly, not with silent coercions.
5. Choose types: IRx language semantics versus Arrow runtime representation. A reserved lexical token or ASTx type alone does not prove executable language support.
6. Validate the one complete slice through manifest/lexer/parser, ASTx, semantic analysis, LLVM, registered native feature/linking if applicable, and compiled tests.
7. Update existing source contracts/examples only where behavior is actually supported.

## Examples of decisions

- Numeric functions: prefer imported `stdlib.math`, Arrow compute when semantically compatible, and typed plans; do not automatically add every function to the builtin namespace.
- New iterables: explicitly define eager/lazy semantics, lifetime, for-loop eligibility and error behavior before inventing a universal `LazyType`.
- New protocol: demonstrate an actual operation and two useful implementations; don't add a speculative method hierarchy.
- API change before 2.0: no default compatibility alias/deprecation shim, but update actual callers and maintain ABI/IR consistency.

Arx uses name-first syntax where currently implemented, significant two-space indentation and required Douki module docstrings. Verify examples against current parser rather than guessing spellings.

## Review check

Is it obvious to an Arx user how to do the common case? Is there one canonical interface? Are restrictions and errors precise? Is the requested behavior actually executable? Did the implementation avoid building a larger language feature than requested?
