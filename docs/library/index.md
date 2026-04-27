# Library Reference

The **Library** section is the language reference for Arx features, inspired by
the structure of `docs.python.org`.

Start here when you need exact syntax and placement rules.

Arx documents the surface language here, but the AST and lowering boundary comes
from IRx: parser output should use `astx`, and new lowering behavior should land
in IRx rather than in Arx-local code.

## Available References

- [Modules](modules.md)
- [Functions](functions.md)
- [Classes](classes.md)
- [Data Types](datatypes.md)
- [Built-in Types](built-in-types.md)
- [Control Flow](control-flow.md)
- [Docstrings](docstrings.md)

## Scope (Current Prototype)

This reference currently focuses on:

- module structure
- function definitions and calls
- type system and annotations
- built-in type reference
- class declarations and member modifiers
- control-flow syntax
- docstring placement rules

More feature pages can be added here as the language grows.
