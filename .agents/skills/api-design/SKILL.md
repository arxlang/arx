---
name: api-design
description:
  Design minimal, consistent Arx public Python and .x APIs with clear semantics,
  typing, visibility and correct package exports. Use for new or changed public
  APIs.
---

# Design one coherent public API

**Use for changes to public Python functions, classes, `.x` types, builtins,
methods, protocols or exports.** Apply
[minimal-change](../minimal-change/SKILL.md),
[python-code-style](../python-code-style/SKILL.md) when Python is touched, and
[language-design](../language-design/SKILL.md) for Arx source surface.

## API design steps

1. Locate nearest comparable API and inspect real callers, export mechanism,
   Douki source contract and current tests.
2. Write a common-case usage example and, only if meaningful, one advanced
   example; place them in the PR description or existing executable tests, not a
   new documentation page.
3. Choose a **single canonical call shape**. Distinguish core builtins, stdlib
   functions and type methods. Do not add wrappers solely for alias names.
4. Specify inputs/outputs: complete annotations, defaults, typed options, valid
   combinations, error statuses, null semantics, lifetime/ownership and
   unsupported cases.
5. Confirm the owning compiler/analysis layer validates the contract rather than
   allowing downstream LLVM/native code to discover errors.
6. Keep Python symbol visibility explicit via atpublic where used; update
   necessary `__all__`, exports, schemas and consumers. Preserve an existing
   name unless semantics or a real usability/correctness issue requires
   renaming.
7. Review pre-2.0 changes: don't introduce deprecation shims without a request;
   ensure producer/consumer and published package contracts remain synchronized.

## Anti-patterns and better alternatives

| Avoid                                                              | Prefer                                                                      |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| `compute()`, `calculate()`, `evaluate()` with equivalent contracts | One existing canonical operation                                            |
| A long list of unrelated optional booleans                         | A focused typed options object **only when** justified by real advanced use |
| Generic `Any` input and delayed C++ type errors                    | Typed semantic validation near the API boundary                             |
| New builtin for every math function                                | Focused `stdlib.math` functions when appropriate                            |
| Alias or underscore naming to represent visibility                 | `@public` / `@private` in packages using atpublic                           |
| Handwritten API page reproducing a Douki signature                 | Updated source Douki docstring and generated reference                      |

Verify the common case, invalid arguments and only distinct uncovered boundary
behavior in existing tests. Do not reorganize neighboring APIs or document
unrelated parts of the library.

**Exit:** consistent semantic contract, canonical entry point, correct
exports/consumers and sufficiently verified behavior.
