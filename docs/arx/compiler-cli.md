# Arx Compiler CLI

The `arxlang` distribution installs the `arx` command. It can inspect frontend
and lowering stages, compile native artifacts, run executables, and execute
compiled tests.

## Command forms

```text
arx [input_file] [options]
arx run [input_file] [options]
arx test [paths ...] [options]
```

`run` is an alternate spelling of `--run`. `test` is a separate subcommand.

## Inspection modes

```bash
arx --show-tokens program.x
arx --show-ast program.x
arx --show-llvm-ir program.x
```

| Option           | Output                                  |
| ---------------- | --------------------------------------- |
| `--show-tokens`  | lexer tokens and source positions       |
| `--show-ast`     | parser output expressed as ASTx nodes   |
| `--show-llvm-ir` | LLVM IR after IRx analysis and lowering |

These modes stop after printing the requested representation.

## Build and run

```bash
arx program.x --output-file program
arx --run program.x
arx run program.x
```

The compiler emits an executable when the module defines `main`. Without a
native entry point, or with `--lib`, it emits an object artifact instead.

| Option                       | Purpose                                         |
| ---------------------------- | ----------------------------------------------- |
| `--output-file PATH`         | select the object or executable path            |
| `--lib`                      | emit a library/object artifact                  |
| `--run`                      | build and run an executable                     |
| `--link-mode MODE`           | use `auto`, `pie`, or `no-pie` linking          |
| `--diagnostic-format FORMAT` | use `human` or versioned `json` errors          |
| `--traceback`                | expose Python tracebacks for compiler debugging |
| `--version`                  | print the installed version                     |

Compiling multiple input files in one invocation is not currently supported. Use
[project-aware imports](projects.md#imports) to compile a module graph from one
entry file.

## Output path

`--output-file` accepts the requested artifact path. If it is omitted, the
compiler derives a name from the entry source file and otherwise falls back to
`a.out`.

## Link modes

The default `auto` mode uses the platform toolchain's default executable mode.
`pie` and `no-pie` request explicit position-independent or non-PIE linking.

If a linker defaults to PIE but rejects an object relocation, use:

```bash
arx program.x --link-mode no-pie
```

IRx emits PIC-compatible objects by default. Explicit link modes are primarily
toolchain compatibility controls.

## Diagnostics

Expected lexer, parser, semantic, lowering, native compilation, and linking
failures exit with status 1. Human-readable diagnostics go to standard error by
default. Unexpected internal failures produce `ARX-INTERNAL-001` without
exposing exception details and exit with status 70. Compiler developers can opt
in to the original Python exception and traceback with `--traceback`.

Use `--diagnostic-format json` for one versioned JSON document on standard
error:

```json
{
  "diagnostics": [
    {
      "code": "ARX-PARSE-001",
      "column": 7,
      "end_column": null,
      "end_line": null,
      "hint": null,
      "line": 4,
      "message": "expected expression",
      "module": null,
      "notes": [],
      "phase": "frontend",
      "severity": "error"
    }
  ],
  "schema_version": 1
}
```

JSON mode covers expected compiler-phase failures and sanitized internal
failures. Argument usage errors remain argparse text with exit status 2.
Consumers must reject unsupported `schema_version` values instead of guessing
field semantics.

| Exit status | Meaning                              |
| ----------- | ------------------------------------ |
| 0           | command succeeded                    |
| 1           | expected compiler/source failure     |
| 2           | CLI usage or input-path failure      |
| 70          | unexpected internal compiler failure |

## Tests

The `arx test` subcommand has its own discovery and execution options. See
[Compiled Tests](testing.md).

## API boundary

CLI argument handling lives in Arx. Semantic diagnostics, LLVM lowering,
artifact building, and runtime feature activation are provided by IRx.
