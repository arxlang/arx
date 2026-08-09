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

The direct `irx.record_batch` ctypes API currently loads a standalone shared
library. Build it from the checkout before first use:

```bash
python -c "from irx.builder.runtime.record_batch import build_record_batch_shared_library; build_record_batch_shared_library()"
```

IRx programs compiled through the Builder use runtime-feature artifact
collection instead of this standalone ctypes setup.

## Link modes

IRx emits PIC-compatible objects by default for modern PIE-default linkers. If a
downstream manual link still requires non-PIE output, pass the equivalent of
`clang -no-pie` or use Arx's `--link-mode no-pie` option.
