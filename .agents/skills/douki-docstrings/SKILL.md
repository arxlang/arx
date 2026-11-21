---
name: douki-docstrings
description: Write, validate and minimally maintain Douki Python docstrings, Arx .x YAML docstrings and generated documentation sources. Use for docstring or documentation changes.
---

# Douki documentation contracts

Use when creating or modifying Python public APIs, `.x` modules, class/function documentation, or generated documentation sources. Apply [minimal-change](../minimal-change/SKILL.md).

## Python source

Python docstrings follow the project's Douki YAML conventions: `title` plus relevant `summary`, `parameters`, `returns`, etc., based on the owning schema. Parameters and returns require meaningful descriptions; annotations alone do not replace source contracts. Preserve existing docstrings if their meaning is unchanged. Use the established `douki` commands and ensure `douki sync` is idempotent; do not hand-edit generated reference pages.

## Arx source

Every committed `.x` module—including examples and tests—starts at line 1, column 1 with a valid triple-backtick Douki YAML module docstring. The mapping requires a `title`; validate against `packages/arx/src/arx/schema/douki.json`. Function/member docstrings must occupy parser-supported positions and comply with their schema. Current Arx parser validates these blocks but does not emit them into AST/IR. Do not infer that every user-defined function needs a docstring. Preserve two-space indentation outside module documentation.

## Scope control

Do not create a Markdown page for each API or PR; DoukiMD generates API reference from native source contracts according to `doukimd.yaml`. Update a short existing guide only when a user workflow, safety/lifetime contract, important restriction, or architecture explanation actually changes. Avoid duplicate signatures/default tables and investigation notes.

For affected docs, run the relevant `douki` validation and `makim docs.check` / `makim docs.build` when needed. Report unrun checks precisely.
