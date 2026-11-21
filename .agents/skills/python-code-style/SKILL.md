---
name: python-code-style
description:
  Apply Arx Python coding conventions including Typeguard development
  instrumentation, atpublic visibility, Plum dispatch, SOLID, shallow nesting,
  strict typing and Ruff. Use on Python changes.
---

# Python implementation conventions for Arx

**Use on Python edits and reviews.** Read root `AGENTS.md` and
[minimal-change](../minimal-change/SKILL.md). Do not perform a style-only
rewrite of unrelated code.

## Type annotations and development-time runtime checks

- Annotate _every argument and return_, including helpers; avoid `Any` except
  where a contract truly requires it. Root `pyproject.toml` enables strict mypy,
  Ruff line length 79, and Python 3.11 target; check package manifests and CI
  for actual supported interpreters (currently 3.11–3.14).
- For ASTx, import `typechecked` from `astx.tools.typing`; for IRx, from
  `irx.typecheck`. IRx re-exports the ASTx policy. Do **not** directly use
  `typeguard.typechecked` in these packages.
- `packages/astx/src/astx/tools/typing.py` reads `ARX_RUNTIME_TYPECHECK` at
  **import time**. `0` (default) returns the original function/class without
  instrumentation; `1` instruments arguments, returns, and all collection items
  via `CollectionCheckStrategy.ALL_ITEMS`. Other values raise `ValueError`.
  Changing the environment after import **does not** retrofit checking.
- Use runtime checking in development/CI where configured; it is not a
  substitute for semantic validation of `.x` code.

```python
from irx.typecheck import typechecked
from public import public

@public
@typechecked
def normalize_width(width: int) -> int:
    """
    title: Validate a requested numeric width.
    parameters:
      width: Width in bits.
    returns: Validated width.
    """
    if width <= 0:
        raise ValueError("width must be positive")
    return width
```

This is an illustrative pattern, not a suggestion to add a new helper. Follow
the owning package's actual decorator/export conventions; inspect existing
`@public` and `@private` use before editing.

To probe runtime checking, start a **fresh process** with
`ARX_RUNTIME_TYPECHECK=1` before package imports and exercise bad arguments
(including a non-first invalid collection item). Don't toggle environment
settings mid-test and claim the wrapper changed.

## Visibility

In packages using `atpublic`, use `from public import private, public` and the
relevant decorators. A leading `_` in existing names is historical/internal
naming, **not** the visibility mechanism to introduce for new APIs. Review
`__all__` and exports where the package uses them. Avoid gratuitous renames.

## Type-specific behavior

Prefer Plum overloads sharing a single name, such as `visit`, when behavior
differs by ASTx node type. Do not introduce `visit_binary` / `visit_return`
families in place of typed dispatch. A broad fallback must raise a typed,
actionable error instead of silently returning `None` or a generic AST node.

## Control flow and SOLID

Use validation-first guard clauses; avoid "never nesting" as an absolute rule.
Nested scope can be appropriate in parsers, CFG construction or resource
handling. Single responsibility and dependency inversion should enforce actual
Arx ownership boundaries, not create interfaces without real consumers. Avoid
redundant wrappers, broad exception handling and reflective `getattr`
workarounds where the type contract should be explicit.

```python
def checked_divisor(value: int | None) -> int:
    if value is None:
        raise ValueError("missing divisor")
    if value == 0:
        raise ValueError("zero divisor")
    return value
```

## Errors, source contracts, verification

Prefer structured phase errors with trustworthy spans. Do not raise bare
`Exception`, invent locations, or swallow inputs. Python source docstrings use
Douki YAML content (see [douki-docstrings](../douki-docstrings/SKILL.md));
update only changed contracts.

Verify with focused `pytest`, `makim <package>.typecheck` and
`makim <package>.lint` for affected packages, and relevant development-mode
runtime type tests. Report what actually ran.
