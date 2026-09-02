# Support Policy

## Current releases

Arx is pre-production. Only the latest released package set and the current
development branch receive routine fixes. Older releases may be useful for
reproduction but are not maintained as security or compatibility branches.

All six packages use lockstep release versions. Mixing package versions is not a
supported configuration unless a package manifest explicitly permits it.

## Supported environment

The packages declare Python 3.10 through 3.14. The current CI configuration
tests those Python versions on Ubuntu. macOS, Windows, non-x86 architectures,
and alternate Clang/LLVM combinations are experimental until they are added to
the required CI and clean-install matrix.

Native compilation additionally requires a compatible C/C++ toolchain and the
libraries documented by IRx. A build that happens to work outside the tested
matrix is welcome evidence, but it is not a support guarantee.

## Getting help

- Use a GitHub issue for reproducible compiler, documentation, installation, or
  compatibility bugs.
- Use a GitHub discussion or the community chat for design and usage questions.
- Follow `SECURITY.md` for vulnerabilities; do not report them publicly.
- Follow `CODE_OF_CONDUCT.md` for private conduct reports.

Include the exact Arx package versions or Git commit, Python version, operating
system and architecture, compiler/linker versions, command, minimal source, and
complete diagnostic output. Remove secrets and proprietary source.

## Production support target

Before the first production release, this file will name supported language and
ABI versions, operating systems, architectures, toolchain ranges, maintenance
periods, security-fix periods, and deprecation timelines. Those guarantees do
not apply retroactively to current pre-production releases.
