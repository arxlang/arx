# PyArx

PyArx is the planned stable Python API for parsing, compiling, and running Arx
programs without invoking the CLI.

## Current status

PyArx is currently an API foundation, not an end-to-end compiler facade.

Implemented:

- `Diagnostic` and `DiagnosticSeverity`
- conversion helpers for IRx diagnostics and Arx parser failures
- `ArxError` as the public base exception
- `ParseError`, `CompileError`, and `ExecutionError`
- lightweight imports that do not initialize LLVM at module import time

Not implemented:

- parse-from-string or parse-from-file entry points
- compiler/session configuration objects
- native artifact and execution result APIs
- an end-to-end exception translation boundary

## Install

```bash
pip install pyarx
```

## Current usage

```python
from pyarx import ArxError, Diagnostic, DiagnosticSeverity

diagnostic = Diagnostic(
    severity=DiagnosticSeverity.ERROR,
    message="example failure",
    filename="example.x",
    line=3,
    column=2,
    code="S001",
)

try:
    raise ArxError("compilation failed", diagnostics=[diagnostic])
except ArxError as error:
    for item in error.diagnostics:
        print(item.message)
```

Use the [Arx CLI](../getting-started.md) for current end-to-end compilation. The
[roadmap](../roadmap.md) lists the compiler facade planned for PyArx.
