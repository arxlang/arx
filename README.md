# Arx

Arx is a new programming language that uses the power of LLVM to provide a
multi-architecture machine target code generation. Arx aims to provide a direct
interface to Apache Arrow.

Arx is a prototype that should replace the current Arx compiler in c++.

- Free software: Apache Software License 2.0
- Documentation: https://arxlang.org

If you want more information about ArxLang, please check the original project in
c++: https://github.com/arxlang/arx

## Link Modes

Arx supports explicit executable link modes:

```bash
arx program.x --link-mode auto    # default, use toolchain default
arx program.x --link-mode pie     # force PIE executable
arx program.x --link-mode no-pie  # force non-PIE executable
```

## Troubleshooting (PIE / Colab / Conda)

If you hit an error like:

```text
relocation R_X86_64_32 ... can not be used when making a PIE object
```

use:

```bash
arx program.x --link-mode no-pie
```

This typically happens on environments where the linker defaults to PIE while
objects were not compiled in a PIE-compatible mode.
