---
name: douki-docstrings
description: Write, validate and minimally maintain Douki Python docstrings, Arx .x YAML docstrings and generated documentation sources. Use for docstring or documentation changes.
---

# Douki source contracts without documentation churn

**Use when changing public Python symbols, `.x` source modules, docstrings, or DoukiMD.** Apply [minimal-change](../minimal-change/SKILL.md).

## Python docstrings

Actual source examples: `packages/irx/src/irx/typecheck.py` and `packages/arx/src/arx/docstrings.py`. Arx uses YAML content in Python triple-quoted docstrings, with `title`, appropriate `parameters`, `returns`, `summary`, etc. as required by the owning Douki schema.

```python
def validate_name(name: str) -> str:
    """
    title: Validate a requested name.
    parameters:
      name: Name supplied by the caller.
    returns: Validated name.
    """
    if not name:
        raise ValueError("name must not be empty")
    return name
```

Illustrative only. A Python annotation is **not** a replacement for a parameter or return description. Preserve existing correct descriptions. Update the docstring if meaning or signature changes; do not reword unrelated documentation for personal taste. Avoid invented `returns` on APIs without a return value unless the package schema requires it.

## Arx `.x` documents

Every committed `.x`—source, stdlib, example, fixture or compiled test—begins at **line 1 column 1** with a triple-backtick Douki YAML module block. Example:

````text
```
title: Example module
summary: Show a minimal supported Arx source module.
```
````

`packages/arx/src/arx/docstrings.py` validates YAML against `packages/arx/src/arx/schema/douki.json`; `title` is mandatory. Function/member documentation must appear at the parser-supported position. A user function is not automatically required to have its own docstring. Docstrings are currently validated but not emitted into AST/IR. Keep significant two-space syntax indentation.

## Docs-versus-code decision

| Change | Documentation action |
| --- | --- |
| Internal bug fix, unchanged API/workflow | No guide changes; update source contract only if inaccurate |
| Public signature/semantics changed | Update the owning source Douki docstring and affected example/test |
| New user workflow/restriction/safety requirement | Update the smallest existing guide |
| Generated API reference | Never hand-edit it; source remains authoritative |
| New feature in an existing page | Extend that page, not create a separate feature page by default |

Do not duplicate signatures, defaults, type tables or method lists in handwritten Markdown. `doukimd.yaml` defines generated API sources. Avoid docs pages, test-result logs, and implementation diaries not explicitly needed.

## Validation

For affected source contracts, use established `douki sync` / lint workflow and confirm idempotency. Use `makim docs.check` or `makim docs.build` when documentation generation is affected. For `.x` modules validate through existing lexer/parser/compiled tests. Don't add a documentation-specific CI job for an ordinary code change.
