# ArxPy

ArxPy is the typed Python-facing API for the Arx compiler.

> Status: pre-stable compiler facade. Parse, semantic check, host compilation,
> captured execution, structured diagnostics, and typed artifacts are available.
> Cancellation, cross-target compilation, query/LSP APIs, and API compatibility
> guarantees are not complete.

## Install

```bash
pip install arxpy
```

## Current API

```python
from arxpy import (
    ArtifactKind,
    ArxError,
    Compiler,
    CompileError,
    Diagnostic,
    DiagnosticSeverity,
    ExecutionError,
    ParseError,
)
```

`Diagnostic` is an immutable external record with severity, message, filename,
line, column, and optional code. ArxPy adapters translate IRx structured
diagnostics and Arx parser exceptions without exposing raw compiler nodes.

All expected public failures inherit from `ArxError` and carry a `diagnostics`
list. Unexpected internal compiler exceptions are not relabeled as user input
errors.

```python
from pathlib import Path

from arxpy import ArtifactKind, Compiler

compiler = Compiler()
parsed = compiler.parse_file("program.x")
checked = compiler.check(parsed)

ir = compiler.compile(checked, kind=ArtifactKind.LLVM_IR)
assert ir.llvm_ir is not None

binary = compiler.compile(
    checked,
    kind=ArtifactKind.EXECUTABLE,
    output=Path("build/program"),
)
result = compiler.run(binary, timeout=10)
print(result.exit_code, result.stdout, result.stderr)
```

Native output from in-memory source requires an explicit output path. File
compilation defaults beside the source (`.o` for objects and no suffix for an
executable). The API creates no implicit persistent temporary directory.
Compiler operations are serialized across instances while the Arx frontend uses
its process-wide input buffer; repeated calls use fresh lowering builders. `run`
never invokes a shell, and a program's non-zero exit status is returned as data.
Public annotations are enforced at runtime, including every collection item. The
`args` input must be a non-string sequence of strings; scalar `str` and `bytes`
values are rejected rather than expanded character by character.

Use the `arx` CLI for test discovery and CLI-oriented workflows that the facade
does not yet model.

Documentation: <https://arxlang.org/arxpy/>

License: Apache-2.0.
