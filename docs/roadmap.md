# Roadmap

The roadmap document define the direction that the project is taking.

The initial and decisive part of the project is the implementation of the Apache
Arrow datatypes as the native datatypes. But in order to get to the point where
we can implement that, we need first implement a bunch of small pieces to the
compiler, in all the phases: lexer, parser, semantic analysis, and code
generator.

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

## Implement Apache Arrow datatypes

TBA
