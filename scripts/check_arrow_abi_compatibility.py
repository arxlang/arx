#!/usr/bin/env python3
"""
title: Check Arrow ABI manifests against stable compatibility baselines.
"""

from __future__ import annotations

import argparse
import sys

from collections.abc import Sequence
from pathlib import Path

from gen_arrow_abi import DEFAULT_MANIFEST, Handle, Manifest, load_manifest

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE_DIRECTORY = (
    ROOT
    / "packages"
    / "irx"
    / "src"
    / "irx"
    / "builder"
    / "runtime"
    / "arrow"
    / "abi_baselines"
)


def require_prefix(
    label: str,
    baseline: tuple[object, ...],
    current: tuple[object, ...],
) -> None:
    """
    title: Require an append-only sequence to preserve its stable prefix.
    parameters:
      label:
        type: str
      baseline:
        type: tuple[object, Ellipsis]
      current:
        type: tuple[object, Ellipsis]
    """
    if current[: len(baseline)] != baseline:
        raise ValueError(f"Arrow ABI {label} changed before its append point")


def handle_contract(handle: Handle) -> tuple[object, ...]:
    """
    title: Return the compatibility-relevant contract of one opaque handle.
    parameters:
      handle:
        type: Handle
    returns:
      type: tuple[object, Ellipsis]
    """
    return (
        handle.id,
        handle.name,
        handle.c_type,
        handle.ownership,
        handle.retain,
        handle.release,
    )


def check_runtime_features(
    baseline: Manifest,
    current: Manifest,
) -> None:
    """
    title: Check stable runtime-feature identities and contract versions.
    parameters:
      baseline:
        type: Manifest
      current:
        type: Manifest
    """
    baseline_features = baseline.runtime_features
    current_features = current.runtime_features
    baseline_identities = tuple(
        (feature.id, feature.name) for feature in baseline_features
    )
    current_identities = tuple(
        (feature.id, feature.name) for feature in current_features
    )
    require_prefix(
        "runtime feature identities",
        baseline_identities,
        current_identities,
    )

    for old_feature, new_feature in zip(
        baseline_features,
        current_features,
        strict=False,
    ):
        old_version = old_feature.contract_version
        new_version = new_feature.contract_version
        if new_version[0] != old_version[0] or new_version < old_version:
            raise ValueError(
                "Arrow runtime feature "
                f"'{old_feature.name}' has an incompatible contract version"
            )
        if (
            old_feature.availability == "implemented"
            and new_feature.availability != "implemented"
        ):
            raise ValueError(
                "implemented Arrow runtime feature "
                f"'{old_feature.name}' became unavailable"
            )


def check_handle_availability(
    baseline: Manifest,
    current: Manifest,
) -> None:
    """
    title: Reject regressions of implemented opaque-handle families.
    parameters:
      baseline:
        type: Manifest
      current:
        type: Manifest
    """
    for old_handle, new_handle in zip(
        baseline.handles,
        current.handles,
        strict=False,
    ):
        if (
            old_handle.availability == "implemented"
            and new_handle.availability != "implemented"
        ):
            raise ValueError(
                "implemented Arrow handle "
                f"'{old_handle.name}' became unavailable"
            )


def check_manifest_compatibility(
    baseline: Manifest,
    current: Manifest,
) -> None:
    """
    title: Check one current manifest against an older same-major consumer.
    parameters:
      baseline:
        type: Manifest
      current:
        type: Manifest
    """
    if current.version[0] != baseline.version[0]:
        raise ValueError("Arrow ABI compatibility requires the same major")
    if current.version[1] < baseline.version[1]:
        raise ValueError(
            "Arrow ABI runtime version is older than its consumer baseline"
        )

    require_prefix(
        "status codes",
        baseline.status_codes,
        current.status_codes,
    )
    require_prefix(
        "status categories",
        baseline.status_categories,
        current.status_categories,
    )
    require_prefix(
        "ownership kinds",
        baseline.ownership_kinds,
        current.ownership_kinds,
    )
    require_prefix("type IDs", baseline.type_ids, current.type_ids)
    require_prefix(
        "handle contracts",
        tuple(handle_contract(handle) for handle in baseline.handles),
        tuple(handle_contract(handle) for handle in current.handles),
    )
    check_handle_availability(baseline, current)
    require_prefix(
        "function declarations",
        tuple(baseline.functions),
        tuple(current.functions),
    )
    check_runtime_features(baseline, current)


def baseline_paths(arguments: argparse.Namespace) -> tuple[Path, ...]:
    """
    title: Resolve explicit or default ABI baseline paths.
    parameters:
      arguments:
        type: argparse.Namespace
    returns:
      type: tuple[Path, Ellipsis]
    """
    explicit = arguments.baseline
    if explicit:
        return tuple(explicit)
    return tuple(sorted(DEFAULT_BASELINE_DIRECTORY.glob("*.json")))


def main(argv: Sequence[str] | None = None) -> int:
    """
    title: Validate the current ABI against every same-major baseline.
    parameters:
      argv:
        type: Sequence[str] | None
    returns:
      type: int
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--baseline", type=Path, action="append")
    arguments = parser.parse_args(argv)

    try:
        current = load_manifest(arguments.manifest)
        baselines = tuple(
            load_manifest(path) for path in baseline_paths(arguments)
        )
        same_major = tuple(
            baseline
            for baseline in baselines
            if baseline.version[0] == current.version[0]
        )
        if not same_major:
            raise ValueError(
                f"Arrow ABI major {current.version[0]} has no baseline"
            )
        for baseline in same_major:
            check_manifest_compatibility(baseline, current)
    except (OSError, ValueError) as error:
        print(f"Arrow ABI compatibility error: {error}", file=sys.stderr)
        return 1

    print(
        f"Arrow ABI {current.version} satisfies {len(same_major)} baseline(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
