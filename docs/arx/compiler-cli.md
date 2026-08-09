# Arx Compiler CLI

The `arxlang` distribution installs the `arx` command. It can inspect frontend
and lowering stages, compile native artifacts, run executables, and execute
compiled tests.

## Command forms

```text
arx [input_files ...] [options]
arx run [input_files ...] [options]
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

| Option               | Purpose                                            |
| -------------------- | -------------------------------------------------- |
| `--output-file PATH` | select the object or executable path               |
| `--lib`              | emit a library/object artifact                     |
| `--run`              | build and run an executable                        |
| `--link-mode MODE`   | use `auto`, `pie`, or `no-pie` linking             |
| `--version`          | print the installed version                        |
| `--shell`            | reserved; the interactive shell is not implemented |

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

## Tests

The `arx test` subcommand has its own discovery and execution options. See
[Compiled Tests](testing.md).

## API boundary

CLI argument handling lives in Arx. Semantic diagnostics, LLVM lowering,
artifact building, and runtime feature activation are provided by IRx.
