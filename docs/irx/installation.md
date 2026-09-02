# Installing IRx

## Published package

```bash
pip install pyirx
```

The distribution is named `pyirx`; Python code imports `irx`.

IRx requires Python 3.10 or newer. Translation uses `llvmlite`. Native object
and executable workflows require an LLVM/Clang-compatible toolchain, while
Arrow-backed features additionally require a C++ compiler.

PyArrow and `arx-arrowcpp-sources` are installed dependencies. IRx uses their
Arrow C++ include, source, library, and linker metadata for native runtime
builds.

## Source checkout

```bash
git clone https://github.com/arxlang/arx.git
cd arx
mamba env create --file conda/dev.yaml
conda activate arx
poetry install
makim irx.unittests
```

## Direct RecordBatch Python API

The direct `irx.record_batch` ctypes API loads a standalone shared library. On
first use it builds the library from packaged native sources; later uses verify
the source/toolchain fingerprint and rebuild stale cache entries automatically.
To pre-warm the cache explicitly:

```bash
python -c "from irx.builder.runtime.record_batch import ensure_record_batch_shared_library; ensure_record_batch_shared_library()"
```

The generated library, objects, and source/toolchain fingerprint are stored
under `${XDG_CACHE_HOME:-~/.cache}/arxlang/irx/record_batch/abi-1` by default.
Set `IRX_NATIVE_CACHE_DIR` to move the native cache or
`IRX_RECORD_BATCH_LIBRARY` to use an exact library path. The loader rejects ABI
mismatches and asks for a rebuild before configuring ctypes symbols.

IRx programs compiled through the Builder use runtime-feature artifact
collection instead of this standalone ctypes setup.

## Link modes

IRx emits PIC-compatible objects by default for modern PIE-default linkers. If a
downstream manual link still requires non-PIE output, pass the equivalent of
`clang -no-pie` or use Arx's `--link-mode no-pie` option.
