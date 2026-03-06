# Docstrings

Arx docstrings use the [Douki](https://github.com/arxlang/douki) YAML format and
are validated against the official
[Douki schema](https://github.com/arxlang/douki/blob/main/src/douki/schema.json).

Docstrings are delimited by triple backticks:

````text
```
title: Example docstring
summary: Optional summary value.
```
````

## Supported Targets (Current)

- module docstring
- function docstring

## Required Field

Every docstring must provide at least:

- `title` (required by Douki schema)

Valid minimal docstring:

````text
```
title: Add two numbers
```
````

## Module Docstring Rule

The module docstring must:

- be the first top-level statement
- start at line 1, character 0

Valid:

````text
```
title: Module docs
```
fn main() -> i32:
  ```
  title: main
  summary: Entry point for the module.
  ```
  return 1
````

## Function Docstring Rule

A function docstring must be the first statement in the function body, right
after `:` and the required newline/indentation.

Valid:

````text
fn main() -> i32:
  ```
  title: Function docs
  summary: Function summary
  ```
  return 1
````

Invalid:

````text
fn main() -> i32:
  return 1
  ```
  title: Too late
  summary: This docstring is valid Douki but in the wrong position.
  ```
````

## Current Compiler Behavior

Docstrings are currently lexed and validated for:

- placement rules (module/function positions)
- Douki YAML schema conformance

After validation, they are intentionally ignored during AST/IR generation until
dedicated `DocString` nodes are added in `astx` and `irx`.
