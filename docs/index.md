---
title: ""
pagetitle: ArxLang — LLVM-native, Arrow-native compiler ecosystem
description: >-
  Build statically typed, data-oriented programs through ASTx, IRx, LLVM, and a
  native Apache Arrow C++ runtime.
page-layout: full
toc: false
sidebar: false
---

:::::: {.arx-home}

::::: {.arx-hero} :::: {.arx-hero-inner} ::: {.arx-hero-copy}

<div class="arx-eyebrow">LLVM-native compiler ecosystem</div>

# Typed programs. Native data. Arrow at the core.

::: {.arx-hero-lead} ArxLang is an experimental compiler ecosystem for
statically typed, data-oriented programs. Arx produces ASTx nodes, IRx resolves
their semantics, and LLVM builds native artifacts backed by an on-demand Apache
Arrow C++ runtime. :::

::: {.arx-hero-actions} [Get started](getting-started.md){.btn .btn-primary}
[Explore native Arrow](apache-arrow.md){.btn .btn-outline-primary} :::

::: {.arx-tech-list} <span>Python 3.10+</span> <span>LLVM</span> <span>Apache
Arrow C++</span> <span>Apache-2.0</span> ::: :::

::: {.arx-code-window} ::: {.arx-code-window-header} example.x :::

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

::: :::: :::::

:::: {.arx-home-section} ::: {.arx-section-heading}

## A deliberately layered compiler

Each project has a focused responsibility. Frontends define syntax, ASTx defines
reusable program structure, and IRx owns semantics, lowering, and native runtime
integration. :::

:::: {.arx-feature-grid} ::: {.arx-feature-card}

<div class="arx-card-kicker">01 · Frontend</div>

### Parse typed source

Arx owns indentation-sensitive syntax, modules, classes, templates, tests, and
the compiler CLI. It emits shared ASTx nodes rather than a private AST model.
:::

::: {.arx-feature-card}

<div class="arx-card-kicker">02 · Semantics</div>

### Resolve before lowering

IRx analyzes symbols, calls, types, control flow, templates, classes, and FFI
contracts before lowering the supported ASTx subset to LLVM IR. :::

::: {.arx-feature-card}

<div class="arx-card-kicker">03 · Runtime</div>

### Activate only what is used

Native features contribute symbols, sources, objects, and linker flags only when
a compilation unit needs them—including the Apache Arrow C++ runtime. ::: ::::
::::

:::: {.arx-home-section} ::: {.arx-section-heading}

## Packages with clear boundaries

The ecosystem is intentionally modular. Package maturity differs, so every
overview distinguishes working behavior from planned work. :::

:::: {.arx-package-grid} ::: {.arx-package-card}
<span class="arx-status">Functional prototype</span>

### Arx

The source language, lexer, parser, project model, test runner, and native
compiler CLI.

[Read the language reference →](library/index.md) :::

::: {.arx-package-card} <span class="arx-status">Functional, evolving</span>

### ASTx

A language-agnostic Python model for typed abstract syntax trees and compiler
tooling.

[Explore ASTx →](astx/index.md) :::

::: {.arx-package-card} <span class="arx-status">Experimental backend</span>

### IRx

Semantic analysis, LLVM lowering, native artifacts, diagnostics, and runtime
feature activation.

[Explore IRx →](irx/index.md) :::

::: {.arx-package-card} <span class="arx-status">API foundation</span>

### PyArx

The developing Python-facing compiler API, currently focused on structured
diagnostics and public error types.

[View PyArx status →](pyarx/index.md) :::

::: {.arx-package-card} <span class="arx-status">Frontend foundations</span>

### ArxJIT

A developing decorator route from a restricted Python subset to ASTx and IRx;
decorated calls still use Python fallback today.

[View ArxJIT status →](arxjit/index.md) ::: :::: ::::

:::: {.arx-home-section} :::: {.arx-arrow-band} ::: {.arx-arrow-copy}

<div class="arx-eyebrow">Native Apache Arrow</div>

## Data infrastructure, not an afterthought

Generated LLVM calls a stable IRx-owned C ABI while Arrow C++ retains container
layout and ownership. Runtime artifacts are compiled and linked on demand.

[See the architecture and current limits →](apache-arrow.md) :::

::: {.arx-arrow-details}

<ul class="arx-arrow-list">
  <li>Arrays with Arrow C Data interoperability</li>
  <li>Tensors backed by <code>arrow::Tensor</code></li>
  <li>DataFrames backed by <code>arrow::Table</code></li>
  <li>Series backed by <code>arrow::ChunkedArray</code></li>
  <li>RecordBatch IPC and PyArrow round trips</li>
</ul>
:::
::::
::::

:::: {.arx-home-section} ::: {.arx-status-note} **Current status:** ArxLang is a
pre-production compiler ecosystem. The documented surface is tested, but
language semantics and package APIs can still change. Review the
[ecosystem status](ecosystem.md) and [roadmap](roadmap.md) before adopting
unstable interfaces. ::: ::::

::::::
