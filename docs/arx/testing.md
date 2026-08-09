# Compiled Tests

`arx test` discovers Arx test functions, compiles each selected test into an
executable, and runs it in a separate subprocess.

## Test files and functions

The default discovery rules are:

- search the `tests` directory
- include files matching `test_*.x`
- include functions matching `test_*`
- require zero parameters and a `none` return type

Test entry files must not define `main`, and executable module-level statements
are not supported in test entry files.

````arx
```
title: Math tests
summary: Uses fatal assertions in compiled tests.
```

import math from stdlib

fn test_square() -> none:
  assert math.square(3) == 9

fn test_clamp() -> none:
  assert math.clamp(0 - 3, 0, 2) == 0, "lower bound"
````

## Run tests

```bash
arx test
arx test tests/test_math.x --list
arx test -k square
arx test -x
arx test --keep-artifacts
```

| Option                    | Purpose                                    |
| ------------------------- | ------------------------------------------ |
| `--list`                  | list discovered tests without running them |
| `-k TEXT`                 | select tests containing `TEXT`             |
| `-x`, `--fail-fast`       | stop after the first failing test          |
| `--exclude GLOB`          | exclude matching paths; may be repeated    |
| `--file-pattern GLOB`     | override the test file pattern             |
| `--function-pattern GLOB` | override the function name pattern         |
| `--keep-artifacts`        | retain generated wrappers and executables  |
| `--link-mode MODE`        | use `auto`, `pie`, or `no-pie` linking     |

## Project configuration

Configure default discovery in `.arxproject.toml`:

```toml
[tests]
paths = ["tests", "integration"]
exclude = ["tests/experimental_*.x"]
file_pattern = "test_*.x"
function_pattern = "test_*"
```

CLI flags take precedence over project settings.

## Execution model

For each selected test, the runner builds a synthetic module with a `main`
function that calls exactly that test. IRx builds and links the executable.
Assertion failures are returned through IRx's machine-readable assertion
protocol and converted into test results.

Use `--keep-artifacts` when inspecting generated wrappers or compiler output for
a failing test.
