# ArxLang

ArxLang is an experimental compiler ecosystem for statically typed,
data-oriented programs. The Arx frontend turns indentation-based source into
ASTx nodes; IRx performs semantic analysis, lowers the program to LLVM IR, and
builds native artifacts.

## Apache Arrow, natively

Apache Arrow is not an optional serialization afterthought in ArxLang. IRx owns
a native C++ runtime that stores and exchanges data through Arrow containers:

- arrays use Arrow C++ builders and Arrow C Data interoperability
- tensors use `arrow::Tensor`
- DataFrames use `arrow::Table`
- Series use `arrow::ChunkedArray`
- RecordBatch streams use Arrow IPC in files or memory buffers

Generated LLVM calls a stable IRx-owned C ABI, keeping Arrow ownership and
container implementation in native runtime code. Native artifacts are linked
only when the compilation unit activates the corresponding runtime feature.

[Explore native Apache Arrow support](apache-arrow.md){.btn .btn-primary}
[View ecosystem status](ecosystem.md){.btn .btn-secondary}

## Quick example

````arx
```
title: Arrow-backed DataFrame example
summary: Builds named columns and reads native table metadata.
```

fn main() -> i32:
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  var scores: series[f64] = rows.score
  return cast(rows.nrows(), i32)
````

```bash
arx --show-llvm-ir example.x
arx --run example.x
```

## Compiler pipeline

```text
Arx or AIX source
  -> frontend lexer and parser
  -> ASTx nodes
  -> IRx semantic analysis
  -> LLVM lowering
  -> on-demand native runtime features, including Arrow C++
  -> object file or executable
```

ASTx, IRx, and the language frontends have deliberately separate ownership:

- **ASTx** models syntax trees but does not parse source or generate code.
- **IRx** owns semantics, lowering, runtime features, and LLVM code generation.
- **Arx** and **AIX** own their source syntax, lexers, parsers, and CLIs.
- **PyArx** and **ArxJIT** are developing Python-facing entry points.

## Current status

The project is a pre-production prototype. Arx can compile functions, typed
variables, control flow, imports, classes, templates, lists, tensors,
DataFrames, assertions, and tests. Supported behavior is covered by the local
test suites, but language and package APIs are not yet stable.

The [ecosystem status](ecosystem.md) distinguishes implemented behavior from
planned work for all six subprojects. The [roadmap](roadmap.md) tracks only
remaining work rather than presenting completed features as pending.

## Next steps

- [Install Arx and compile a program](getting-started.md)
- [Read the language reference](library/index.md)
- [Understand ASTx](astx/index.md)
- [Understand IRx](irx/index.md)
- [Contribute](contributing.md)
