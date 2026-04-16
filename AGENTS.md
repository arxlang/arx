# AI Skill: Arx Contributor Guide

This file is the shared operating manual for AI contributors working in `arx`.
Use it to keep implementation style, review standards, and delivery quality
consistent across different agents.

## When To Use This Skill

Use this guidance for any change inside the Arx compiler repository:

- parser or lexer changes
- language feature work
- CLI behavior updates
- docs/examples updates
- tests, typing, and lint fixes
- release/CI-related maintenance

## Core Objectives

1. Preserve existing language behavior unless the task explicitly changes it.
2. Keep syntax, parser rules, docs, examples, and tests aligned.
3. Keep code quality gates green (tests, mypy, ruff, pre-commit).
4. Make minimal, targeted edits with clear intent.

## Project Snapshot

- Package: `arxlang`
- Runtime: Python `>=3.10,<4`
- Main architecture: `source -> lexer -> parser -> astx -> irx/LLVM`
- Key dependencies:
  - `astx` for AST nodes
  - `irx` for IR/codegen
  - `jsonschema` + `pyyaml` for Douki docstring validation
- Docs stack: MkDocs + Material + mkdocstrings

## Repository Layout

- `src/arx/`: compiler implementation
- `tests/`: unit tests
- `examples/`: runnable language samples (`.x`)
- `docs/`: project and language documentation
- `syntax/arx.syntax.json`: lexical source-of-truth for editor tooling
- `.makim.yaml`: local task runner definitions
- `.github/workflows/main.yaml`: CI pipeline

## Architecture And Responsibilities

### `src/arx/io.py`

- Maintains a shared text buffer used by lexer/parser flows.
- `ArxIO.file_to_buffer` and `ArxIO.string_to_buffer` are standard entry points
  for tests and compilation.

### `src/arx/lexer.py`

- Defines `TokenKind`, `Token`, `TokenList`, and `Lexer`.
- Tokenizes indentation-sensitive syntax and emits `TokenKind.indent` for
  leading spaces at each logical line.
- Parses docstrings delimited by triple backticks as `TokenKind.docstring`.

### `src/arx/parser.py`

- Converts token stream into `astx` nodes.
- Enforces indentation-based blocks (`INDENT_SIZE = 2`).
- Handles module/function docstring placement and validation.
- Raises `ParserException` for parser-specific errors.

### `src/arx/docstrings.py`

- Validates docstring content as Douki YAML.
- Loads schema from `src/arx/douki_schema.json`.
- Enforces non-empty YAML object and schema conformance.

### `src/arx/codegen.py`

- Contains Arx-specific LLVM lowering overrides on top of IRx.
- `ArxVisitor` extends `irx.builder.Visitor`.
- `ArxBuilder` extends `irx.builder.Builder`.
- Keep this layer minimal and explicit; prefer upstream fixes in IRx when
  changes are generic.

### `src/arx/main.py` and `src/arx/cli.py`

- CLI argument handling and execution modes (`--show-tokens`, `--show-ast`,
  `--show-llvm-ir`, compile, `--run`).
- `ArxMain._get_astx()` orchestrates parse flow over input files.
- `ArxMain` uses `arx.codegen.ArxBuilder` for Arx-specific codegen behavior.

## Language Rules You Must Preserve

Current language behavior (from parser/lexer/tests/syntax manifest):

- Significant indentation, 2-space unit
- Keywords: `fn`, `extern`, `return`, `if`, `else`, `for`, `in`, `var`, `const`
- Numeric literals: decimal integer/float (single `.` max)
- String/char/bool/none literals are supported
- Comments: `#` line comments
- Function definitions: `fn name(arg: type, ...) -> type` followed by indented
  block
- Function arguments must be explicitly typed
- Variable declarations must be explicitly typed (`var name: type`)
- Extern definitions: `extern name(arg: type, ...) -> type`
- Control flow: `if/else`, `while`, `for ... in (...)`, count-style `for`
- Range-style for header is `(start:end:step)` (tuple-style is rejected)
- Builtins: `cast(value, type)` and `print(expr)`

If you extend language syntax, update all affected surfaces:

1. lexer/token definitions
2. parser behavior
3. tests
4. `syntax/arx.syntax.json`
5. docs and examples

## Codegen Invariants (Arx + IRx)

When changing `src/arx/codegen.py`, preserve these invariants:

- `result_stack` discipline:
  - never assume a value exists after statement-only or terminating branches
  - only push values that are semantically produced
- Terminator safety:
  - do not emit instructions after a block terminator
  - for `if` merges, create PHI nodes only when both incoming paths fall through
    and types match
- Build output must remain parseable by LLVM (`llvm.parse_assembly`)
- Arx compatibility workarounds should stay local, small, and test-covered

## Docstring Standard (Mandatory)

Arx docstrings are Douki YAML inside triple backticks:

```text

```

title: Example summary: Optional

```

```

Rules enforced by parser:

- Module docstring:
  - first top-level statement only
  - starts at line 1, column 1 (no leading spaces)
- Function docstring:
  - first statement inside function block only

Schema notes:

- must be valid YAML mapping/object
- must satisfy Douki schema (`title` is required)

Current behavior:

- docstrings are lexed and validated
- docstrings are ignored in AST/IR output for now

## Code Style And Standards

### Design Principles

- Apply SOLID principles where they improve clarity, testability, and change
  safety.
- Prefer a never-nest style: use guard clauses and early returns to keep control
  flow flat when possible.
- Avoid unnecessary or obvious comments; comment only non-trivial intent or
  decisions that are not clear from code itself.

### Formatting and static quality

- Python style:
  - 4-space indentation (`.editorconfig`)
  - max line length: 79 (`ruff`)
- Arx language examples:
  - 2-space indentation
- Ruff:
  - run `ruff check` and `ruff format` (docs excluded by config)
- Typing:
  - `mypy` is strict (`check_untyped_defs = true`, `strict = true`)
- Security/dead code gates in pre-commit:
  - `bandit`, `vulture`, `mccabe`

### Python docstring convention in this repo

- Python docstrings are Douki-style content blocks (for example `title: ...`).
- Keep docstrings present and consistent in new/updated public symbols.
- `pre-commit` runs `douki sync`; keep this passing.

### Error handling

- Parser-level user-facing parse errors: `ParserException`
- Lexer-specific failures: `LexerError` (with source location)
- Avoid raising generic `Exception` for new parser/lexer error paths.

## Tooling And Commands

Environment setup:

```bash
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

High-value commands:

```bash
# tests
pytest tests -q

# strict typing
mypy src

# lint/format
ruff check src tests
ruff format src tests

# full lint stack used by project
makim tests.linter

# CI-like local run
makim tests.ci

# docs
mkdocs build --config-file mkdocs.yaml
```

Codegen-focused checks:

```bash
# translate-path regressions (no linker required)
pytest -q tests/test_codegen_ast_output.py

# build/run-path checks (requires clang)
pytest -q tests/test_codegen_file_object.py
```

Smoke examples:

```bash
makim tests.smoke
```

Note: `arx --show-ast` may require `mermaid-ascii` installed by your `astx`
environment.

## CI Contract (What Must Stay Green)

GitHub Actions (`.github/workflows/main.yaml`) runs:

- tests on Python 3.10 to 3.14 (ubuntu)
- smoke tests
- syntax checks
- lint/pre-commit checks

Do not merge feature work that only passes on one Python version assumption.

## Documentation Contract

When behavior changes, update docs in same PR:

- language overview and getting-started examples
- `docs/library/*` for syntax/placement rules
- API docs are generated via mkdocstrings (`scripts/gen_ref_nav.py`)

If embedding Arx docstrings inside Markdown code examples, prefer quadruple
fences around the code block to safely include inner triple backticks.

## Testing Contract

- Prefer targeted tests near changed behavior.
- For parser or syntax changes: add/adjust parser tests and at least one
  example.
- For codegen/control-flow changes:
  - add at least one translate-path test (`tests/test_codegen_ast_output.py`)
  - add build/run assertions when behavior depends on linked execution and
    toolchain is available.

## Examples Contract

- Keep `examples/*.x` valid under current parser rules.
- Keep examples synchronized with docs examples.
- For now, examples should include valid Douki module/function docstrings.

## Change Playbooks

### Adding/changing lexer tokens

1. Update `TokenKind` and keyword maps.
2. Adjust lexing logic and location behavior.
3. Add/adjust `tests/test_lexer.py` cases.
4. Update `syntax/arx.syntax.json` if lexical spec changed.
5. Update docs/examples.

### Adding/changing parser rules

1. Implement parse behavior in `parser.py`.
2. Raise `ParserException` with clear messages.
3. Add parser tests (`tests/test_parser.py`).
4. Validate existing examples still parse.
5. Update docs and examples.

### Changing docstring behavior

1. Update `docstrings.py` and/or parser integration.
2. Add valid and invalid schema tests.
3. Update `docs/library/docstrings.md` and related examples.
4. Keep AST/IR behavior explicit if unchanged.

## Contributor Workflow Expectations

1. Make minimal focused changes.
2. Add/update tests for behavior changes.
3. Run local quality checks before finalizing.
4. Keep docs/examples in sync.
5. Use conventional commits in PR title (project uses semantic-release and
   squash-merge).

## PR Review Checklist For AI Agents

Before submitting final output, verify:

- [ ] behavior change is covered by tests
- [ ] parser/lexer updates reflected in docs and examples
- [ ] `mypy` passes for touched code
- [ ] `ruff` and pre-commit hooks pass (or clearly report blockers)
- [ ] no unrelated refactors or formatting churn
- [ ] error messages are explicit and actionable

## Non-Goals / Avoid

- Do not invent unsupported syntax in examples.
- Do not update unrelated files to "clean up" style.
- Do not bypass schema validation for docstrings.
- Do not leave parser, docs, and examples out of sync.
