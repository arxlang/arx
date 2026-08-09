# ArxPy

ArxPy is the developing Python-facing API for the Arx compiler.

> Status: API foundation only. The package currently provides structured
> diagnostics and public exception types; it does not yet expose parse, compile,
> run, or artifact APIs.

## Install

```bash
pip install arxpy
```

## Current API

```python
from arxpy import (
    ArxError,
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

All public failures inherit from `ArxError` and carry a `diagnostics` list.

Until the compiler facade lands, use the `arx` CLI for end-to-end compilation or
the lower-level Arx/IRx APIs for internal integrations.

Documentation: <https://arxlang.org/arxpy/>

License: Apache-2.0.
