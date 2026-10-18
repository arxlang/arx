# External Native Packages

Arx libraries can ship C ABI wrappers alongside their `.x` sources. The compiler
discovers them through normal project dependencies and links declared native
features from the reachable module graph. No Python plugins or shell build hooks
run during discovery. Source-only manifests are unchanged.

For example, an external rendering backend can receive numeric coordinates,
UTF-8 labels, and a filename and write JPEG itself. This adds no chart API or
JPEG codec to Arx and does not require binary Arx `File` support.

## Manifest and distribution

```toml
[project]
name = "demo-native"
version = "0.1.0"

[build]
package = "demo_native"
src_dir = "src"

[native]
version = 1

[native.features.backend]
libraries = ["m"]

[[native.features.backend.artifacts]]
kind = "c_source"
path = "native/shim.c"
include_dirs = ["native/include"]

[native.modules."demo_native.bridge"]
features = ["backend"]
```

This layout contains `.arxproject.toml`, `src/demo_native/__init__.x`,
`src/demo_native/bridge.x`, `native/shim.c`, and `native/include/`. Include all
resources in the wheel/sdist, preserving manifest-relative paths. Consumers
declare the distribution in `project.dependencies`, install it externally, then
import its modules normally. Local development uses the same contract.

Version 1 supports `c_source`, `cxx_source`, `object`, and `static_library`.
Source compilation requires the appropriate toolchain; objects/archives must
match the target ABI. Optional system library names become individual `-l`
arguments. The compiler never installs missing headers/libraries or downloads
dependencies. Arbitrary shell hooks and compiler flags are not accepted.

Absolute/traversing paths, escaping symlinks, missing inputs, unknown fields,
unsupported versions/features, and invalid library names are errors. Modules
must belong to the package's actual origin. Local shadow modules cannot inherit
installed native capabilities, and features cannot override builtins.

Mappings apply to actual top-level extern declarations, not ordinary functions
or callee spellings. C symbols must match the extern names; use unique prefixes.
Incompatible ABI/native requirements are rejected across modules. Reachable
extern declarations may activate features even if never called; this is not
call-site dead-code elimination. Unrelated installed packages add no inputs.

## C ABI and ownership

The first route uses existing scalar/string extern support. For example, an
external module might declare the following functions, implemented by its shim:

````arx
```
title: Example external native bridge
```
extern demo_create(size: i32) -> i64
extern demo_write(token: i64, filename: str) -> i32
extern demo_release(token: i64) -> i32
````

Use positive checked table tokens, with `0` indicating creation failure—not
pointers cast to integers. The external wrapper validates stale/forged tokens
and owns native allocations. A normal Arx class can keep a token in a private
scalar field and release it through `__del__`. Integer tokens themselves have no
static resource ownership or nominal type safety; class aliases retain their
ordinary shared identity and lexical cleanup.

Strings borrow NUL-terminated UTF-8 storage during the call. Copy retained text.
Embedded NUL is unsupported; known NUL-containing literal arguments are
rejected. Owned extern string returns still require an ownership ABI and remain
rejected. Return statuses and read output slots only after success. Translate
native exceptions/nonlocal jumps inside the wrapper, never across Arx frames.
Image dimensions, overflow, quality, and domain validation belong to the
external backend. No arbitrary fatal-error unwind is added.

`Compiler.check`, LLVM/object output, and executable compilation carry the same
capabilities in isolated registries. Object output may contain unresolved
externs; it is not a self-contained native distribution format. Direct pointer
APIs, callbacks, dynamic loading, and general foreign-object ownership are not
introduced by this metadata feature.

Native compilation is a trusted build operation, not a sandbox for malicious
dependencies. Compiler fixtures verify exact delivery of an existing JPEG and
arbitrary binary bytes; real rendering/encoding and image correctness must be
implemented and tested in the external library.
