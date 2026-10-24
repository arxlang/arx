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
summary: Uses assertions in compiled tests.
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

Use `arx test --help` for discovery and execution options, including selection,
exclusion, and artifact retention.

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

## Arrow and Parquet CI coverage

CI collects the complete package suites and compiled-language tests on Python
3.10–3.14. Native prerequisites are checked explicitly in Arx/IRx jobs so
missing compilers or expected codecs cannot silently omit those integration
paths. Installed-wheel smoke tests run in clean environments on Python 3.10 and
3.14, including the nullable Series native header and compiled kernel calls.

A separate Linux job runs `makim irx.test-sanitizers`: registered Arrow and
Parquet runtime artifacts are compiled with AddressSanitizer and UBSan. Its
standalone harness exercises ownership/release, nullable scalar and Series
outputs, invalid indices, overflow, and durable atomic Parquet round trips. Leak
detection is enabled in CI. Third-party Arrow libraries are not rebuilt with
instrumentation. Restricted local environments may run
`python scripts/test_native_sanitizers.py --no-leaks`; that is **not** evidence
of a passing leak check.

Live cloud-provider compatibility requires provisioned services and credentials
and is not covered by these jobs. Local URI and unsupported transaction/error
paths remain in the regular suites. No finite test suite proves every possible
input or external-provider behavior.
