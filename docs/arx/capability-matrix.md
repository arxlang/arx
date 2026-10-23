# Arx Capability Matrix

This is the compact end-to-end support boundary, not a method catalog or a
stability promise. Tokenization or an ASTx node alone does not establish Arx
support. Package APIs and syntax may change before Arx 2.0 with coordinated
caller updates and concise migration notes.

| Area                                                                  | Supported boundary                                                                                            | Important limits                                                                                                                        |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| [Functions](functions.md) and [types](datatypes.md)                   | Explicit annotations, defaults, named calls, bounded templates, finite numeric unions                         | No inferred local declarations, argument unpacking, or keyword-only declarations; no runtime tagged unions                              |
| [Numeric safety](specification.md#fixed-width-integer-overflow)       | Lossless promotion, checked integer arithmetic/casts, explicit wrapping                                       | 8–64-bit integers; no bigint fallback; dynamic failures are fatal, not recoverable                                                      |
| [Control flow](control-flow.md)                                       | `if`/`else`, `while`, count loops, scalar-list `for ... in`                                                   | No Arx `break`, `continue`, general generators, `with`, or recoverable `try`/`except`, even where IRx has nodes                         |
| [Modules](modules.md) and [projects](projects.md)                     | One entry graph; local, relative, namespace, stdlib and installed imports                                     | Cycles fail; no multiple direct CLI entries or executable module-level initialization                                                   |
| [Classes](classes.md) and [files](file-io.md)                         | Acyclic shared identities, lifecycle hooks, string/File/class fields                                          | No owning list/Arrow fields, class containers, cycles, general foreign object ABI, or fatal cross-frame unwinding                       |
| [Lists](collections.md#lists) and strings                             | Enforced owner/borrow/move cleanup; builtin `range` returns an allocated list                                 | No general copy operation, mutable list parameters, or owning generator captures                                                        |
| [Tensors](collections.md#tensors)                                     | Readonly fixed-shape numeric values; runtime-shaped parameters                                                | No dynamic indexing or general runtime-shaped returns                                                                                   |
| [DataFrames and Series](collections.md#dataframes-and-series)         | Static/rich schemas, runtime-schema locals/returns, exact checked casts, numeric/Boolean nullable expressions | No unchecked runtime column access; rich storage does not imply rich scalar arithmetic                                                  |
| [CSV](csv.md), [Parquet](parquet.md), [Arrow IPC](../apache-arrow.md) | Eager chunked frames, explicit streams, snapshots, C Data/C Stream interchange                                | Native toolchain required; format restrictions apply; compiled operational failures are fatal; TCP is blocking/POSIX without TLS/Flight |
| [Native packages](native-packages.md)                                 | Declarative registered C ABI dependencies                                                                     | No raw-pointer source API, callbacks, plugins, or stable general FFI ABI                                                                |
| [CLI](compiler-cli.md) and [tests](testing.md)                        | Inspect, compile, run, and isolated compiled tests; structured diagnostics                                    | Host toolchain controls linking; no interactive shell                                                                                   |
| [Docstrings](docstrings.md) and [lexical syntax](syntax.md)           | Douki validation, UTF-8 source limits, Unicode locations                                                      | Docstrings are omitted from AST/IR; `const`, `then`, and operator declarations remain reserved                                          |

[ArxPy](../arxpy/index.md) provides Python parse/check/compile/run workflows.
[ArxJIT](../arxjit/index.md) still executes Python fallback, not native
dispatch.

A support claim needs aligned frontend, ASTx, semantics, lowering/runtime,
exports, and positive/negative tests. Unsupported input must fail at the
earliest responsible boundary. Keep [preview safety contracts](specification.md)
and necessary workflow guidance synchronized; adding an API does not require
another handwritten reference page.
