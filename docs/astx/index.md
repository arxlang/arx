# ASTx

ASTx is the language-agnostic abstract syntax tree model shared by the ArxLang
ecosystem. It lets frontends and compiler tools exchange typed Python objects
without sharing a source grammar.

> Status: functional and evolving. ASTx can model constructs that IRx or a
> particular source language does not yet lower.

## Current capabilities

- common AST base classes, source locations, parents, and structured output
- identifiers, variables, literals, operators, statements, and blocks
- scalar, text, temporal, collection, generic, and finite-union types
- functions, modules, packages, imports, defaults, and templates
- conditionals, loops, comprehensions, generators, and context managers
- classes, structs, inheritance, member access, visibility, and mutability
- FFI pointers and opaque handles
- list, buffer-view, Tensor, DataFrame, and Series nodes
- YAML, JSON, Mermaid, PNG, and optional ASCII visualization

## Architecture boundary

ASTx does not:

- lex or parse source code
- decide Arx or AIX language syntax
- perform IRx semantic analysis
- provide native storage or depend on Apache Arrow
- guarantee backend lowering for every modeled node

IRx consumes ASTx nodes and owns analysis, LLVM lowering, and the native Arrow
C++ runtime. Arx and AIX construct ASTx nodes from their respective languages.

## Small example

```python
import astx

body = astx.Block()
body.append(astx.FunctionReturn(astx.LiteralInt32(0)))

main = astx.FunctionDef(
    prototype=astx.FunctionPrototype(
        name="main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    ),
    body=body,
)

print(main.to_yaml())
```

## License

ASTx is licensed under Apache-2.0 as part of the ArxLang monorepo.
