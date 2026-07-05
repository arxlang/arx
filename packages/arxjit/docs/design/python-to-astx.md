# Design notes: Python AST to ASTx lowering

Status: draft for Sprint 1. Describes the intended pipeline for `arxjit`; only
the type API (`SigType` / `Signature`) and the `@jit` decorator surface exist
today. Lowering and compilation land in later sprints.

## Goal

Compile a restricted subset of pure, built-in Python through the existing Arx
stack, so a user writes ordinary Python and adds `@jit` — no Arx source strings,
no new compiler backend.

## Pipeline

```
pure Python function
  -> Python AST            (stdlib `ast`)
  -> validation            (accept only the supported subset)
  -> ASTx                  (astx nodes)
  -> irx.builder.Builder   (translate / build / run -> LLVM -> native)
  -> Python-callable wrapper
```

`arxjit` owns only the first three arrows plus the wrapper. `astx` provides the
node model; `irx` (dist `pyirx`) owns everything from ASTx down to the native
binary. `arxlang` is intentionally not involved — this path reaches ASTx from
Python, not from Arx source.

## Where the current code plugs in

- `arxjit.types.SigType` / `Signature` — the type vocabulary the user writes
  (`i64(i64, i64)`). Each `SigType` already records its target astx class name
  (`i64 -> "Int64"`).
- `arxjit.core.jit` / `JitFunction` — the decorator surface. `JitFunction`
  stores `py_func`, `signature`, and `cache`, and preserves the original
  function.
- Today `JitFunction.__call__` runs `py_func` directly (Python fallback). In
  later sprints it will, on first call for a given signature: extract source,
  parse, validate, lower to an `astx.Module`, compile via `irx`, cache the
  compiled callable, then convert arguments and dispatch.

## Type mapping (SigType to astx)

Driven by `SigType.astx_name`; the literal node is used when lowering a constant
of that type.

- `i32` -> `astx.Int32` (literal: `astx.LiteralInt32`)
- `i64` -> `astx.Int64` (literal: `astx.LiteralInt64`)
- `f32` -> `astx.Float32` (literal: `astx.LiteralFloat32`)
- `f64` -> `astx.Float64` (literal: `astx.LiteralFloat64`)
- `bool` -> `astx.Boolean` (literal: `astx.LiteralBoolean`)

## Node mapping (Python AST to astx)

For the v1 supported subset only. Unsupported nodes are rejected by the
validation pass with a clear diagnostic.

- Module wrapper -> `astx.Module`
- `ast.FunctionDef` -> `astx.FunctionDef` (via `astx.FunctionPrototype` for the
  signature and an `astx.Block` for the body)
- `ast.arg` (typed parameter) -> `astx.Argument`, grouped in `astx.Arguments`;
  the argument type comes from the `Signature`
- `ast.Return` -> `astx.FunctionReturn`
- `ast.Assign` (single local target) -> `astx.VariableAssignment` (first binding
  may emit `astx.VariableDeclaration`)
- `ast.Name` (load) -> `astx.Variable` / `astx.Identifier`
- `ast.Constant`:
  - `int` -> `astx.LiteralInt64` (or `LiteralInt32` per the declared type)
  - `float` -> `astx.LiteralFloat64`
  - `bool` -> `astx.LiteralBoolean`
- `ast.BinOp` (`+ - * /`) -> `astx.BinaryOp`
- `ast.UnaryOp` -> `astx.UnaryOp`
- `ast.Compare` (`< <= > >= == !=`) -> `astx.CompareOp`
- `ast.BoolOp` (`and` / `or`) -> `astx.BinaryOp` (boolean operator)
- `ast.If` -> `astx.IfStmt`
- `ast.While` -> `astx.WhileStmt`
- `ast.For` over `range(...)` -> `astx.ForRangeLoopStmt`
- function body / block -> `astx.Block`

## Lowering approach

A visitor walks the validated Python AST and builds one `astx.Module` containing
a single `astx.FunctionDef`:

1. Build the prototype from the `Signature` (return type + argument types) and
   the parameter names from the Python function.
2. Lower the body statement by statement into an `astx.Block`.
3. Lower expressions bottom-up (constants and variables first, then operators),
   so each parent node receives already-lowered children.

Keeping one function per module for v1 mirrors how the Arx compiler feeds ASTx
into `irx`, and sidesteps cross-function resolution.

## Compilation handoff

The `astx.Module` is handed to `irx.builder.Builder`:

- `.translate(node)` -> LLVM IR as text (useful for debug output).
- `.build(node, output_file)` -> native object / executable artifact.
- `.run(...)` -> build and execute.

`arxjit` calls into this; it does not reimplement any of it. The runtime bridge
(converting Python scalars to native values and back) is a separate concern
handled in the runtime sprint.

## Deferred / open questions

- Annotations vs. explicit `signature=`: v1 treats `signature=` as the source of
  truth; annotation-based inference is a later enhancement.
- Array types (`i64[2, 2]`): `SigType` was named to stay neutral so array forms
  can be added later via subscripting; not in v1.
- Cache-key contents (source, signature, tool versions, platform): defined in
  the caching sprint.
