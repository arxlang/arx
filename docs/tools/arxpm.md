# ArxPM

[ArxPM](https://github.com/arxlang/arxpm) is the project manager and workspace
tool for Arx. It is a separate Python package and installs the `arxpm` command.

> **Status:** ArxPM implements project and environment workflows, but its
> interfaces and manifest integration are still evolving with the compiler.

## Responsibility

The boundary between the two commands is:

- `arx` compiles source files and resolves project-aware imports.
- `arxpm` manages manifests, layouts, environments, dependencies, builds,
  execution, packaging, and publishing workflows.

ArxPM currently uses typed manifest models, validates effective project layout,
provisions Python environments, stores publishing credentials through the system
keyring, and invokes the compiler for build and run operations.

## Commands

The current command surface includes:

```text
arxpm init
arxpm config
arxpm install
arxpm add <requirement> [--path PATH | --git URL]
arxpm build
arxpm compile
arxpm run
arxpm pack
arxpm publish
arxpm healthcheck
```

Consult `arxpm --help` for the options supported by the installed version.

## Project metadata

ArxPM works with Arx project metadata and environment configuration. The
compiler documents the currently accepted `.arxproject.toml` fields in
[Projects and Imports](../arx/projects.md).

ArxPM owns dependency installation. Arx import resolution does not download or
install packages while compiling.

## Current considerations

- ArxPM and Arx are released independently, so manifest and CLI compatibility
  must be checked for the installed versions.
- Project and package publishing workflows require external package indexes and
  credentials.
- Integration tests require the `arx` and `uv` executables on `PATH`.

Source and detailed usage:
[github.com/arxlang/arxpm](https://github.com/arxlang/arxpm)
