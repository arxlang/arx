# Roadmap

This roadmap lists remaining work. For implemented behavior, see the
[ecosystem status](ecosystem.md) and language reference.

## Completed foundations

The current monorepo already provides:

- indentation-sensitive Arx parsing with typed functions and variables
- structured control flow, imports, classes, templates, assertions, and tests
- ASTx as the shared node model
- IRx semantic analysis, structured diagnostics, LLVM lowering, and linking
- on-demand native runtime features
- Apache Arrow C++ arrays, tensors, tables, Series, and RecordBatch IPC
- static-schema Arx DataFrames and fixed-shape numeric tensors
- ArxPy and ArxJIT package foundations

## Native Arrow and collections

- [ ] Add dynamic indexing for runtime-shaped Tensor parameters.
- [ ] Define ownership and return semantics for runtime-shaped Tensor values.
- [ ] Add runtime validation when an unknown shape or row count flows into a
      statically sized target.
- [ ] Support partial Tensor constraints such as `tensor[f64, 2, ...]`.
- [ ] Add symbolic shape parameters for generic algorithms.
- [ ] Expand the Arx DataFrame surface to UTF-8, nullable, and temporal columns
      already represented by lower-level Arrow facilities.
- [ ] Define an Arx-facing RecordBatch and streaming surface.
- [ ] Add selected Arrow Compute operations without turning IRx into a general
      query engine.
- [ ] Complete dynamic-list storage reclamation and collection ownership.

## Arx language

- [ ] Stabilize language semantics and publish a versioned language
      specification beyond the lexical manifest.
- [ ] Decide the final `const` declaration behavior; it is currently reserved
      lexically but not a general parsed declaration form.
- [ ] Add `break` and `continue` to the Arx surface after aligning parser, ASTx,
      IRx, and documentation behavior.
- [ ] Expand string, temporal, and collection operations.
- [ ] Define constructor arguments and richer class lifecycle behavior.
- [x] Remove the unimplemented `arx --shell` option from the stable CLI. An
      interactive shell can return later as a separately designed feature.
- [ ] Grow the bundled pure-Arx standard library.

## IRx and ASTx

- [ ] Continue separating stable public APIs from internal helper nodes.
- [ ] Expand lowering coverage without implying that every ASTx node must have
      an LLVM implementation.
- [ ] Stabilize native runtime ownership and ABI compatibility guarantees.
- [ ] Improve API documentation generated from Douki Python docstrings.
- [ ] Add explicit compatibility documentation for Python, llvmlite, LLVM, and
      native C++ toolchains.

## Python entry points

### ArxPy

- [ ] Add parse-from-string and parse-from-file APIs.
- [ ] Add compile, artifact, and execution result objects.
- [ ] Translate all Arx and IRx failures into the public ArxPy hierarchy.

### ArxJIT

- [ ] Connect source extraction and validation to `@jit`.
- [x] Add fail-closed ASTx lowering for the scalar function shell and
      straight-line literal, parameter, arithmetic, unary, and comparison
      expressions.
- [ ] Extend ASTx lowering to assignments and validated control flow.
- [ ] Compile and call native functions through IRx.
- [ ] Implement signature inference, runtime marshalling, and caching.
- [ ] Add Arrow-backed array and tensor signatures after scalar compilation is
      stable.

## Release readiness

- [ ] Define stability levels and compatibility policies for each package.
- [ ] Publish complete migration notes for breaking language or API changes.
- [ ] Expand cross-platform native-runtime coverage.
- [ ] Provide end-user binary/toolchain installation guidance for supported
      platforms.
