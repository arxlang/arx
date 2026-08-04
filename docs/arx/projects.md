# Arx Projects and Imports

The Arx compiler can read project metadata from `.arxproject.toml`. The compiler
uses this metadata for source layout, import resolution, output defaults, and
test discovery. [ArxPM](../tools/arxpm.md) provides higher-level project and
environment workflows.

## Project layout

A conventional source tree is:

```text
.
├── .arxproject.toml
├── src
│   └── geometry
│       ├── __init__.x
│       ├── shared
│       │   └── math.x
│       └── shapes
│           ├── area.x
│           └── helpers.x
└── tests
    └── test_area.x
```

## Manifest

```toml
[project]
name = "geometry"
version = "0.1.0"
requires-arx = ">=1.0,<2"
dependencies = [
  "sciarx>=0.0.3,<1",
]

[environment]
kind = "conda"
name = "geometry"

[build-system]
dependencies = [
  "arxlang>=1.0,<2",
]

[build]
src_dir = "src"
out_dir = "build"
package = "geometry"
```

`requires-arx` uses standard version-specifier syntax. Project dependencies use
standard requirement strings and may also be direct references.

The compiler validates the manifest but does not install dependencies during
import resolution. Use ArxPM or another environment tool to provision them.

## Imports

```arx
import geometry.shapes.area
import geometry.shapes.area as area
import circle_area from geometry.shapes.area
import circle_area as area_of_circle from geometry.shapes.area
import (circle_area, square_area) from geometry.shapes.area
import helper from .helpers
import clamp from ..shared.math
```

Relative imports require the `from` form. Plain `import .area` is not supported.

The resolver checks local project modules before installed Arx packages. The
compiler reserves:

- `stdlib` for bundled pure-Arx modules
- `builtins` for compiler-injected source modules

```arx
import math from stdlib

fn main() -> i32:
  return math.square(4)
```

## Build settings

The `[build]` table can select:

- `src_dir`: source root
- `package`: default package/module root
- `out_dir`: build output directory
- `mode`: project build mode when supported by the invoking tool

The `arx` command compiles an entry file and resolves its imported module graph.
ArxPM owns workspace-level commands such as project initialization, dependency
installation, build, run, packaging, and publishing.

## Test settings

The optional `[tests]` table controls compiled test discovery:

```toml
[tests]
paths = ["tests", "integration"]
exclude = ["tests/experimental_*.x"]
file_pattern = "test_*.x"
function_pattern = "test_*"
```

See [Compiled Tests](testing.md) for the test function contract and CLI flags.
