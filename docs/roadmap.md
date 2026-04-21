# Roadmap

The roadmap document define the direction that the project is taking.

The initial and decisive part of the project is the implementation of native
array abstractions backed by Apache Arrow. But in order to get to that point, we
need first implement a bunch of small pieces across the Arx + IRx stack. Arx
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

## Implement native arrays

TBA
