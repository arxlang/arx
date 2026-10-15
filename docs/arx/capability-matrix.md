# Arx Capability Matrix

## How to read this matrix

This matrix distinguishes end-to-end Arx support from lexical reservation and
ASTx modeling. `Complete` means the checked-out repository has the relevant
pipeline path and tests; it does not yet imply a frozen compatibility promise.
`Partial` means users must follow the linked/current limitations. `Reserved`
means the spelling is recognized but must not be advertised as usable.

| Construct                                    | Lex/parse                                                  | Semantics                                             | LLVM/runtime                                                 | Current status                                                                     |
| -------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Typed scalar functions and returns           | Complete                                                   | Complete                                              | Complete                                                     | Production candidate                                                               |
| Default arguments                            | Complete                                                   | Complete                                              | Complete                                                     | Production candidate                                                               |
| C extern declarations                        | Complete                                                   | Complete                                              | Complete for supported scalar/pointer forms                  | Partial pending stable FFI ABI                                                     |
| Function templates                           | Complete for current forms                                 | Complete for current forms                            | Complete for tested instantiations                           | Partial pending compatibility specification                                        |
| Typed mutable variables                      | Complete                                                   | Complete                                              | Complete                                                     | Production candidate                                                               |
| General `const` declaration                  | Token reserved                                             | Incomplete                                            | Incomplete                                                   | Reserved                                                                           |
| Scalar arithmetic/comparisons/casts          | Complete for documented operators                          | Boolean operands and numeric conversions validated    | Wrapping integers, checked division, short circuit           | Partial pending floating non-finite/NaN rules; integer and Boolean rules specified |
| `if`/`else` and `while`                      | Complete                                                   | Complete                                              | Complete                                                     | Production candidate                                                               |
| Count and range `for`                        | Complete                                                   | Complete                                              | Complete                                                     | Production candidate                                                               |
| List `for ... in`                            | Complete                                                   | Borrowed iteration over owned/static lists            | Complete for scalar list elements                            | Partial; lifecycle is enforced outside generators                                  |
| `break` and `continue` in Arx source         | Incomplete                                                 | ASTx/IRx support exists                               | IRx support exists                                           | Not an Arx feature yet                                                             |
| Modules and imports                          | Complete from one entry graph                              | Complete                                              | Complete                                                     | Partial pending cycle/init specification                                           |
| Multiple direct CLI entry files              | Rejected early                                             | Not applicable                                        | Not applicable                                               | Unsupported; use imports                                                           |
| Source resource limits and locations         | UTF-8/size/token/nesting limits; one-based Unicode columns | Not applicable                                        | Not applicable                                               | Implemented; compatibility freeze pending                                          |
| Classes, fields, methods, inheritance        | Complete for documented subset                             | Complete for documented subset                        | Complete for documented subset                               | Partial pending lifecycle and ABI                                                  |
| Constructor arguments/bodies and destruction | Incomplete                                                 | Incomplete                                            | Incomplete                                                   | Not supported                                                                      |
| Finite union aliases/casts/type queries      | Complete                                                   | Complete                                              | Complete for tested forms                                    | Experimental candidate                                                             |
| Strings, concatenation, casts, and returns   | Complete for current scalar forms                          | Static/borrow/owner/copy/move rules enforced          | Checked allocation plus lexical cleanup                      | Partial; immutable pointer ABI, no owned fields/generators/external returns        |
| Literal and dynamic lists                    | Complete                                                   | Owner/borrow/move/return rules enforced               | Checked append/index plus lexical cleanup                    | Partial; scalar elements and move-only values                                      |
| Fixed-shape numeric tensors                  | Complete                                                   | Complete                                              | Complete for tested readonly paths                           | Experimental candidate                                                             |
| Runtime-shaped tensor parameters             | Complete for documented syntax                             | Partial                                               | Partial                                                      | No general dynamic indexing/return ownership                                       |
| Static-schema DataFrame/Series               | Complete                                                   | Primitive and executable logical columns              | Native typed columns and explicit adapters                   | Experimental candidate                                                             |
| Runtime-schema DataFrame named access        | Partial modeling                                           | Incomplete                                            | Incomplete                                                   | Not supported                                                                      |
| Arrow-core type/field/schema descriptors     | Builtin literals and closed queries                        | Canonical validation, physical and ownership sidecars | Native Arrow C++ construction, projection and exact identity | Experimental; descriptor support is not full container support                     |
| RecordBatch/PyArrow Python API               | Not Arx syntax                                             | Python validation                                     | Native Arrow C++ bridge                                      | Experimental Python API                                                            |
| Assertions and `arx test`                    | Complete                                                   | Complete                                              | Complete                                                     | Production candidate after error semantics freeze                                  |
| Douki docstrings                             | Complete validation                                        | Omitted intentionally                                 | Not applicable                                               | Supported validation-only feature                                                  |
| Operator declarations                        | Tokens reserved                                            | Incomplete                                            | Incomplete                                                   | Reserved                                                                           |
| `then` keyword                               | Token reserved                                             | Incomplete                                            | Incomplete                                                   | Reserved                                                                           |
| Interactive shell                            | Removed from CLI                                           | Not applicable                                        | Not applicable                                               | Non-goal for first production release                                              |
| ArxPy compiler facade                        | Parse string/file complete                                 | Check complete                                        | Host IR/object/executable/run complete                       | Pre-stable; cancellation/targets/queries remain                                    |

## Cross-stage rule

A row can move to the stable Arx 1 set only when the syntax manifest, token
definitions, parser, ASTx nodes, IRx analysis, LLVM lowering, native runtime,
exports, positive and negative tests, examples, and documentation all agree as
applicable. Unsupported input must fail at the earliest responsible boundary.

Primitive nullable scalars now have normalized ASTx/IRx types, explicit validity
storage, source-level locals and function boundaries, and checked unwrapping.
See [the builtin reference](built-in-types.md#primitive-nullable-scalars).
Primitive nullable operators, direct predicate narrowing and first-class
primitive arrays now have native execution paths. Reusable primitive builders,
chunked arrays and nullable shared array/descriptor owners also execute
natively. Nullable strings and unique builders, nested logical values, typed
batch/table operations, explicit legacy adapters, extension storage and checked
C Data/buffer construction also execute natively. General nullable language
collections and managed by-value struct destruction remain pending; M4 is not
complete. Fatal cleanup currently covers the active generated function, not
owned caller frames.
