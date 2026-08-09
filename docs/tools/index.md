# ArxLang Tools

These projects support Arx development but are maintained separately from the
core compiler packages. Each has its own repository, release process, and
maturity level.

| Project                        | Role                          | Current scope                                               |
| ------------------------------ | ----------------------------- | ----------------------------------------------------------- |
| [ArxPM](arxpm.md)              | project and workspace manager | manifests, environments, dependencies, build/run, packaging |
| [VS Code extension](vscode.md) | editor integration            | TextMate highlighting and language configuration            |
| [Jupyter kernel](jupyter.md)   | notebook integration          | wrapper kernel that compiles and runs cells                 |
| [Douki](douki.md)              | structured docstring tool     | YAML schema validation, synchronization, and migration      |

## Relationship to Arx

- The `arx` compiler remains responsible for parsing and compiling `.x` files.
- ArxPM orchestrates project-level operations around the compiler.
- The VS Code extension derives highlighting data from Arx's lexical manifest.
- The Jupyter kernel invokes the compiler as an external process.
- Arx uses the Douki YAML format for source and Python docstrings, while Douki
  itself is language-independent.

The [ecosystem status](../ecosystem.md) covers the packages stored in the main
Arx monorepo. The pages in this section describe related repositories.
