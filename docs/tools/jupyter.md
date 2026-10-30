# ArxLang Jupyter Kernel

[arxlang-jupyter-kernel](https://github.com/arxlang/arxlang-jupyter-kernel) is a
wrapper-style Jupyter kernel for Arx. It invokes the `arx` executable rather
than embedding the compiler.

> **Status:** The repository provides the kernel process, installer, session
> handling, and subprocess diagnostics. Its compiler command construction still
> needs to stay aligned with the current Arx CLI before it can be treated as a
> stable notebook interface.

## Execution model

- Each cell is combined with a session prelude containing previous successful
  cells.
- The resulting source is written to a temporary build directory.
- The kernel invokes the Arx compiler and then runs the produced executable.
- Standard output and error are returned to Jupyter.
- A failed compilation does not update the session prelude.

The wrapper does not currently provide incremental compilation or an in-process
JIT session.

## Install from a source checkout

```bash
git clone https://github.com/arxlang/arxlang-jupyter-kernel.git
cd arxlang-jupyter-kernel
poetry install
poetry run python -m arxlang_jupyter_kernel.install --user
jupyter kernelspec list
```

The `arx` executable must be available on `PATH`, or `ARX_BIN` must point to it.

## Documentation notebooks

DoukiMD renders saved `.ipynb` cells and outputs without starting a kernel. Run
notebooks in Jupyter with the registered Arx kernel and save the results before
building the documentation. Interactive widgets are not executed.

## Configuration

| Variable                  | Purpose                                     |
| ------------------------- | ------------------------------------------- |
| `ARX_BIN`                 | compiler executable; defaults to `arx`      |
| `ARX_COMPILE_ARGS`        | additional compiler arguments               |
| `ARX_RUN_ARGS`            | additional executable arguments             |
| `ARX_KERNEL_KEEP_BUILD`   | retain temporary build directories when set |
| `ARX_KERNEL_SESSION_FILE` | optional persistent session source file     |

Source and current limitations:
[github.com/arxlang/arxlang-jupyter-kernel](https://github.com/arxlang/arxlang-jupyter-kernel)
