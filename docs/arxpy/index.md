# ArxPy

ArxPy is the typed Python API for parsing, checking, compiling, and running Arx
programs without invoking the CLI.

## Current status

ArxPy now has a pre-stable end-to-end compiler facade.

Implemented:

- `Diagnostic` and `DiagnosticSeverity`
- conversion helpers for IRx diagnostics and Arx parser failures
- `ArxError` as the public base exception
- `ParseError`, `CompileError`, and `ExecutionError`
- lightweight imports that do not initialize LLVM at module import time
- parse-from-string and parse-from-file entry points through `Compiler`
- semantic checking and structured diagnostic translation
- host LLVM IR, object, and executable artifacts
- captured execution with arguments, environment, working directory, and timeout
- runtime validation of public arguments and every collection item
- serialized repeated/concurrent operations while the frontend uses global input
  state

Not yet stable or implemented:

- cancellation and asynchronous compilation
- cross-target selection and target discovery
- compiler test-discovery facade
- cache controls and a query/LSP protocol
- compatibility guarantees for the pre-1.0 facade

## Install

```bash
pip install arxpy
```

## Usage

```python
from pathlib import Path

from arxpy import ArtifactKind, Compiler

compiler = Compiler()
parsed = compiler.parse_file("program.x")
checked = compiler.check(parsed)
artifact = compiler.compile(
    checked,
    kind=ArtifactKind.EXECUTABLE,
    output=Path("build/program"),
)
result = compiler.run(artifact, timeout=10)
print(result.exit_code, result.stdout, result.stderr)
```

Expected failures expose structured diagnostics:

```python
from arxpy import ArxError, Compiler

try:
    Compiler().check(Compiler().parse_file("program.x"))
except ArxError as error:
    for item in error.diagnostics:
        print(item.code, item.filename, item.line, item.column, item.message)
```

In-memory native compilation requires an explicit output path. File compilation
defaults beside the source. No implicit persistent temporary directory is
created. Compiler calls are safe to repeat and are serialized across instances
because the current lexer reads a process-wide source buffer. Execution never
uses a shell; a non-zero program exit is returned in `ExecutionResult` rather
than raised. Command arguments must be supplied as a non-string sequence of
strings; scalar `str` and `bytes` values are rejected.

Use the [Arx CLI](../arx/compiler-cli.md) for compiler test discovery and other
CLI-specific workflows. The [roadmap](../roadmap.md) tracks the remaining API
stability work.
