# Support and Toolchain Matrix

## Status labels

Arx is still pre-production. This page distinguishes what the repository
currently verifies from the target that may become supported at GA:

- **CI-verified** means a checked-in workflow runs on every pull request.
- **Release candidate** means the combination is intended for the first stable
  release but has not completed an RC soak.
- **Experimental** means it may work but is not a compatibility commitment.
- **Unsupported** means the project does not currently provide artifacts or a
  passing gate for the combination.

## Current matrix

| Dimension            | CI-verified now                                                                   | Release candidate                                                       | Experimental / unsupported                                   |
| -------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------ |
| Operating system     | Ubuntu GitHub-hosted runner                                                       | A named Ubuntu LTS release, to be frozen before RC                      | macOS and Windows are experimental                           |
| Architecture         | GitHub-hosted x86-64                                                              | x86-64                                                                  | AArch64 and other architectures are experimental             |
| Python               | CPython 3.10, 3.11, 3.12, 3.13, and 3.14 package/language jobs                    | The same versions that pass the RC wheel gate                           | PyPy and CPython outside this range are unsupported          |
| Native compiler      | Conda-forge Clang/Clangdev 14 in `conda/dev.yaml`                                 | Clang 14 until a newer range is explicitly qualified                    | GCC/MSVC and other Clang versions are experimental           |
| LLVM code generation | The LLVM bundled by the resolved `llvmlite` package                               | Exact `llvmlite`/LLVM combinations from the RC lock and wheels          | System LLVM replacement is unsupported                       |
| Linker               | Toolchain-default linker, plus explicit PIE/non-PIE modes in tests                | The linker shipped with the selected Ubuntu/Clang environment           | Other linkers are experimental                               |
| C/C++ runtime        | The glibc/libstdc++ environment of the Ubuntu runner                              | Versions shipped by the selected Ubuntu LTS                             | musl and alternative C++ runtimes are experimental           |
| Arrow                | PyArrow 24.x and `arx-arrowcpp-sources` 24.0.0 from package metadata              | The exact lockstep dependency range that passes RC                      | Other Arrow major versions are unsupported                   |
| Package artifact     | Pure-Python-tagged wheels plus on-demand native compilation from packaged sources | Fresh isolated wheel install and native smoke on every supported target | Precompiled platform-native wheels are not currently shipped |

“Pure-Python-tagged” describes the wheel container, not the runtime
requirements. IRx compiles native C/C++ runtime features on demand and therefore
requires a compatible compiler/linker for those features.

## Wheel gate

The `wheel-smoke` CI job builds all six lockstep packages once, installs those
wheels together in a fresh virtual environment, and checks:

- lockstep versions, `Requires-Python`, typing markers, and identical Apache-2.0
  license files in wheels and source distributions;
- packaged C/C++ sources and headers needed for IRx runtime compilation;
- imports from wheel contents rather than the repository source tree;
- scalar and multi-module compile/run through ArxPy;
- class, dynamic-list, and fixed-shape tensor compile/run;
- first-use RecordBatch native-cache construction and PyArrow IPC
  interoperability.

Each run uses a tool-owned temporary directory below `.tmp/wheel-smoke/` and
removes only that generated directory when the run finishes.

Run the release-equivalent gate with:

```bash
makim all.wheel-smoke
```

For an offline developer audit that deliberately reuses already-installed
third-party dependencies (not acceptable as release evidence):

```bash
./scripts/build.sh
python scripts/test_wheels.py --current-environment
```

## Requirements before a stable support claim

Before any row becomes supported rather than a release candidate, it needs:

1. an exact OS image and architecture rather than a moving `*-latest` label;
2. clean wheel compile/run and native sanitizer jobs for every matrix cell;
3. documented minimum compiler, linker, glibc, and C++ runtime versions;
4. installation and failure tests without a repository checkout;
5. an RC soak plus upgrade and rollback rehearsal;
6. a stated support lifetime in [SUPPORT.md](../SUPPORT.md).

Passing on an unlisted platform is useful feedback but is not evidence of
project support.
