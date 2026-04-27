# Roadmap

The roadmap document define the direction that the project is taking.

The initial and decisive part of the project is the implementation of native
tensor abstractions backed by Apache Arrow. But in order to get to that point,
we need first implement a bunch of small pieces across the Arx + IRx stack. Arx
owns the surface front end (lexer, parser, docs, examples), while IRx owns AST
definitions, semantic analysis, lowering, and code generation.

## Improve the language structure

- [ ] Currently, almost everything is a expression, but some structure should be
      converted to statements.
  - [ ] `For` loop
  - [ ] `If`
  - [ ] Implement `return` keyword
- [ ] Allow multiple lines in a block
- [ ] Add support for `while` loop
- [ ] Add support for `switch`
- [ ] Add support for code structure defined by indentation
- [ ] Add support packaging and `import`
- [ ] Add support for `docstring`
- [x] Add support for file objects generation
- [ ] Add support for generating executable files
- [ ] Add support for mutable variables
- [ ] Add support for classes (details TBA)

## Data type support

ArxLang is based on [Kaleidoscope compiler](https://llvm.org/docs/tutorial/), so
it just implements float data type for now.

In order to accept more datatypes, the language should have a way to specify the
type for each variable and function returning.

- [x] Wave 1: float32
- [ ] Wave 2: static typing
- [ ] Wave 3: int8, int16, int32, int64
- [ ] Wave 4: float16, float64
- [ ] Wave 5: string
- [ ] Wave 6: datetime

## Implement native tensors

Native tensors now have an initial Arrow C++ backed implementation. Remaining
work should continue to make runtime-shaped tensor values usable in more
contexts, while preserving the same runtime-layout rules for every collection
type that uses that approach.

- [ ] Expand runtime-layout annotations beyond function and extern parameters
      once default values, ownership, and type checking are ready for local
      declarations and expression contexts.
- [ ] Keep tensor semantics aligned with the Arrow-backed runtime rather than
      adding Arx-local lowering behavior.

## DataFrames and Series

DataFrames are a distinct public collection abstraction for heterogeneous named
columns. Static-schema values use `dataframe[name: T, ...]`, column views use
`series[T]`, and literals are constructed with `dataframe({...})`.

- [x] Add the builtin `dataframe[...]` type.
- [x] Add the builtin `series[T]` type for typed DataFrame columns.
- [x] Add the builtin `dataframe({...})` constructor for column-oriented
      literals.
- [x] Back DataFrame values with Arrow C++ `arrow::Table`.
- [x] Back Series values with Arrow C++ `arrow::ChunkedArray`.
- [x] Keep the MVP limited to fixed-width numeric and `bool` columns.
- [ ] Add string, nullable, nested, temporal, and user-defined column support
      after the fixed-width MVP is stable.
- [ ] Expand runtime-layout/schema annotations beyond function and extern
      parameters, applying the same behavior to both `dataframe[...]` and
      `tensor[T, ...]`.

## Type System Follow-ups

- [ ] Add parser-level support for optional list, tensor, series, and dataframe
      size/shape annotations once the surface-syntax restrictions are ready to
      change.
- [ ] Add runtime check sidecars for assigning unknown-size values to sized
      targets, including list length, tensor shape, series length, and dataframe
      row count; sized annotations must not become trusted metadata until the
      runtime check has passed.
- [ ] Add support for partial tensor shape constraints using ellipsis, such as
      `tensor[f64, 2, ...]`, `tensor[f64, ..., 3]`, and
      `tensor[f64, 2, ..., 3]`.
- [ ] Add symbolic shape variables for generic algorithms, such as
      `fn dot[N](a: tensor[f64, N], b: tensor[f64, N])`.
