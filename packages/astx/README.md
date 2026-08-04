# ASTx

ASTx is a language-agnostic Python model for abstract syntax trees. It provides
typed nodes and common metadata that parsers, analyzers, transpilers, and
compiler backends can share without adopting a particular source grammar.

> Status: functional and actively evolving. ASTx models more constructs than any
> one backend necessarily supports.

## Scope

ASTx currently models:

- source locations, identifiers, expressions, statements, and blocks
- scalar, string, temporal, collection, generic, and union types
- functions, defaults, modules, packages, and imports
- conditionals, loops, generators, comprehensions, and context managers
- classes, structs, inheritance, member access, and modifiers
- templates, FFI pointers/opaque handles, and semantic helper metadata
- lists, buffer views, tensors, DataFrames, and Series
- YAML, JSON, Mermaid, PNG, and optional console visualization paths

ASTx does not lex or parse source and does not generate LLVM by itself. IRx is
the Arx ecosystem backend that analyzes and lowers the supported ASTx subset.

## Install

```bash
pip install astx
```

For ASCII visualization through `mermaid-ascii`:

```bash
pip install 'astx[console]'
```

## Example

```python
import astx

args = astx.Arguments(
    astx.Argument(name="x", type_=astx.Int32()),
    astx.Argument(name="y", type_=astx.Int32()),
)

body = astx.Block()
body.append(
    astx.FunctionReturn(
        astx.BinaryOp(
            op_code="+",
            lhs=astx.Variable("x"),
            rhs=astx.Variable("y"),
        )
    )
)

add = astx.FunctionDef(
    prototype=astx.FunctionPrototype(
        name="add",
        args=args,
        return_type=astx.Int32(),
    ),
    body=body,
)

print(add.to_yaml())
```

## Relationship to Arrow

ASTx defines the compiler-facing node and type vocabulary for arrays, buffer
views, Tensors, DataFrames, and Series. It deliberately does not depend on
Apache Arrow or own native storage. IRx maps those nodes to its Arrow C++
runtime.

Documentation: <https://arxlang.org/astx/>

License: Apache-2.0.
