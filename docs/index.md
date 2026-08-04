---
title: ""
pagetitle: ArxLang compiler ecosystem
description: >-
  Documentation for the Arx language, ASTx, IRx, LLVM compilation, and native
  Apache Arrow support.
page-layout: full
toc: false
sidebar: false
---

<div class="arx-home">

<div class="arx-hero">
<div class="arx-hero-inner">
<div class="arx-hero-copy">

<div class="arx-eyebrow">ArxLang</div>

# ArxLang compiler ecosystem

<div class="arx-hero-lead">

ArxLang is an experimental statically typed language and compiler toolchain. The
Arx frontend parses source into ASTx nodes. IRx performs semantic analysis,
lowers supported nodes to LLVM IR, and builds native artifacts. IRx also
provides runtime components for Apache Arrow-backed collections.

</div>

<div class="arx-hero-actions">

[Getting started](getting-started.md){.btn .btn-primary}
[Apache Arrow support](apache-arrow.md){.btn .btn-outline-primary}

</div>

<div class="arx-tech-list">
<span>Python 3.10+</span>
<span>LLVM</span>
<span>Apache Arrow C++</span>
<span>Apache-2.0</span>
</div>

</div>

<div class="arx-code-window">
<div class="arx-code-window-header">example.x</div>

````arx
```
title: Arrow-backed rows
```
fn main() -> i32:
  var rows: dataframe[id: i32, score: f64] = dataframe({
    id: [1, 2, 3],
    score: [0.5, 0.8, 1.0],
  })
  return cast(rows.nrows(), i32)
````

</div>
</div>
</div>

<div class="arx-home-section">
<div class="arx-section-heading">

## Compiler architecture

The compilation path separates source parsing, program representation, semantic
analysis, LLVM lowering, and runtime integration. Each package owns a defined
part of that path.

</div>

<div class="arx-feature-grid">
<div class="arx-feature-card">

<div class="arx-card-kicker">Arx</div>

### Source frontend

Arx owns indentation-sensitive syntax, modules, classes, templates, tests, and
the compiler CLI. The parser emits ASTx nodes rather than an Arx-specific AST
model.

</div>

<div class="arx-feature-card">

<div class="arx-card-kicker">ASTx</div>

### Shared AST model

ASTx provides language-independent nodes for types, expressions, statements,
functions, control flow, classes, templates, and collections. Frontends and
backends use the same model.

</div>

<div class="arx-feature-card">

<div class="arx-card-kicker">IRx</div>

### Analysis and LLVM backend

IRx analyzes symbols, calls, types, control flow, templates, classes, and FFI
contracts. It lowers the supported ASTx subset to LLVM IR and activates native
runtime features when they are required.

</div>
</div>
</div>

<div class="arx-home-section">
<div class="arx-section-heading">

## Packages

Package pages describe implemented behavior, known limitations, and planned
work. The labels below summarize the current maturity of each primary package.

</div>

<div class="arx-package-grid">
<div class="arx-package-card">

<span class="arx-status">Functional prototype</span>

### Arx

The source language, lexer, parser, project model, test runner, and native
compiler CLI.

[Arx documentation →](library/index.md)

</div>

<div class="arx-package-card">

<span class="arx-status">Functional, evolving</span>

### ASTx

A language-agnostic Python model for typed abstract syntax trees and compiler
tooling.

[ASTx documentation →](astx/index.md)

</div>

<div class="arx-package-card">

<span class="arx-status">Functional experimental backend</span>

### IRx

Semantic analysis, LLVM lowering, native artifacts, diagnostics, and runtime
feature activation.

[IRx documentation →](irx/index.md)

</div>

<div class="arx-package-card">

<span class="arx-status">API foundation only</span>

### PyArx

The developing Python-facing compiler API, currently focused on structured
diagnostics and public error types.

[PyArx documentation →](pyarx/index.md)

</div>

<div class="arx-package-card">

<span class="arx-status">Frontend foundations only</span>

### ArxJIT

A developing decorator route from a restricted Python subset to ASTx and IRx;
decorated calls still use Python fallback today.

[ArxJIT documentation →](arxjit/index.md)

</div>
</div>
</div>

<div class="arx-home-section">
<div class="arx-arrow-band">
<div class="arx-arrow-copy">

<div class="arx-eyebrow">IRx native runtime</div>

## Apache Arrow integration

IRx includes a native Apache Arrow C++ runtime. Generated LLVM calls an
IRx-owned C ABI, while Arrow C++ manages container layout and ownership. The
required runtime artifacts are compiled and linked when a program uses the
corresponding feature.

[Implementation details and current limits →](apache-arrow.md)

</div>

<div class="arx-arrow-details">
<ul class="arx-arrow-list">
  <li>Arrays with Arrow C Data interoperability</li>
  <li>Tensors backed by <code>arrow::Tensor</code></li>
  <li>DataFrames backed by <code>arrow::Table</code></li>
  <li>Series backed by <code>arrow::ChunkedArray</code></li>
  <li>RecordBatch IPC and PyArrow round trips</li>
</ul>
</div>
</div>
</div>

<div class="arx-home-section">
<div class="arx-status-note">

**Project status:** The primary packages are pre-production. Documented
implemented behavior is tested, but language semantics and package APIs can
still change. See the [ecosystem status](ecosystem.md) for current capabilities
and limitations, and the [roadmap](roadmap.md) for planned work.

</div>
</div>

</div>
