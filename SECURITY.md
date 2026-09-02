# Security Policy

## Current support status

Arx is pre-production software. No release line currently carries a stable
language, native ABI, or long-term security-support guarantee. Security fixes
are applied to the latest development line and included in the next available
release. This policy will be versioned with explicit support windows before the
first production release.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Email
`arxcompiler@gmail.com` with the subject `Arx security report` and include:

- the affected package and version or Git commit;
- the operating system, architecture, Python version, and native toolchain;
- a minimal reproduction or proof of concept;
- the expected and observed impact;
- whether the issue is already public or has a disclosure deadline;
- a safe way to contact you for follow-up.

Avoid including secrets, personal data, or production datasets. Use a minimal
synthetic reproduction where possible.

The project will acknowledge a report within seven calendar days. Initial triage
aims to establish reproducibility, affected versions, severity, and a disclosure
plan. These are response targets rather than a contractual service level while
the project remains community-maintained.

## Coordinated disclosure

Reporters and maintainers should agree on a disclosure date based on impact and
fix availability. The project will credit reporters who request credit and will
keep identities private when requested. A release addressing a vulnerability
should include an advisory, affected/fixed versions, mitigations, and upgrade
instructions without publishing exploit details before the agreed date.

## Scope

Security-relevant areas include:

- compiler crashes or memory corruption caused by untrusted source;
- unsafe generated native code or runtime ownership failures;
- package/import path traversal or dependency substitution;
- arbitrary command execution outside documented compilation/linking behavior;
- malformed Arrow C Data Interface or FFI inputs causing memory unsafety;
- release, artifact-integrity, or CI credential compromise.

Ordinary unsupported syntax, documented pre-production API changes, and
performance bugs without a denial-of-service impact are normally handled as
public bug reports.

## Release requirements

Before Arx makes a production-readiness claim, release artifacts must have a
documented vulnerability triage owner, immutable build inputs, dependency
auditing, an SBOM, signed provenance/integrity data, and a tested process for
shipping coordinated security fixes.
