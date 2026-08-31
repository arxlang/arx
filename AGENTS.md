# Arx Contributor Guide

This file is the shared operating manual for AI contributors working in the Arx
monorepo. It applies to compiler, library, runtime, documentation, test, CI, and
release changes unless a more specific instruction file overrides it.

## Core Objectives

1. Preserve existing behavior unless the task explicitly changes it.
2. Respect package ownership and keep cross-package contracts aligned.
3. Keep Python 3.10-3.14 behavior and the relevant quality gates green.
4. Make minimal, targeted changes with focused tests and documentation.
5. Report evidence honestly; never invent commands, results, spans, or support.

## Working With Repository State

- Inspect the local workspace, requested branch or commit, working tree, code,
  tests, manifests, CI, and review context before drawing conclusions.
- For reviews, use the requested change as the subject, then verify it against
  the local implementation, tests, configuration, and documented contracts. Use
  issues and prose documentation as supporting context, not as a substitute for
  executable evidence.
- Clearly distinguish current behavior from proposed or partially implemented
  behavior. Lexical reservation and AST modeling do not prove end-to-end
  language support.
- Refresh dated facts from the repository. Do not preserve stale package,
  version, CI, or support claims merely because they appear in prose.
- Do not mutate GitHub, publish artifacts, or perform other remote side effects
  unless the user explicitly requests them.

## Repository And Architecture

The root project is the development metaproject for six Python packages:

- `packages/arx/` (`arxlang`): Arx surface syntax, source/package discovery,
  lexer, parser, CLI, stdlib, examples, and compiled-language tests. It emits
  ASTx and supplies parsed modules to IRx.
- `packages/astx/` (`astx`): language-agnostic AST nodes and types. Adding a
  node does not imply semantic-analysis or backend support.
- `packages/irx/` (`pyirx`): semantic analysis and metadata, diagnostics, LLVM
  lowering, native runtime features, linking, and Python-side Arrow
  interoperability.
- `packages/arxpy/` (`arxpy`): the Python API layer for the Arx stack and a
  foundational integration package.
- `packages/arxjit/` (`arxjit`): a developing Numba-style Python frontend.
  Native dispatch is not complete; `@jit` currently executes Python fallback.
- `packages/aix/` (`airx`): a toy symbolic-language experiment, not the design
  authority for Arx.

The main compiler pipeline is:

```text
.x source -> Arx lexer/parser -> ASTx -> IRx semantic sidecars
          -> IRx LLVM lowering -> registered native features -> link/run
```

Important root locations:

- `examples/`: executable Arx examples
- `docs/`: Quarto documentation
- `scripts/`: build, documentation, release, and maintenance tooling
- `.makim.yaml`: canonical local task definitions
- `.github/workflows/main.yaml`: CI behavior
- `.releaserc.json`: lockstep release and version-replacement wiring

## Package Ownership Boundaries

### Arx, ASTx, And IRx

- Arx owns source syntax, lexing, parsing, module discovery, CLI flow, and
  frontend-specific diagnostics. It constructs existing `astx` nodes directly.
- ASTx owns reusable node and type modeling. Do not create Arx-owned AST or ASTx
  node classes.
- IRx owns program meaning and validity in `irx.analysis`, plus general lowering
  and native code generation. Lowering must consume `node.semantic` and the
  `CompilationSession`; it must not rediscover symbols, types, conversions,
  imports, class rules, or other semantic facts.
- Hosts provide `ParsedModule` and `ImportResolver`. IRx must not find or parse
  source files itself.
- When a feature needs a reusable node, add it to ASTx and coordinate frontend
  emission, IRx semantics, lowering, exports, docs, and tests. When a needed
  semantic or lowering hook is absent, implement it in IRx rather than adding a
  frontend workaround.
- `packages/arx/src/arx/codegen.py` is an Arx integration adapter over IRx. Keep
  it small and prefer shrinking it; do not add general feature lowering there.
- Never silently omit input or emit a generic node that merely fails in a later
  phase. Reject unsupported input at the earliest responsible boundary with an
  actionable diagnostic.

### Long-Term Direction

Python is the current implementation language. Keep typed Python APIs and stable
ABI/IR boundaries migration-friendly, but do not begin speculative self-hosting
or rewrites. Arx self-hosting is only a long-term option after a stable
Arx-to-LLVM binding exists.

## Cross-Package Implementation Standards

- Use strict type annotations for every argument and return. Minimize `Any` and
  test invalid runtime inputs.
- ASTx and IRx runtime-checked code must use the owning package wrapper
  (`astx.tools.typing.typechecked` or `irx.typecheck.typechecked`), not an ad
  hoc Typeguard import. Runtime validation must cover arguments and collection
  items. Follow the established package convention elsewhere.
- Do not encode API privacy with leading-underscore names in new code. In
  packages using `atpublic`, use `@private` and `@public` from `public`; do not
  expand existing naming debt.
- Use Plum multiple dispatch for behavior that varies by type, especially
  visitors. Overload one method name such as `visit`; do not create per-type
  names. Keep a typed, fail-closed fallback.
- Use structured, phase-appropriate diagnostics and exceptions. Do not raise a
  generic `Exception`, invent source locations, or attach spans that cannot be
  trusted.
- Prefer guard clauses and early returns over deeply nested control flow.
- Apply SOLID principles where they improve clarity, testability, or change
  safety. Avoid unrelated refactors and formatting churn.
- Comment non-obvious intent and constraints, not code that is already clear.
- Python uses four-space indentation. Ruff uses a 79-character line length and
  double-quoted formatting. Mypy is strict.
- Python docstrings use Douki-style content blocks. Keep them present and
  synchronized for new or updated public symbols; `douki sync` must remain
  idempotent.

## Arx Frontend Contract

### Key Locations

- `packages/arx/src/arx/io.py`: shared source buffer and standard file/string
  entry points
- `packages/arx/src/arx/lexer/`: tokens, lexical behavior, and syntax tables
- `packages/arx/src/arx/lexer/syntax.json`: canonical lexical manifest for the
  lexer and editor tooling
- `packages/arx/src/arx/parser/`: concern-grouped parser core and mixins
- `packages/arx/src/arx/docstrings.py`: Douki YAML validation
- `packages/arx/src/arx/schema/douki.json`: Arx docstring schema
- `packages/arx/src/arx/main.py` and `cli.py`: compilation orchestration and CLI
- `packages/arx/src/arx/settings.py` and `package_index.py`: project settings,
  source roots, and installed-package discovery
- `packages/arx/src/arx/codegen.py`: remaining Arx builder/link adapter

### Syntax Changes

Arx uses significant two-space indentation. The lexical source of truth is
`packages/arx/src/arx/lexer/syntax.json`. Apply syntax changes in this order:

1. Update the syntax manifest.
2. Update token definitions and lexer behavior.
3. Update the relevant parser module or mixin.
4. Add lexer, parser, and integration tests.
5. Update docs, examples, and editor-facing consumers.

Do not infer parser, semantic, or lowering support from a keyword or operator
being present in the manifest. Check each downstream stage. Preserve current
parser and test behavior unless the task explicitly changes the language.

Use `LexerError` with a trustworthy source location for lexer failures and
`ParserException` for parser-specific user errors. Do not replace these with
generic exceptions.

### Arx Docstrings

Arx docstrings are Douki YAML enclosed by triple backticks:

````text
```
title: Example
summary: Optional summary
```
````

The parser enforces these rules:

- A module docstring is the first top-level statement and starts at line 1,
  column 1, without leading spaces.
- A function docstring is the first statement in its function block.
- Class or member docstrings appear in the supported declaration position and
  use the same valid Douki YAML form.
- Abstract methods may use a docstring-only body when supported by the parser.
- The YAML value is a non-empty mapping that satisfies the schema; `title` is
  required.
- Docstrings are currently validated but omitted from AST/IR output.

Every committed `.x` file, including examples, stdlib files, fixtures, and
compiled tests, must begin with a valid module docstring. Added class and method
docstrings must also follow the parser-supported Douki placement. Use quadruple
Markdown fences when an example needs to contain the triple-backtick syntax.

## IRx Semantic, Lowering, And Native Runtime Contract

- Put meaning, type validity, symbol resolution, conversion rules, imports, and
  class rules in `packages/irx/src/irx/analysis/`.
- Keep analysis and lowering separate. Lowering consumes resolved semantic
  metadata and fails explicitly when required metadata is absent.
- Preserve `result_stack` discipline: push only values that are semantically
  produced and never assume a value follows a statement-only or terminating
  branch.
- Never emit instructions after a terminator. Create merge values such as PHI
  nodes only when incoming paths fall through and their types are compatible.
- Generated LLVM must remain valid and parseable with `llvm.parse_assembly`.
- Activate native code only through registered runtime features. Do not add
  implicit compiler/linker dependencies outside the runtime feature registry.
- Keep Arrow C++ objects behind opaque handles and the `irx_arrow_*` or
  `irx_rb_*` C ABI. Never encode Arrow C++ layouts directly in LLVM IR.
- Make ownership, lifetime, transfer, status, and output-slot contracts explicit
  and test them. Read output slots only after a successful status result.
- Treat Arrow kernels as focused runtime primitives, not as a general-purpose
  query engine.

Native and Arrow tests should cover relevant null, empty, error, overflow,
shape/type mismatch, ownership, and release paths, plus PyArrow interchange when
applicable.

## ArxJIT Contract

Keep these stages independently testable:

```text
extract -> validate -> resolve_signature -> lower
        -> future compile/bridge/cache
```

- `@jit` still calls the original Python function; do not claim native dispatch
  is implemented.
- Preserve source indentation. Parse nested definitions inside a wrapper rather
  than using `dedent`.
- Python AST columns are UTF-8 byte offsets. Convert them to one-based Unicode
  columns only at the source-location boundary, and omit a location when it
  cannot be trusted.
- Validation aggregates violations. Reject unsupported global/closure access and
  calls to a shadowed intrinsic `range`.
- An explicit signature selects scalar types; it does not redefine function
  shape or arity. Reserved annotations map `int`, `float`, and `bool` to `i64`,
  `f64`, and `bool_` without consulting mutable globals.
- Lower only forms accepted by IRx and prove the boundary with
  `analyze(lower(...))`. Range-check contextual literal widths and mangle names
  reserved by IRx, including `main`.

## Tests, Documentation, And Examples

- Add focused tests at the earliest layer responsible for the behavior, plus
  integration tests at every affected package boundary.
- Arx Python tests live in `packages/arx/tests/python/`; compiled Arx tests live
  in `packages/arx/tests/arx/`.
- ASTx, IRx, ArxPy, ArxJIT, and AIX tests live under their respective
  `packages/<name>/tests/` trees.
- Parser or syntax changes need lexer/parser coverage and at least one relevant
  example or compiled-language test.
- Codegen/control-flow changes need a translate-path regression, normally in
  `packages/arx/tests/python/test_codegen_ast_output.py`, and a build/run test
  when behavior depends on linked execution and the toolchain is available.
- Keep `examples/*.x`, stdlib files, tests, syntax manifests, and documentation
  synchronized with supported behavior. Never invent syntax in examples.
- Update language overview, getting-started material, and relevant `docs/arx/`
  pages when public Arx behavior changes. Quarto API documentation is generated
  through `scripts/gen_api_docs.py`.
- Public cross-package changes may also require schemas, exports, package
  manifests, dependency pins, build scripts, and release wiring.

## Tooling And Verification

Install the root development environment with:

```bash
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
```

Prefer the smallest relevant checks first:

```bash
pytest <target> -q
makim <package>.unittests
makim <package>.typecheck
makim <package>.lint
makim <package>.ci
```

Repository-wide and documentation checks are:

```bash
makim all.typecheck
makim all.lint
makim all.ci
makim docs.build
```

Useful Arx-specific checks include:

```bash
makim arx.test-compiled
makim arx.test-smoke
makim arx.check-syntax
pytest -q packages/arx/tests/python/test_codegen_ast_output.py
pytest -q packages/arx/tests/python/test_codegen_file_object.py
```

The GitHub workflow runs package tests and Arx/AIX language checks on Ubuntu
with Python 3.10 through 3.14, plus the pre-commit lint stack. Do not assume a
change is portable because it passes on only one Python version. Native build
and execution checks may additionally require Clang and a C++ toolchain.

Always report exactly which checks ran, their results, and any environment or
toolchain blockers. Do not imply that an unrun check passed.

## Configuration And Release Rules

- Never use heredocs inside YAML files, including GitHub workflows and
  `.makim.yaml`. Use plain shell commands or direct Python/xonsh statements.
- Never edit `poetry.lock` manually. Change the appropriate `pyproject.toml` and
  regenerate the lockfile only with `poetry lock` from the repository root.
- Keep package versions and dependency pins synchronized with the lockstep
  semantic-release configuration. Update `.releaserc.json`, build/publish
  scripts, and release assets when adding or renaming a package.
- Use a Conventional Commit PR title. The project squash-merges PRs and releases
  the package set in lockstep.

## PR Review Protocol

Lead with findings ordered by severity. Each finding should state:

1. the violated contract or defect,
2. its concrete impact,
3. supporting evidence,
4. an exact file and line location where possible.

Review callers and downstream stages, not only the changed function. Probe the
relevant edge cases: shadowing, Unicode locations, overflow and null handling,
terminators and result stacks, lifetime/ownership/status, unsupported nodes,
Python-version differences, docs, CI/release wiring, and stacked-branch
assumptions.

Require cross-stage evidence for cross-stage claims. Separate merge blockers
from follow-up improvements. If no findings remain, say so and list unverified
risks or checks rather than inventing confidence.

## Delivery Checklist

Before finalizing a change, verify as applicable:

- [ ] behavior changes have focused tests
- [ ] frontend, ASTx, semantics, lowering, runtime, and exports remain aligned
- [ ] syntax changes update manifest, lexer, parser, tests, docs, and examples
- [ ] touched code passes relevant Ruff, mypy, Douki, and unit checks
- [ ] generated LLVM and native boundaries are validated where affected
- [ ] docs, schemas, manifests, dependency pins, and release wiring are current
- [ ] no unrelated refactor, formatting churn, generic error, or silent fallback
- [ ] the final report lists executed checks and remaining blockers
