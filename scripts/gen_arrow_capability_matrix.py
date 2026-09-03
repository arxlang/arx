"""
title: Generate the Apache Arrow capability matrix.
summary: Validate and render the versioned Arrow capability manifest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, cast

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "docs" / "data" / "arrow-capabilities.json"
DEFAULT_OUTPUT = ROOT / "docs" / "arrow-capability-matrix.md"
IRX_PROJECT = ROOT / "packages" / "irx" / "pyproject.toml"
REPOSITORY_SOURCE_URL = "https://github.com/arxlang/arx/blob/main"
CAPABILITY_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FOUNDATION_ID_PATTERN = re.compile(r"^FND-\d{3}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
MILESTONE_PATTERN = re.compile(r"^M(?:[0-9]|10)$")
STAGE_NAMES = (
    "native_runtime",
    "astx_model",
    "irx_semantics",
    "llvm_lowering",
    "arx_surface",
    "interop",
)
STAGE_LABELS = {
    "native_runtime": "Native",
    "astx_model": "ASTx",
    "irx_semantics": "Semantics",
    "llvm_lowering": "Lowering",
    "arx_surface": "Arx",
    "interop": "Interop",
}
STATUS_LABELS = {
    "complete": "Complete",
    "partial": "Partial",
    "not_started": "Not started",
    "not_applicable": "N/A",
}
SCOPE_LABELS = {
    "core": "Core",
    "staged": "Staged",
    "optional": "Optional",
    "interop": "Interop",
    "preserve_only": "Preserve only",
    "out_of_scope": "Out of scope",
}
READINESS_STATUS_LABELS = {
    "not_started": "Not started",
    "in_progress": "In progress",
    "partial": "Partial",
    "blocked": "Blocked",
    "done": "Done",
    "deferred": "Deferred",
}
PLACEMENT_LABELS = {
    "compiler_builtin_type": "Compiler builtin type",
    "compiler_intrinsic": "Compiler intrinsic",
    "builtin_operator": "Builtin operator or method",
    "bundled_builtin_module": "Bundled builtin module",
    "stdlib_compute": "Standard library compute",
    "stdlib_io": "Standard library I/O",
    "stdlib_dataset": "Standard library dataset",
    "optional_module": "Optional standard-library module",
    "interop_only": "Interoperability API",
    "internal_runtime": "Internal runtime",
}
VISIBILITY_LABELS = {
    "public": "Public",
    "compiler_only": "Compiler only",
    "interop_api": "Interop API",
}
MODULE_CLASSIFICATION_LABELS = {
    "core_language": "Core language/runtime",
    "standard_library": "Standard library",
    "interoperability": "Interoperability only",
    "optional": "Optional feature",
    "preserve_only": "Preserve only",
    "internal": "Internal implementation",
    "out_of_scope": "Out of scope",
}


@dataclass(frozen=True)
class Evidence:
    """
    title: Test evidence attached to one capability.
    attributes:
      path:
        type: Path
      symbol:
        type: str
      purpose:
        type: str
    """

    path: Path
    symbol: str
    purpose: str


@dataclass(frozen=True)
class Capability:
    """
    title: Current support state for one Arrow capability.
    attributes:
      id:
        type: str
      category:
        type: str
      name:
        type: str
      scope:
        type: str
      target_milestone:
        type: str
      stages:
        type: dict[str, str]
      overall:
        type: str
      notes:
        type: str
      evidence:
        type: tuple[Evidence, Ellipsis]
    """

    id: str
    category: str
    name: str
    scope: str
    target_milestone: str
    stages: dict[str, str]
    overall: str
    notes: str
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class Foundation:
    """
    title: Tracked compiler foundation required by Arrow support.
    attributes:
      id:
        type: str
      name:
        type: str
      owner:
        type: str
      status:
        type: str
      test_targets:
        type: tuple[Path, Ellipsis]
      blocks:
        type: tuple[str, Ellipsis]
      baseline:
        type: str
      completion:
        type: str
    """

    id: str
    name: str
    owner: str
    status: str
    test_targets: tuple[Path, ...]
    blocks: tuple[str, ...]
    baseline: str
    completion: str


@dataclass(frozen=True)
class Distribution:
    """
    title: Accepted native Arrow artifact distribution contract.
    attributes:
      strategy:
        type: str
      core_package:
        type: str
      optional_packages:
        type: tuple[str, Ellipsis]
      pyarrow_role:
        type: str
      system_arrow_role:
        type: str
      source_build_role:
        type: str
      compiled_output_policy:
        type: str
      python_abi:
        type: str
    """

    strategy: str
    core_package: str
    optional_packages: tuple[str, ...]
    pyarrow_role: str
    system_arrow_role: str
    source_build_role: str
    compiled_output_policy: str
    python_abi: str


@dataclass(frozen=True)
class AbiContract:
    """
    title: Accepted unified Arrow C ABI compatibility contract.
    attributes:
      name:
        type: str
      major:
        type: int
      minor:
        type: int
      patch:
        type: int
      symbol_prefix:
        type: str
      legacy_prefixes:
        type: tuple[str, Ellipsis]
      compatibility:
        type: str
      version_query:
        type: str
      feature_query:
        type: str
    """

    name: str
    major: int
    minor: int
    patch: int
    symbol_prefix: str
    legacy_prefixes: tuple[str, ...]
    compatibility: str
    version_query: str
    feature_query: str


@dataclass(frozen=True)
class Operation:
    """
    title: Placement decision for one public operation family.
    attributes:
      id:
        type: str
      name:
        type: str
      surface:
        type: str
      placement:
        type: str
      module:
        type: str
      visibility:
        type: str
      target_milestone:
        type: str
      capabilities:
        type: tuple[str, Ellipsis]
      rationale:
        type: str
    """

    id: str
    name: str
    surface: str
    placement: str
    module: str
    visibility: str
    target_milestone: str
    capabilities: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class ArrowModule:
    """
    title: Scope classification for one upstream Arrow module group.
    attributes:
      id:
        type: str
      upstream:
        type: str
      classification:
        type: str
      public_module:
        type: str
      runtime_feature:
        type: str
      capabilities:
        type: tuple[str, Ellipsis]
      rationale:
        type: str
    """

    id: str
    upstream: str
    classification: str
    public_module: str
    runtime_feature: str
    capabilities: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class Manifest:
    """
    title: Validated Arrow capability manifest.
    attributes:
      schema_version:
        type: int
      arrow_cpp_version:
        type: str
      pyarrow_constraint:
        type: str
      arrow_sources_constraint:
        type: str
      distribution:
        type: Distribution
      abi:
        type: AbiContract
      foundations:
        type: tuple[Foundation, Ellipsis]
      capabilities:
        type: tuple[Capability, Ellipsis]
      operations:
        type: tuple[Operation, Ellipsis]
      modules:
        type: tuple[ArrowModule, Ellipsis]
    """

    schema_version: int
    arrow_cpp_version: str
    pyarrow_constraint: str
    arrow_sources_constraint: str
    distribution: Distribution
    abi: AbiContract
    foundations: tuple[Foundation, ...]
    capabilities: tuple[Capability, ...]
    operations: tuple[Operation, ...]
    modules: tuple[ArrowModule, ...]


class CapabilityMatrixError(Exception):
    """
    title: Raised when the Arrow capability manifest is invalid or stale.
    """


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """
    title: Parse command-line arguments.
    parameters:
      argv:
        type: Sequence[str] | None
    returns:
      type: argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description="Generate the versioned Apache Arrow capability matrix."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to the source capability manifest.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to the generated Markdown matrix.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the generated matrix is stale.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """
    title: Validate the manifest and write or check the generated matrix.
    parameters:
      argv:
        type: Sequence[str] | None
    returns:
      type: int
    """
    args = parse_args(argv)
    manifest_path = cast(Path, args.manifest).resolve()
    output_path = cast(Path, args.output).resolve()
    try:
        manifest = load_manifest(manifest_path)
        validate_dependency_pins(manifest)
        rendered = render_manifest(manifest, manifest_path)
        if cast(bool, args.check):
            check_output(output_path, rendered)
        else:
            write_output(output_path, rendered)
    except CapabilityMatrixError as exc:
        print(f"Arrow capability matrix error: {exc}", file=sys.stderr)
        return 1
    return 0


def load_manifest(path: Path) -> Manifest:
    """
    title: Load and validate an Arrow capability manifest.
    parameters:
      path:
        type: Path
    returns:
      type: Manifest
    """
    if not path.is_file():
        raise CapabilityMatrixError(f"manifest does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CapabilityMatrixError(
            f"cannot parse {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc

    root = require_mapping(value, "manifest")
    schema_version = require_int(root, "schema_version", "manifest")
    if schema_version != 1:
        raise CapabilityMatrixError(
            f"unsupported manifest schema version: {schema_version}"
        )

    arrow_version = require_string(root, "arrow_cpp_version", "manifest")
    if VERSION_PATTERN.fullmatch(arrow_version) is None:
        raise CapabilityMatrixError(
            f"invalid Arrow C++ version: {arrow_version!r}"
        )

    dependencies = require_mapping(
        root.get("dependency_constraints"), "dependency_constraints"
    )
    pyarrow_constraint = require_string(
        dependencies, "pyarrow", "dependency_constraints"
    )
    arrow_sources_constraint = require_string(
        dependencies,
        "arx_arrowcpp_sources",
        "dependency_constraints",
    )
    distribution = parse_distribution(root.get("distribution"))
    abi = parse_abi_contract(root.get("abi"))
    raw_foundations = require_list(
        root.get("foundations"), "manifest.foundations"
    )
    foundations = tuple(
        parse_foundation(item, index)
        for index, item in enumerate(raw_foundations)
    )
    if not foundations:
        raise CapabilityMatrixError("manifest.foundations must not be empty")
    validate_unique_foundations(foundations)
    raw_capabilities = require_list(
        root.get("capabilities"), "manifest.capabilities"
    )
    capabilities = tuple(
        parse_capability(item, index)
        for index, item in enumerate(raw_capabilities)
    )
    if not capabilities:
        raise CapabilityMatrixError("manifest.capabilities must not be empty")
    validate_unique_capabilities(capabilities)
    raw_operations = require_list(
        root.get("operations"), "manifest.operations"
    )
    operations = tuple(
        parse_operation(item, index)
        for index, item in enumerate(raw_operations)
    )
    if not operations:
        raise CapabilityMatrixError("manifest.operations must not be empty")
    validate_unique_operations(operations)
    validate_operation_capabilities(operations, capabilities)
    raw_modules = require_list(root.get("modules"), "manifest.modules")
    modules = tuple(
        parse_arrow_module(item, index)
        for index, item in enumerate(raw_modules)
    )
    if not modules:
        raise CapabilityMatrixError("manifest.modules must not be empty")
    validate_modules(modules, capabilities)

    return Manifest(
        schema_version=schema_version,
        arrow_cpp_version=arrow_version,
        pyarrow_constraint=pyarrow_constraint,
        arrow_sources_constraint=arrow_sources_constraint,
        distribution=distribution,
        abi=abi,
        foundations=foundations,
        capabilities=capabilities,
        operations=operations,
        modules=modules,
    )


def parse_abi_contract(value: object) -> AbiContract:
    """
    title: Validate the initial unified Arrow C ABI contract.
    parameters:
      value:
        type: object
    returns:
      type: AbiContract
    """
    context = "manifest.abi"
    item = require_mapping(value, context)
    expected_strings = {
        "name": "irx_arrow",
        "symbol_prefix": "irx_arrow_",
        "compatibility": "same_major_runtime_minor_gte_consumer",
        "version_query": "irx_arrow_abi_version",
        "feature_query": "irx_arrow_runtime_has_feature",
    }
    values = {
        field: require_string(item, field, context)
        for field in expected_strings
    }
    mismatches = {
        field: (expected, values[field])
        for field, expected in expected_strings.items()
        if values[field] != expected
    }
    if mismatches:
        raise CapabilityMatrixError(
            f"{context} does not match the accepted ABI: {mismatches}"
        )
    version = tuple(
        require_int(item, field, context)
        for field in ("major", "minor", "patch")
    )
    if version != (1, 0, 0):
        raise CapabilityMatrixError(
            f"{context} initial version must be 1.0.0, got {version}"
        )
    raw_legacy = require_list(
        item.get("legacy_prefixes"), f"{context}.legacy_prefixes"
    )
    legacy_prefixes = tuple(
        require_string_value(prefix, f"{context}.legacy_prefixes[{index}]")
        for index, prefix in enumerate(raw_legacy)
    )
    if legacy_prefixes != ("irx_rb_",):
        raise CapabilityMatrixError(
            f"{context}.legacy_prefixes must contain only 'irx_rb_'"
        )
    return AbiContract(
        name=values["name"],
        major=version[0],
        minor=version[1],
        patch=version[2],
        symbol_prefix=values["symbol_prefix"],
        legacy_prefixes=legacy_prefixes,
        compatibility=values["compatibility"],
        version_query=values["version_query"],
        feature_query=values["feature_query"],
    )


def parse_distribution(value: object) -> Distribution:
    """
    title: Validate the accepted native artifact distribution strategy.
    parameters:
      value:
        type: object
    returns:
      type: Distribution
    """
    context = "manifest.distribution"
    item = require_mapping(value, context)
    expected = {
        "strategy": "dedicated_runtime_wheels",
        "core_package": "arx-arrowcpp-runtime",
        "pyarrow_role": "optional_arxpy_interop_and_test_bootstrap",
        "system_arrow_role": "explicit_validated_developer_override",
        "source_build_role": "explicit_advanced_fallback",
        "compiled_output_policy": "bundle_activated_libraries",
        "python_abi": "abi_independent_platform_wheels",
    }
    values = {
        field: require_string(item, field, context) for field in expected
    }
    mismatches = {
        field: (expected_value, values[field])
        for field, expected_value in expected.items()
        if values[field] != expected_value
    }
    if mismatches:
        raise CapabilityMatrixError(
            f"{context} does not match the accepted strategy: {mismatches}"
        )
    raw_optional = require_list(
        item.get("optional_packages"), f"{context}.optional_packages"
    )
    optional_packages = tuple(
        require_string_value(package, f"{context}.optional_packages[{index}]")
        for index, package in enumerate(raw_optional)
    )
    if not optional_packages or len(optional_packages) != len(
        set(optional_packages)
    ):
        raise CapabilityMatrixError(
            f"{context}.optional_packages must be non-empty and unique"
        )
    return Distribution(
        strategy=values["strategy"],
        core_package=values["core_package"],
        optional_packages=optional_packages,
        pyarrow_role=values["pyarrow_role"],
        system_arrow_role=values["system_arrow_role"],
        source_build_role=values["source_build_role"],
        compiled_output_policy=values["compiled_output_policy"],
        python_abi=values["python_abi"],
    )


def parse_foundation(value: object, index: int) -> Foundation:
    """
    title: Validate one tracked foundation entry.
    parameters:
      value:
        type: object
      index:
        type: int
    returns:
      type: Foundation
    """
    context = f"manifest.foundations[{index}]"
    item = require_mapping(value, context)
    foundation_id = require_string(item, "id", context)
    if FOUNDATION_ID_PATTERN.fullmatch(foundation_id) is None:
        raise CapabilityMatrixError(
            f"{context}.id is invalid: {foundation_id!r}"
        )
    status = require_string(item, "status", context)
    if status not in READINESS_STATUS_LABELS:
        raise CapabilityMatrixError(
            f"{context}.status must be one of {tuple(READINESS_STATUS_LABELS)}"
        )

    raw_test_targets = require_list(
        item.get("test_targets"), f"{context}.test_targets"
    )
    test_targets = tuple(
        parse_repository_path(
            target, f"{context}.test_targets[{target_index}]"
        )
        for target_index, target in enumerate(raw_test_targets)
    )
    if not test_targets:
        raise CapabilityMatrixError(
            f"{context}.test_targets must not be empty"
        )

    raw_blocks = require_list(item.get("blocks"), f"{context}.blocks")
    blocks = tuple(
        parse_milestone(block, f"{context}.blocks[{block_index}]")
        for block_index, block in enumerate(raw_blocks)
    )
    if not blocks:
        raise CapabilityMatrixError(f"{context}.blocks must not be empty")

    return Foundation(
        id=foundation_id,
        name=require_string(item, "name", context),
        owner=require_string(item, "owner", context),
        status=status,
        test_targets=test_targets,
        blocks=blocks,
        baseline=require_string(item, "baseline", context),
        completion=require_string(item, "completion", context),
    )


def parse_operation(value: object, index: int) -> Operation:
    """
    title: Validate one operation placement entry.
    parameters:
      value:
        type: object
      index:
        type: int
    returns:
      type: Operation
    """
    context = f"manifest.operations[{index}]"
    item = require_mapping(value, context)
    operation_id = require_string(item, "id", context)
    if CAPABILITY_ID_PATTERN.fullmatch(operation_id) is None:
        raise CapabilityMatrixError(
            f"{context}.id is not stable kebab case: {operation_id!r}"
        )
    placement = require_string(item, "placement", context)
    if placement not in PLACEMENT_LABELS:
        raise CapabilityMatrixError(
            f"{context}.placement must be one of {tuple(PLACEMENT_LABELS)}"
        )
    visibility = require_string(item, "visibility", context)
    if visibility not in VISIBILITY_LABELS:
        raise CapabilityMatrixError(
            f"{context}.visibility must be one of {tuple(VISIBILITY_LABELS)}"
        )
    module = require_string(item, "module", context)
    surface = require_string(item, "surface", context)
    validate_public_namespace(module, surface, visibility, context)

    raw_capabilities = require_list(
        item.get("capabilities"), f"{context}.capabilities"
    )
    capabilities = tuple(
        require_string_value(
            capability,
            f"{context}.capabilities[{capability_index}]",
        )
        for capability_index, capability in enumerate(raw_capabilities)
    )
    if not capabilities:
        raise CapabilityMatrixError(
            f"{context}.capabilities must not be empty"
        )

    milestone = require_string(item, "target_milestone", context)
    if MILESTONE_PATTERN.fullmatch(milestone) is None:
        raise CapabilityMatrixError(
            f"{context}.target_milestone is invalid: {milestone!r}"
        )
    validate_placement_module(placement, module, context)
    return Operation(
        id=operation_id,
        name=require_string(item, "name", context),
        surface=surface,
        placement=placement,
        module=module,
        visibility=visibility,
        target_milestone=milestone,
        capabilities=capabilities,
        rationale=require_string(item, "rationale", context),
    )


def parse_arrow_module(value: object, index: int) -> ArrowModule:
    """
    title: Validate one upstream module-scope classification.
    parameters:
      value:
        type: object
      index:
        type: int
    returns:
      type: ArrowModule
    """
    context = f"manifest.modules[{index}]"
    item = require_mapping(value, context)
    module_id = require_string(item, "id", context)
    if CAPABILITY_ID_PATTERN.fullmatch(module_id) is None:
        raise CapabilityMatrixError(
            f"{context}.id is not stable kebab case: {module_id!r}"
        )
    classification = require_string(item, "classification", context)
    if classification not in MODULE_CLASSIFICATION_LABELS:
        raise CapabilityMatrixError(
            f"{context}.classification must be one of "
            f"{tuple(MODULE_CLASSIFICATION_LABELS)}"
        )
    public_module = require_string(item, "public_module", context)
    if "arrow" in {part.lower() for part in public_module.split(".")}:
        raise CapabilityMatrixError(
            f"{context}.public_module exposes an Arrow namespace"
        )
    raw_capabilities = require_list(
        item.get("capabilities"), f"{context}.capabilities"
    )
    capabilities = tuple(
        require_string_value(
            capability,
            f"{context}.capabilities[{capability_index}]",
        )
        for capability_index, capability in enumerate(raw_capabilities)
    )
    return ArrowModule(
        id=module_id,
        upstream=require_string(item, "upstream", context),
        classification=classification,
        public_module=public_module,
        runtime_feature=require_string(item, "runtime_feature", context),
        capabilities=capabilities,
        rationale=require_string(item, "rationale", context),
    )


def parse_capability(value: object, index: int) -> Capability:
    """
    title: Validate one capability entry.
    parameters:
      value:
        type: object
      index:
        type: int
    returns:
      type: Capability
    """
    context = f"manifest.capabilities[{index}]"
    item = require_mapping(value, context)
    capability_id = require_string(item, "id", context)
    if CAPABILITY_ID_PATTERN.fullmatch(capability_id) is None:
        raise CapabilityMatrixError(
            f"{context}.id is not a stable kebab-case ID: {capability_id!r}"
        )

    scope = require_string(item, "scope", context)
    if scope not in SCOPE_LABELS:
        raise CapabilityMatrixError(
            f"{context}.scope has unknown value: {scope!r}"
        )
    milestone = require_string(item, "target_milestone", context)
    if MILESTONE_PATTERN.fullmatch(milestone) is None:
        raise CapabilityMatrixError(
            f"{context}.target_milestone is invalid: {milestone!r}"
        )

    stages_value = require_mapping(item.get("stages"), f"{context}.stages")
    unknown_stages = set(stages_value) - set(STAGE_NAMES)
    missing_stages = set(STAGE_NAMES) - set(stages_value)
    if unknown_stages or missing_stages:
        raise CapabilityMatrixError(
            f"{context}.stages must contain exactly {STAGE_NAMES}; "
            f"missing={sorted(missing_stages)}, "
            f"unknown={sorted(unknown_stages)}"
        )
    stages = {
        stage: require_status(stages_value.get(stage), f"{context}.{stage}")
        for stage in STAGE_NAMES
    }
    overall = require_status(item.get("overall"), f"{context}.overall")
    evidence_values = require_list(item.get("evidence"), f"{context}.evidence")
    evidence = tuple(
        parse_evidence(evidence_value, context, evidence_index)
        for evidence_index, evidence_value in enumerate(evidence_values)
    )
    if not evidence:
        raise CapabilityMatrixError(
            f"{context}.evidence must link at least one test"
        )

    return Capability(
        id=capability_id,
        category=require_string(item, "category", context),
        name=require_string(item, "name", context),
        scope=scope,
        target_milestone=milestone,
        stages=stages,
        overall=overall,
        notes=require_string(item, "notes", context),
        evidence=evidence,
    )


def parse_evidence(
    value: object,
    capability_context: str,
    index: int,
) -> Evidence:
    """
    title: Validate one test-evidence reference.
    parameters:
      value:
        type: object
      capability_context:
        type: str
      index:
        type: int
    returns:
      type: Evidence
    """
    context = f"{capability_context}.evidence[{index}]"
    item = require_mapping(value, context)
    relative_path = Path(require_string(item, "path", context))
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise CapabilityMatrixError(
            f"{context}.path must be repository-relative: {relative_path}"
        )
    path = ROOT / relative_path
    if not path.is_file():
        raise CapabilityMatrixError(
            f"{context}.path does not exist: {relative_path}"
        )
    symbol = require_string(item, "symbol", context)
    find_symbol_line(path, symbol)
    return Evidence(
        path=relative_path,
        symbol=symbol,
        purpose=require_string(item, "purpose", context),
    )


def parse_repository_path(value: object, context: str) -> Path:
    """
    title: Validate one repository-relative file path.
    parameters:
      value:
        type: object
      context:
        type: str
    returns:
      type: Path
    """
    if not isinstance(value, str) or not value.strip():
        raise CapabilityMatrixError(f"{context} must be a non-empty string")
    relative_path = Path(value)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise CapabilityMatrixError(
            f"{context} must be repository-relative: {relative_path}"
        )
    if not (ROOT / relative_path).is_file():
        raise CapabilityMatrixError(
            f"{context} does not exist: {relative_path}"
        )
    return relative_path


def parse_milestone(value: object, context: str) -> str:
    """
    title: Validate one blocking milestone identifier.
    parameters:
      value:
        type: object
      context:
        type: str
    returns:
      type: str
    """
    if (
        not isinstance(value, str)
        or MILESTONE_PATTERN.fullmatch(value) is None
    ):
        raise CapabilityMatrixError(f"{context} is not a valid milestone")
    return value


def require_mapping(value: object, context: str) -> dict[str, object]:
    """
    title: Require an object with string keys.
    parameters:
      value:
        type: object
      context:
        type: str
    returns:
      type: dict[str, object]
    """
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise CapabilityMatrixError(f"{context} must be an object")
    return cast(dict[str, object], value)


def require_list(value: object, context: str) -> list[object]:
    """
    title: Require a list value.
    parameters:
      value:
        type: object
      context:
        type: str
    returns:
      type: list[object]
    """
    if not isinstance(value, list):
        raise CapabilityMatrixError(f"{context} must be a list")
    return cast(list[object], value)


def require_string(
    mapping: dict[str, object],
    key: str,
    context: str,
) -> str:
    """
    title: Require a non-empty string field.
    parameters:
      mapping:
        type: dict[str, object]
      key:
        type: str
      context:
        type: str
    returns:
      type: str
    """
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityMatrixError(
            f"{context}.{key} must be a non-empty string"
        )
    return value


def require_string_value(value: object, context: str) -> str:
    """
    title: Require a standalone non-empty string value.
    parameters:
      value:
        type: object
      context:
        type: str
    returns:
      type: str
    """
    if not isinstance(value, str) or not value.strip():
        raise CapabilityMatrixError(f"{context} must be a non-empty string")
    return value


def require_int(
    mapping: dict[str, object],
    key: str,
    context: str,
) -> int:
    """
    title: Require an integer field.
    parameters:
      mapping:
        type: dict[str, object]
      key:
        type: str
      context:
        type: str
    returns:
      type: int
    """
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise CapabilityMatrixError(f"{context}.{key} must be an integer")
    return value


def require_status(value: object, context: str) -> str:
    """
    title: Require a supported capability status.
    parameters:
      value:
        type: object
      context:
        type: str
    returns:
      type: str
    """
    if not isinstance(value, str) or value not in STATUS_LABELS:
        raise CapabilityMatrixError(
            f"{context} must be one of {tuple(STATUS_LABELS)}"
        )
    return value


def validate_unique_capabilities(
    capabilities: tuple[Capability, ...],
) -> None:
    """
    title: Reject duplicate capability identifiers.
    parameters:
      capabilities:
        type: tuple[Capability, Ellipsis]
    """
    identifiers = [capability.id for capability in capabilities]
    duplicates = sorted(
        identifier
        for identifier, count in Counter(identifiers).items()
        if count > 1
    )
    if duplicates:
        raise CapabilityMatrixError(
            f"duplicate capability IDs: {', '.join(duplicates)}"
        )


def validate_unique_foundations(foundations: tuple[Foundation, ...]) -> None:
    """
    title: Reject duplicate foundation identifiers.
    parameters:
      foundations:
        type: tuple[Foundation, Ellipsis]
    """
    identifiers = [foundation.id for foundation in foundations]
    duplicates = sorted(
        identifier
        for identifier, count in Counter(identifiers).items()
        if count > 1
    )
    if duplicates:
        raise CapabilityMatrixError(
            f"duplicate foundation IDs: {', '.join(duplicates)}"
        )


def validate_unique_operations(operations: tuple[Operation, ...]) -> None:
    """
    title: Reject duplicate operation identifiers.
    parameters:
      operations:
        type: tuple[Operation, Ellipsis]
    """
    identifiers = [operation.id for operation in operations]
    duplicates = sorted(
        identifier
        for identifier, count in Counter(identifiers).items()
        if count > 1
    )
    if duplicates:
        raise CapabilityMatrixError(
            f"duplicate operation IDs: {', '.join(duplicates)}"
        )


def validate_operation_capabilities(
    operations: tuple[Operation, ...],
    capabilities: tuple[Capability, ...],
) -> None:
    """
    title: Require every operation to reference known capability rows.
    parameters:
      operations:
        type: tuple[Operation, Ellipsis]
      capabilities:
        type: tuple[Capability, Ellipsis]
    """
    known = {capability.id for capability in capabilities}
    referenced: set[str] = set()
    for operation in operations:
        referenced.update(operation.capabilities)
        unknown = sorted(set(operation.capabilities) - known)
        if unknown:
            raise CapabilityMatrixError(
                f"operation {operation.id!r} references unknown "
                f"capabilities: {', '.join(unknown)}"
            )
    missing = sorted(known - referenced)
    if missing:
        raise CapabilityMatrixError(
            "capabilities without an operation placement: "
            f"{', '.join(missing)}"
        )


def validate_public_namespace(
    module: str,
    surface: str,
    visibility: str,
    context: str,
) -> None:
    """
    title: Reject an Arrow namespace from public Arx APIs.
    parameters:
      module:
        type: str
      surface:
        type: str
      visibility:
        type: str
      context:
        type: str
    """
    if visibility != "public":
        return
    module_parts = {part.lower() for part in module.split(".")}
    if "arrow" in module_parts or "arrow." in surface.lower():
        raise CapabilityMatrixError(
            f"{context} exposes the forbidden public Arrow namespace"
        )


def validate_placement_module(
    placement: str,
    module: str,
    context: str,
) -> None:
    """
    title: Require domain standard-library placements to use fixed facades.
    parameters:
      placement:
        type: str
      module:
        type: str
      context:
        type: str
    """
    required_modules = {
        "stdlib_compute": "stdlib.compute",
        "stdlib_io": "stdlib.io",
        "stdlib_dataset": "stdlib.dataset",
    }
    expected = required_modules.get(placement)
    if expected is not None and module != expected:
        raise CapabilityMatrixError(
            f"{context}.module must be {expected!r} for {placement!r}"
        )


def validate_modules(
    modules: tuple[ArrowModule, ...],
    capabilities: tuple[Capability, ...],
) -> None:
    """
    title: Validate upstream module IDs, scopes, and capability references.
    parameters:
      modules:
        type: tuple[ArrowModule, Ellipsis]
      capabilities:
        type: tuple[Capability, Ellipsis]
    """
    identifiers = [module.id for module in modules]
    duplicates = sorted(
        identifier
        for identifier, count in Counter(identifiers).items()
        if count > 1
    )
    if duplicates:
        raise CapabilityMatrixError(
            f"duplicate module IDs: {', '.join(duplicates)}"
        )
    classifications = {module.classification for module in modules}
    missing_classifications = (
        set(MODULE_CLASSIFICATION_LABELS) - classifications
    )
    if missing_classifications:
        raise CapabilityMatrixError(
            "module inventory does not exercise classifications: "
            f"{', '.join(sorted(missing_classifications))}"
        )
    known_capabilities = {capability.id for capability in capabilities}
    for module in modules:
        unknown = sorted(set(module.capabilities) - known_capabilities)
        if unknown:
            raise CapabilityMatrixError(
                f"module {module.id!r} references unknown capabilities: "
                f"{', '.join(unknown)}"
            )
        if module.classification in {"internal", "out_of_scope"}:
            if module.public_module != "none":
                raise CapabilityMatrixError(
                    f"module {module.id!r} must not expose a public module"
                )
        if module.classification == "standard_library":
            if not module.public_module.startswith("stdlib."):
                raise CapabilityMatrixError(
                    f"module {module.id!r} needs a standard-library facade"
                )


def validate_dependency_pins(manifest: Manifest) -> None:
    """
    title: Ensure the manifest matches the checked-in Arrow dependencies.
    parameters:
      manifest:
        type: Manifest
    """
    project = IRX_PROJECT.read_text(encoding="utf-8")
    pyarrow_entry = f'"pyarrow ({manifest.pyarrow_constraint})"'
    sources_entry = (
        f'"arx-arrowcpp-sources {manifest.arrow_sources_constraint}"'
    )
    if pyarrow_entry not in project:
        raise CapabilityMatrixError(
            "manifest PyArrow constraint does not match "
            f"{IRX_PROJECT.relative_to(ROOT)}: {manifest.pyarrow_constraint}"
        )
    if sources_entry not in project:
        raise CapabilityMatrixError(
            "manifest Arrow source constraint does not match "
            f"{IRX_PROJECT.relative_to(ROOT)}: "
            f"{manifest.arrow_sources_constraint}"
        )
    expected_sources = f"== {manifest.arrow_cpp_version}"
    if manifest.arrow_sources_constraint != expected_sources:
        raise CapabilityMatrixError(
            "Arrow C++ version and source dependency differ: "
            f"{manifest.arrow_cpp_version} versus "
            f"{manifest.arrow_sources_constraint}"
        )


def find_symbol_line(path: Path, symbol: str) -> int:
    """
    title: Find a Python test symbol and return its one-based source line.
    parameters:
      path:
        type: Path
      symbol:
        type: str
    returns:
      type: int
    """
    pattern = re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(symbol)}\s*\(")
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if pattern.match(line):
            return line_number
    raise CapabilityMatrixError(
        f"evidence symbol {symbol!r} does not exist in "
        f"{path.relative_to(ROOT)}"
    )


def render_manifest(manifest: Manifest, manifest_path: Path) -> str:
    """
    title: Render a validated manifest as Markdown.
    parameters:
      manifest:
        type: Manifest
      manifest_path:
        type: Path
    returns:
      type: str
    """
    try:
        source_name = manifest_path.relative_to(ROOT)
    except ValueError:
        source_name = manifest_path
    lines = [
        "<!--",
        "Generated by scripts/gen_arrow_capability_matrix.py from",
        f"{source_name}. Do not edit this file directly.",
        "-->",
        "",
        "# Apache Arrow Capability Matrix",
        "",
        f"**Arrow C++ baseline:** {manifest.arrow_cpp_version}",
        "",
        f"**PyArrow constraint:** `{manifest.pyarrow_constraint}`",
        "",
        "This matrix records the checked-in implementation baseline, not only",
        "planned syntax or AST declarations. A row remains partial until all",
        "required compiler stages and native behavior have conformance tests.",
        "Arx exposes core data concepts directly and does not require an",
        "`arrow` namespace.",
        "",
        "## Status legend",
        "",
        "| Status | Meaning |",
        "| --- | --- |",
        "| Complete | The stage has the required target behavior and tests. |",
        "| Partial | Checked behavior exists, but the target is incomplete. |",
        "| Not started | No qualifying implementation exists at that stage. |",
        "| N/A | The stage does not participate in this capability. |",
        "",
    ]
    lines.extend(render_distribution(manifest.distribution))
    lines.extend(render_abi_contract(manifest.abi))
    lines.extend(render_foundations(manifest.foundations))
    lines.extend(render_operations(manifest.operations))
    lines.extend(render_modules(manifest.modules))
    categories = tuple(
        dict.fromkeys(
            capability.category for capability in manifest.capabilities
        )
    )
    for category in categories:
        lines.extend(render_category(manifest.capabilities, category))
    lines.extend(render_summary(manifest.capabilities))
    return "\n".join(lines).rstrip() + "\n"


def render_distribution(distribution: Distribution) -> list[str]:
    """
    title: Render the accepted native artifact strategy.
    parameters:
      distribution:
        type: Distribution
    returns:
      type: list[str]
    """
    optional_packages = ", ".join(
        f"`{package}`" for package in distribution.optional_packages
    )
    return [
        "## Native distribution decision",
        "",
        "| Property | Accepted value |",
        "| --- | --- |",
        f"| Strategy | `{distribution.strategy}` |",
        f"| Core package | `{distribution.core_package}` |",
        f"| Optional packages | {optional_packages} |",
        f"| PyArrow role | `{distribution.pyarrow_role}` |",
        f"| System Arrow role | `{distribution.system_arrow_role}` |",
        f"| Source build role | `{distribution.source_build_role}` |",
        f"| Compiled output | `{distribution.compiled_output_policy}` |",
        f"| Python ABI | `{distribution.python_abi}` |",
        "",
    ]


def render_abi_contract(abi: AbiContract) -> list[str]:
    """
    title: Render the accepted unified Arrow C ABI contract.
    parameters:
      abi:
        type: AbiContract
    returns:
      type: list[str]
    """
    version = f"{abi.major}.{abi.minor}.{abi.patch}"
    legacy = ", ".join(f"`{prefix}`" for prefix in abi.legacy_prefixes)
    return [
        "## Unified C ABI decision",
        "",
        "| Property | Accepted value |",
        "| --- | --- |",
        f"| ABI name | `{abi.name}` |",
        f"| Initial version | `{version}` |",
        f"| Symbol prefix | `{abi.symbol_prefix}` |",
        f"| Transitional legacy prefixes | {legacy} |",
        f"| Compatibility | `{abi.compatibility}` |",
        f"| Version query | `{abi.version_query}` |",
        f"| Feature query | `{abi.feature_query}` |",
        "",
    ]


def render_foundations(foundations: tuple[Foundation, ...]) -> list[str]:
    """
    title: Render the tracked core-foundation readiness ledger.
    parameters:
      foundations:
        type: tuple[Foundation, Ellipsis]
    returns:
      type: list[str]
    """
    lines = [
        "## Core foundation readiness",
        "",
        "These are language and compiler prerequisites, not Arrow feature",
        "substitutes. A blocking milestone cannot complete until every",
        "associated foundation row is done.",
        "",
        "| ID | Foundation | Owner | Status | Test targets | Blocks |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for foundation in foundations:
        test_targets = "<br>".join(
            render_test_target(target) for target in foundation.test_targets
        )
        values = [
            f"`{foundation.id}`",
            escape_table(foundation.name),
            escape_table(foundation.owner),
            READINESS_STATUS_LABELS[foundation.status],
            test_targets,
            ", ".join(foundation.blocks),
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(["", "### Foundation completion contracts", ""])
    for foundation in foundations:
        lines.extend(
            [
                f"- **{foundation.id} — {foundation.name}**",
                f"  - Baseline: {foundation.baseline}",
                f"  - Required: {foundation.completion}",
            ]
        )
    lines.append("")
    return lines


def render_test_target(path: Path) -> str:
    """
    title: Render a foundation test target as a source link.
    parameters:
      path:
        type: Path
    returns:
      type: str
    """
    url = f"{REPOSITORY_SOURCE_URL}/{path.as_posix()}"
    return f"[`{escape_table(path.as_posix())}`]({url})"


def render_operations(operations: tuple[Operation, ...]) -> list[str]:
    """
    title: Render the public operation placement catalog.
    parameters:
      operations:
        type: tuple[Operation, Ellipsis]
    returns:
      type: list[str]
    """
    lines = [
        "## Operation placement catalog",
        "",
        "The catalog classifies operation families, not every Arrow C++",
        "overload. Concrete registry entries inherit the placement of",
        "their family. Public modules never use an `arrow` namespace.",
        "",
        "| ID | Operation | Surface | Placement | Module | Visibility | "
        "Target | Capabilities |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for operation in operations:
        values = [
            f"`{operation.id}`",
            escape_table(operation.name),
            f"`{escape_table(operation.surface)}`",
            PLACEMENT_LABELS[operation.placement],
            f"`{escape_table(operation.module)}`",
            VISIBILITY_LABELS[operation.visibility],
            operation.target_milestone,
            ", ".join(f"`{item}`" for item in operation.capabilities),
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(["", "### Placement rationale", ""])
    lines.extend(
        f"- **{operation.id} — {operation.name}:** {operation.rationale}"
        for operation in operations
    )
    lines.append("")
    return lines


def render_modules(modules: tuple[ArrowModule, ...]) -> list[str]:
    """
    title: Render the upstream Arrow module-scope inventory.
    parameters:
      modules:
        type: tuple[ArrowModule, Ellipsis]
    returns:
      type: list[str]
    """
    lines = [
        "## Upstream module scope",
        "",
        "This inventory groups the Arrow 24 C++ header and library tree into",
        "Arx product scopes. Internal source subdirectories inherit their",
        "nearest listed module unless a more specific row overrides it.",
        "",
        "| ID | Upstream module | Classification | Public Arx module | "
        "Runtime feature | Capabilities |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for module in modules:
        capabilities = (
            ", ".join(f"`{item}`" for item in module.capabilities)
            if module.capabilities
            else "—"
        )
        values = [
            f"`{module.id}`",
            f"`{escape_table(module.upstream)}`",
            MODULE_CLASSIFICATION_LABELS[module.classification],
            f"`{escape_table(module.public_module)}`",
            f"`{escape_table(module.runtime_feature)}`",
            capabilities,
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(["", "### Module rationale", ""])
    lines.extend(
        f"- **{module.id}:** {module.rationale}" for module in modules
    )
    lines.append("")
    return lines


def render_category(
    capabilities: tuple[Capability, ...],
    category: str,
) -> list[str]:
    """
    title: Render one capability category.
    parameters:
      capabilities:
        type: tuple[Capability, Ellipsis]
      category:
        type: str
    returns:
      type: list[str]
    """
    lines = [
        f"## {category}",
        "",
        "| Capability | Scope | Target | "
        + " | ".join(STAGE_LABELS[stage] for stage in STAGE_NAMES)
        + " | Overall | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    category_capabilities = tuple(
        capability
        for capability in capabilities
        if capability.category == category
    )
    for capability in category_capabilities:
        evidence_links = "<br>".join(
            render_evidence_link(evidence) for evidence in capability.evidence
        )
        values = [
            f"**{escape_table(capability.name)}**<br>`{capability.id}`",
            SCOPE_LABELS[capability.scope],
            capability.target_milestone,
            *(
                STATUS_LABELS[capability.stages[stage]]
                for stage in STAGE_NAMES
            ),
            STATUS_LABELS[capability.overall],
            evidence_links,
        ]
        lines.append("| " + " | ".join(values) + " |")
    lines.extend(["", "### Baseline notes", ""])
    lines.extend(
        f"- **{capability.name}:** {capability.notes}"
        for capability in category_capabilities
    )
    lines.append("")
    return lines


def render_evidence_link(evidence: Evidence) -> str:
    """
    title: Render one evidence reference as a source link.
    parameters:
      evidence:
        type: Evidence
    returns:
      type: str
    """
    line = find_symbol_line(ROOT / evidence.path, evidence.symbol)
    label = escape_table(evidence.symbol)
    purpose = escape_table(evidence.purpose).replace('"', "&quot;")
    url = f"{REPOSITORY_SOURCE_URL}/{evidence.path.as_posix()}#L{line}"
    return f'[`{label}`]({url} "{purpose}")'


def render_summary(capabilities: tuple[Capability, ...]) -> list[str]:
    """
    title: Render overall status totals.
    parameters:
      capabilities:
        type: tuple[Capability, Ellipsis]
    returns:
      type: list[str]
    """
    counts = Counter(capability.overall for capability in capabilities)
    lines = [
        "## Baseline totals",
        "",
        "| Overall status | Capabilities |",
        "| --- | ---: |",
    ]
    for status, label in STATUS_LABELS.items():
        lines.append(f"| {label} | {counts[status]} |")
    lines.extend(
        [
            "",
            "Upgrade a status only with implementation evidence at the",
            "earliest responsible layer and integration evidence across every",
            "affected package boundary.",
            "",
        ]
    )
    return lines


def escape_table(value: str) -> str:
    """
    title: Escape text for use in a Markdown table cell.
    parameters:
      value:
        type: str
    returns:
      type: str
    """
    return value.replace("|", "\\|").replace("\n", " ")


def check_output(path: Path, expected: str) -> None:
    """
    title: Fail when a generated matrix is absent or stale.
    parameters:
      path:
        type: Path
      expected:
        type: str
    """
    if not path.is_file():
        raise CapabilityMatrixError(f"generated matrix is missing: {path}")
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        raise CapabilityMatrixError(
            f"generated matrix is stale: {path}; run "
            "python scripts/gen_arrow_capability_matrix.py"
        )


def write_output(path: Path, rendered: str) -> None:
    """
    title: Write the generated Markdown matrix.
    parameters:
      path:
        type: Path
      rendered:
        type: str
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
