# VS Code Extension for Arx

[vscode-arx](https://github.com/arxlang/vscode-arx) provides editor support for
`.x` and `.arx` source files.

> **Status:** The extension provides syntax highlighting and basic language
> configuration. It does not currently include a language server, commands, or
> compiler runtime integration.

## Implemented features

- TextMate syntax highlighting under the `source.arx` scope
- Douki YAML docstring highlighting
- comments, strings, characters, numbers, literals, declarations, imports,
  control flow, annotations, templates, and operators
- bracket definitions and automatic closing/surrounding pairs
- `.x` and `.arx` file associations and icons

## Syntax source of truth

The extension vendors Arx's lexical manifest:

```text
packages/arx/src/arx/lexer/syntax.json
```

Its generated TextMate grammar should be synchronized whenever lexical syntax
changes in the Arx repository. Parser or IRx support is not inferred solely from
a token appearing in the lexical manifest.

## Development

The extension repository provides commands to synchronize and validate the
generated grammar:

```bash
npm run sync:syntax
npm run check:grammar
npm run build:grammar
```

Source and installation information:
[github.com/arxlang/vscode-arx](https://github.com/arxlang/vscode-arx)
