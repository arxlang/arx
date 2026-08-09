# IRx

IRx is the semantic-analysis, LLVM-lowering, and native-runtime layer of the
ArxLang ecosystem. The PyPI distribution is `pyirx`; the Python import is `irx`.

> Status: functional experimental backend. It supports substantial compiler and
> runtime flows but does not lower every ASTx node.

## Responsibilities

- analyze ASTx modules and attach resolved semantic sidecars
- validate types, calls, imports, templates, classes, and FFI boundaries
- lower supported nodes to LLVM IR with `llvmlite`
- emit objects, link executables with Clang, and run built artifacts
- report structured semantic, lowering, native-compile, and link diagnostics
- activate native runtime features only when a compilation unit needs them

## Native Apache Arrow runtime

IRx integrates Apache Arrow through native C++ runtime code and opaque C ABI
handles. Current layers include:

- primitive Arrow arrays and Arrow C Data interoperability
- homogeneous fixed-width `arrow::Tensor` values
- DataFrames backed by `arrow::Table`
- Series backed by `arrow::ChunkedArray`
- RecordBatch schemas, builders, nullable data, and Arrow IPC streams

The RecordBatch API interoperates with PyArrow and supports signed/unsigned
integers, floats, booleans, UTF-8 and large UTF-8 strings, dates, timestamps,
and times. `pyarrow` and `arx-arrowcpp-sources` provide the Arrow C++ build and
link metadata.

## Install

```bash
pip install pyirx
```

Native builds require an LLVM/Clang-compatible toolchain. Arrow runtime features
require a C++ compiler.

## Translate ASTx to LLVM IR

```python
import astx

from irx.builder import Builder

builder = Builder()
module = builder.module()

body = astx.Block()
body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
prototype = astx.FunctionPrototype(
    name="main",
    args=astx.Arguments(),
    return_type=astx.Int32(),
)
module.block.append(astx.FunctionDef(prototype=prototype, body=body))

llvm_ir = builder.translate(module)
print(llvm_ir)
```

`translate()` returns LLVM IR text without linking. Use `build()` to emit and
link a native artifact, then `run()` to execute the built program.

## RecordBatch API

The direct Python API lives in `irx.record_batch`. In a source checkout, build
its standalone shared library before first use:

```bash
python -c "from irx.builder.runtime.record_batch import build_record_batch_shared_library; build_record_batch_shared_library()"
```

```python
from irx.record_batch import (
    IrxColumnType,
    RecordBatchBuilder,
    RecordBatchSchema,
)

schema = RecordBatchSchema()
schema.add_field("id", IrxColumnType.INT32, nullable=False)

builder = RecordBatchBuilder(schema)
builder.append_int32(0, 42)
batch = builder.finish()

assert batch.get_int32(0, 0) == 42

batch.release()
builder.release()
schema.release()
```

## Runtime features

Registered features include `libc`, `libm`, `assertions`, `buffer`, `list`,
`array`, `tensor`, `dataframe`, and `record_batch`. Features may contribute
external symbols, C/C++ sources, object files, libraries, and linker flags.

## Boundaries

IRx does not parse Arx/AIX source and does not define high-level query or
DataFrame language semantics. Arrow C++ stays behind the native runtime; LLVM
does not encode Arrow object layouts directly.

Documentation: <https://arxlang.org/irx/>

License: Apache-2.0.
