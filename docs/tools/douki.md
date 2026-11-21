# Douki

[Douki](https://github.com/arxlang/douki) is a Python development tool for YAML
docstrings. Arx uses the Douki document structure for module, class, function,
and method docstrings.

Douki is maintained as a language-independent project; it is not part of the Arx
compiler pipeline.

## Capabilities

The current tool can:

- validate structured docstrings against a JSON Schema
- compare Python signatures with their documented parameters and return types
- synchronize docstrings after signatures change
- migrate supported existing docstring formats
- discover files while respecting `.gitignore` by default

## Python usage

```python
def add(a: int, b: int = 0) -> int:
    """
    title: Add two integers
    parameters:
      a: First integer to add.
      b:
        description: Second integer to add.
        default: 0
    returns: Sum of the two integers.
    """
    return a + b
```

Python annotations supply types; authored docstrings contain descriptions, not
`type` fields. `douki sync` scaffolds missing entries; replace its `...`
placeholders with meaningful descriptions, then run `douki check`. Use
`douki format` to format existing YAML. See the Douki repository for the options
supported by the installed release.

## Use in Arx source

Arx source uses Douki YAML inside triple backticks:

````arx
```
title: Example module
summary: Optional module summary.
```

fn main() -> i32:
  ```
  title: main
  ```
  return 0
````

Arx performs its own YAML and schema validation during parsing. It currently
does not retain source docstrings in ASTx or IR output.

See [Arx Docstrings](../arx/docstrings.md) for placement rules and
[github.com/arxlang/douki](https://github.com/arxlang/douki) for the standalone
tool.
