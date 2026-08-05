# Contributing

ArxLang is developed as a six-package monorepo. Contributions should respect the
boundary between source frontends, AST modeling, semantic analysis, and native
runtime behavior.

## Package ownership

- `packages/arx`: Arx syntax, lexer, parser, CLI, projects, tests, and stdlib
- `packages/astx`: shared language-agnostic AST nodes
- `packages/irx`: semantics, LLVM lowering, diagnostics, and native runtime
- `packages/arxpy`: Python-facing compiler API
- `packages/aix`: toy symbolic-language experiment and CLI
- `packages/arxjit`: Python decorator, extraction, validation, and future JIT

New language syntax belongs in a frontend. New reusable nodes belong in ASTx.
Semantic rules, LLVM lowering, and Arrow C++ integrations belong in IRx.

## Development setup

```bash
git clone https://github.com/arxlang/arx.git
cd arx
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

Create a focused branch, make minimal changes, and add tests close to the
behavior being changed.

## Quality checks

Run package-specific checks while iterating:

```bash
makim arx.unittests
makim astx.unittests
makim irx.unittests
makim arxpy.unittests
makim aix.unittests
makim arxjit.unittests
```

Before opening a pull request:

```bash
makim all.typecheck
makim all.lint
makim all.ci
makim docs.build
```

Native toolchain-dependent checks require Clang and, for Arrow features, a C++
compiler.

## Documentation and examples

- Update reference docs and examples with every behavior change.
- Every committed `.x` file begins with a valid Douki module docstring.
- Class, function, and method docstrings use Douki YAML inside triple backticks.
- Use quadruple Markdown fences around Arx examples containing docstrings.
- Keep `packages/arx/src/arx/lexer/syntax.json`, lexer behavior, and the lexical
  syntax page aligned.
- State experimental limits explicitly; do not document planned behavior as
  implemented.

## Python code

- Python 3.10 is the minimum supported runtime.
- Ruff uses a 79-character line length.
- Mypy is strict.
- Public and internal symbols follow the repository's Douki-style Python
  docstring convention.
- Prefer guard clauses and small focused helpers.
- Avoid unrelated formatting or refactoring churn.

## Configuration

Never use heredocs inside YAML-backed files such as `.makim.yaml` or GitHub
Actions workflows. Use direct commands or plain Python/xonsh statements.

## Pull requests

- Include focused tests and documentation.
- Report checks that could not run and why.
- Use a Conventional Commit title; releases use squash merge and
  semantic-release.
- Report bugs and proposals at <https://github.com/arxlang/arx/issues>.
