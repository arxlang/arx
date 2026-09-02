# Design: Python AST to ASTx lowering

Status: staged implementation. Source extraction, Python-subset validation,
signature reconciliation, and initial fail-closed ASTx lowering are implemented.
IRx compilation, native bridging, caching, and dispatch are not.

## Goal

Compile a restricted subset of pure, built-in Python through the existing Arx
compiler stack. Users write ordinary Python and add `@jit`; they do not embed
Arx source strings or opt into another compiler backend.

## Pipeline status

```text
pure Python function
  -> source extraction       implemented
  -> Python AST validation   implemented
  -> signature resolution    implemented
  -> ASTx lowering           initial straight-line subset
  -> IRx/LLVM compilation    not implemented
  -> native call bridge      not implemented
```

`arxjit` owns source handling, validation, the future Python-to-ASTx lowering,
and the callable wrapper. ASTx owns the node model, while IRx owns semantic
analysis, LLVM lowering, native runtime features, and artifact generation. The
Arx source frontend is intentionally not in this path.

## Implemented frontend stages

### Decorator and signatures

`arxjit.core.jit` returns a `JitFunction` that preserves the original function
and records an optional explicit `Signature` plus the requested `cache` flag.
`JitFunction.__call__` currently calls the original Python function directly.

The current scalar signature vocabulary is:

- `i32` -> `astx.Int32`
- `i64` -> `astx.Int64`
- `f32` -> `astx.Float32`
- `f64` -> `astx.Float64`
- `bool_` -> `astx.Boolean`

The `astx_name` metadata records the future lowering target; it does not mean
that lowering already happens.

### Source extraction

`arxjit.source.extract_source()`:

- unwraps decorated functions before inspection
- retrieves the defining file and exact function source
- removes decorators from the parsed function node
- preserves real-file line and column locations, including nested functions
- carries globals, closure names, and qualified-name context for validation
- translates retrieval and parse failures into structured diagnostics

Source defined only through `exec`, lambdas, builtins, and other objects without
retrievable function source are rejected.

### Validation

`arxjit.validation.validate()` fails closed: an AST form must have an explicit
accepted handler. The current proposed scalar subset includes:

- positional scalar arguments
- numeric and Boolean constants
- arithmetic, comparisons, Boolean expressions, and supported unary operators
- single-name assignments
- `if`/`else` and `while` without loop `else`
- `for` over the unshadowed builtin `range` with one to three positional args
- `return`, docstrings, and `pass`

Unsupported forms produce one structured diagnostic per violation. Examples
include imports, closures, methods, async code, exceptions, generators,
collections, attributes, subscripting, comprehensions, `break`/`continue`,
variadic/default arguments, and arbitrary calls.

## Implemented ASTx mapping

The following straight-line mappings are implemented by `arxjit.lowering`:

| Python AST                        | Proposed ASTx target                            |
| --------------------------------- | ----------------------------------------------- |
| `ast.FunctionDef`                 | `astx.FunctionDef` and `astx.FunctionPrototype` |
| argument                          | `astx.Argument` inside `astx.Arguments`         |
| `ast.Return`                      | `astx.FunctionReturn`                           |
| `ast.Name`                        | identifier/variable reference                   |
| numeric or Boolean `ast.Constant` | matching typed literal node                     |
| `ast.BinOp`                       | `astx.BinaryOp`                                 |
| `ast.UnaryOp`                     | `astx.UnaryOp`                                  |
| `ast.Compare`                     | comparison expression                           |
| statement body                    | `astx.Block`                                    |

The lowerer builds a single-function `astx.Module`, uses the reconciled
`Signature`, range-checks contextual literal widths, preserves source locations,
mangles names reserved by IRx, and lowers expressions bottom-up. Boolean
short-circuiting, chained comparisons, assignments, `if`, `while`, and `for`
remain fail-closed because their Python evaluation semantics are not yet
preserved. IRx remains the only owner of semantic analysis and feature lowering.

## Compilation and runtime work remaining

After lowering, the design hands the module to `irx.builder.Builder` for
translation and native artifact generation. ArxJIT still needs:

1. assignment and control-flow ASTx lowering with Python semantics
2. an in-process native callable bridge and scalar marshalling
3. compilation and dispatch integration in `JitFunction.__call__`
4. a cache key covering source, signature, tool versions, and platform

Signature inference is deferred; an explicit `signature=` remains the intended
first compilation contract. Array, Tensor, and Apache Arrow-backed signatures
are also deferred until scalar compilation and marshalling are stable.
