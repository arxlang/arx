# Arx

Arx is a new programming language that uses the power of LLVM to provide
multi-architecture machine target code generation. Arx aims to provide native
list and ndarray abstractions with a builtin runtime backed internally by IRx.

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

Arx now exposes `list[...]` and `ndarray[...]` as distinct public collection
forms:

```arx
fn pick(grid: ndarray[i32, 2, 2]) -> i32:
  return grid[1, 0]

fn main() -> i32:
  var grid: ndarray[i32, 2, 2] = [[1, 2], [3, 4]]
  var ids: list[i32] = [5, 6, 7, 8]
  return pick(grid) + ids[2]
```

Use:

- `list[T]` for generic collection values
- `ndarray[T]` for dynamic Arrow-backed numeric arrays
- `ndarray[T, N]` and `ndarray[T, D1, D2, ...]` for fixed-shape numeric arrays

NDArray details stay user-facing in terms of element types, shape, dimensions,
and indexing. IRx buffer-view lowering remains an internal backend detail.

Arx also ships a bundled pure-Arx standard library under the reserved `stdlib`
namespace:

```arx
import math from stdlib

fn main() -> i32:
  return math.square(4)
```

Compiler-provided builtins stay separate from stdlib. Builtin sources live in
`src/arx/builtins/*.x`, are bundled inside the installed `arx` package, and are
resolved by dedicated compiler logic instead of user-project module lookup.
Those bundled builtin modules are internal compiler assets, not a public
stdlib-style import namespace.

```arx
fn main() -> i32:
  return range(4)
```

The first builtin module is `generators`. Its current MVP exposes `range(stop)`,
while future overloads and `yield`-backed generator semantics will grow in the
same area.

Arx now supports fatal assertion statements in the language surface:

```arx
fn test_add() -> none:
  assert 1 + 1 == 2
  assert 2 + 2 == 4, "2 + 2 should be 4"
```

You can run compiled tests with the new `arx test` subcommand:

```bash
arx test
arx test tests/arx/test_math.x --list
arx test -k square
arx test -x
arx test --keep-artifacts
arx test --exclude "tests/arx/slow_*.x"
```

By default the runner searches `tests/` for files matching `test_*.x`, discovers
zero-argument `test_*` functions that return `none`, and executes each test in
its own compiled subprocess. Test identifiers use the cwd-relative path of the
source file (without the `.x` suffix) joined to the function name via `::`, for
example `tests/arx/test_math::test_square`, so same-named files in parallel
directories stay distinct.

You can override discovery from `.arxproject.toml`:

```toml
[tests]
paths = ["tests", "integration"]
exclude = ["tests/experimental_*.x"]
file_pattern = "test_*.x"
function_pattern = "test_*"
```

CLI flags always win over `[tests]` settings. In v1, shared top-level support is
intentionally narrow: imports, extern declarations, class declarations, and
helper functions are preserved, while module-scope variable declarations and
other top-level executable code are not supported yet.
