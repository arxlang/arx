---
name: python-code-style
description: Apply Arx Python coding conventions including Typeguard development instrumentation, atpublic visibility, Plum dispatch, SOLID, shallow nesting, strict typing and Ruff. Use on Python changes.
---

# Python engineering standards

Use for Python implementation, review, or refactoring in the Arx monorepo. Apply [minimal-change](../minimal-change/SKILL.md). Read root `AGENTS.md` and follow local package conventions.

## Types and runtime checking

Annotate arguments and returns; minimize `Any`, and use strict mypy. For ASTx use `astx.tools.typing.typechecked`; for IRx use `irx.typecheck.typechecked`. Do not substitute direct Typeguard decoration in those packages. Check invalid inputs and collection elements in focused tests where relevant.

The actual `astx.tools.typing` wrapper reads `ARX_RUNTIME_TYPECHECK` **once at import time** (accepted values `0` or `1`, default `0`). `1` instruments arguments, return values, and **ALL_ITEMS** collection checks; `0` returns the original target without instrumentation. Set the environment variable *before importing* the stack in developer/test processes. Compiler semantic checks remain mandatory regardless of this flag; production need not incur instrumentation overhead.

## API visibility and dispatch

Packages using `atpublic` import `public`/`private` from `public` and explicitly decorate symbols. Do not introduce leading underscores as a substitute for visibility or expand existing naming debt. Respect package `__all__`/exports where relevant.

Use Plum multiple dispatch when behavior varies by argument type, especially visitor overloads of a single `visit` method; retain a typed, fail-closed fallback. Do not introduce per-type visitor names.

## Maintainability

Prefer guard clauses and early returns to unnecessary nested conditionals. Apply SOLID pragmatically: single responsibility, small interfaces, clear ownership, and dependency direction without speculative abstractions. A small direct implementation may be better than several layers of indirection. Use structured, phase-appropriate exceptions and trustworthy spans; never silently discard input.

Follow Ruff's 79-character limit, four-space Python indentation, double quotes, and existing import conventions. Do not reformat untouched code. Public Python source contracts use Douki docstrings; see [douki-docstrings](../douki-docstrings/SKILL.md).
