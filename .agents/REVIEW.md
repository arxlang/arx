## Review Summary

The PR is architecturally in the right area: import discovery belongs in Arx’s
frontend/resolver layer, and the precedence model of local project source before
installed dependencies is sensible. The tests cover the main happy path,
transitive dependencies, local shadowing, Python-only dependencies, missing
distributions, ambiguous module paths, and reserved namespaces.

I found two important issues that should be addressed before merging.

## Findings

### 1. [Important] Transitive dependency discovery ignores PEP 508 markers/extras

**Location:** `packages/arx/src/arx/package_index.py`,
`extract_dependency_name()` and
`discover_installed_arx_packages_from_dependencies()`

**Issue:** The PR extracts dependency names with a regex and then follows every
`distribution.requires` entry as though it is active. That loses environment
markers and extras such as:

```text
Requires-Dist: arx-extra-lib; extra == "dev"
Requires-Dist: arx-win-lib; sys_platform == "win32"
```

As written, those would be added to the pending dependency queue even when the
current project did not request that extra or the marker does not match the
current environment. The new index code performs regex extraction and
unconditional traversal of `distribution.requires` in `package_index.py`.

**Why it matters:** Optional or platform-specific Arx libraries can become
importable even though they are not real active dependencies of the project.
Conversely, inactive optional dependencies can produce misleading “declared
dependency is not installed” errors if the user imports a matching module name.

**Suggested fix:** Use `packaging.requirements.Requirement` instead of regex
parsing for installed distribution requirements. Evaluate `requirement.marker`
before enqueuing the requirement. For extras, either only enable extras
explicitly requested by the top-level dependency model, or skip `extra == ...`
requirements until Arx supports dependency extras in `.arxproject.toml`.

Add regression tests for:

```text
Requires-Dist: arx-optional-lib; extra == "dev"
Requires-Dist: arx-platform-lib; sys_platform == "never-matches"
```

and assert those packages are not indexed unless they are truly active.

### 2. [Important] Installed package discovery appears to ignore `[build].src_dir`

**Location:** `packages/arx/src/arx/package_index.py`,
`_arx_packages_from_distribution()` and `_module_name_from_manifest()`

**Issue:** The installed package index treats the directory containing
`.arxproject.toml` as the Arx source root. It then resolves `local_lib.stats`
relative to that directory. However, Arx project layout already defines source
roots through the default `src/` directory or `[build].src_dir`, and
`arx.settings.resolve_source_root()` exists specifically for that resolution.
The docs describe package modules as files under the effective source root, not
necessarily beside the manifest. The settings module also models `Build.src_dir`
and resolves source roots from it.

**Why it matters:** A normally packaged Arx project shaped like this may be
installed but fail to resolve:

```text
.arxproject.toml
src/
  local_lib/
    __init__.x
    stats.x
```

With `package = "local_lib"` and `src_dir = "src"`, the resolver should find
`src/local_lib/stats.x`; the current implementation appears to look under the
manifest parent instead.

**Suggested fix:** Load the packaged manifest through the existing settings
machinery when possible, or at least honor `[build].src_dir`. The indexed
`source_root` should likely be the package root itself, for example:

```text
manifest_parent / src_dir / package
```

when `[build].package` is set, or another explicitly documented convention if
the intent is different.

Add a regression test where the installed distribution contains
`.arxproject.toml` at project root and Arx sources under `src/<package>/`.

## Suggested Follow-ups

The docs should clarify exactly where `.arxproject.toml` is expected to live
inside an installed wheel and how `[build].package` and `[build].src_dir`
interact for installed library discovery. Right now the tests imply one layout,
while the existing module-layout docs emphasize source-root based layout.

## What Looks Good

The resolver integration keeps local project files ahead of installed libraries,
which matches the documented precedence. The reserved `stdlib` and `builtins`
namespace handling is also preserved. The tests added in `test_app_paths.py`
cover several important import-resolution edge cases, especially local shadowing
and ambiguous installed module/package paths.

## Verification Notes

I inspected the PR metadata, changed files, resolver changes, new package index,
docs, and tests through the GitHub connector. I did not run the test suite
locally. Recommended checks:

```bash
pytest packages/arx/tests/python/test_app_paths.py
ruff check packages/arx/src/arx/package_index.py packages/arx/src/arx/main.py
mypy packages/arx/src/arx
```
