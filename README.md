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

## Testing

Arx now supports fatal assertion statements in the language surface:

```arx
fn test_add() -> none:
  assert 1 + 1 == 2
  assert 2 + 2 == 4, "2 + 2 should be 4"
  return none
```

You can run compiled tests with the new `arx test` subcommand:

```bash
arx test
arx test tests/main.x --list
arx test -k fibonacci
arx test -x
arx test --keep-artifacts
```

By default the runner looks for `tests/main.x`, discovers zero-argument `test_*`
functions that return `none`, and executes each test in its own compiled
subprocess.
