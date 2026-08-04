# Contributing to IRx

IRx lives in `packages/irx` and owns semantic analysis, lowering, native runtime
features, and LLVM-backed artifact generation. Parser syntax belongs in Arx or
AIX; reusable node definitions belong in ASTx.

## Setup

```bash
git clone https://github.com/arxlang/arx.git
cd arx
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

## Architecture rules

- Put semantic meaning and validation in `irx.analysis`, not in codegen.
- Make lowering consume resolved semantic sidecars instead of rediscovering
  types or symbols.
- Preserve `result_stack` discipline and never emit after a block terminator.
- Keep the native runtime behind registered features and opaque ABI boundaries.
- Do not encode Arrow C++ container layouts directly in LLVM IR.
- Keep ASTx node additions in ASTx and source syntax in the frontend package.
- Prefer small dispatch handlers and guard clauses over deeply nested lowering.

## Runtime type checking and docstrings

IRx applies `irx.typecheck.typechecked` to concrete public and internal
implementation boundaries. Class decorators cover methods, so method-level
decorators are normally unnecessary.

All Python symbols, including private helpers, use repository-style Douki
docstrings. Clearly document any typing-only `Protocol` exemption and update
`packages/irx/tests/test_typechecked_policy.py` when the policy changes.

## Tests

Add semantic tests for validation and resolved metadata, translation tests for
LLVM shape, and build/run tests when behavior depends on native linking.

```bash
makim irx.test-analysis
makim irx.unittests
makim irx.typecheck
makim irx.lint
makim irx.build
```

Arrow runtime changes should cover ownership, error handling, native build
integration, and PyArrow interoperability where applicable.

Use Conventional Commit syntax in pull request titles; the repository uses
squash merge and semantic-release.
