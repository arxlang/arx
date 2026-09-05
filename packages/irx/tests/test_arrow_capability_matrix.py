"""
title: Arrow capability manifest tests.
"""

from __future__ import annotations

import json
import subprocess
import sys

from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "docs" / "data" / "arrow-capabilities.json"
GENERATOR = ROOT / "scripts" / "gen_arrow_capability_matrix.py"
REQUIRED_ARROW_24_CAPABILITY_IDS = frozenset(
    {
        "acero",
        "array",
        "binary",
        "c-data-interface",
        "c-stream-interface",
        "chunked-array-series",
        "compute",
        "csv-json-parquet",
        "dense-tensor",
        "device-dlpack",
        "dictionary",
        "extension-types",
        "filesystem-dataset-scanner",
        "fixed-size-binary",
        "flight",
        "ipc",
        "list-family",
        "null-boolean",
        "primitive-numeric",
        "record-batch",
        "run-end-encoded",
        "scalar-buffer",
        "sparse-tensors",
        "struct-map",
        "substrait",
        "table-dataframe",
        "temporal",
        "union",
        "utf8",
        "decimal",
    }
)
REQUIRED_FOUNDATION_IDS = frozenset(
    {
        "FND-001",
        "FND-002",
        "FND-003",
        "FND-004",
        "FND-005",
        "FND-006",
        "FND-007",
        "FND-008",
        "FND-009",
        "FND-010",
        "FND-011",
        "FND-012",
        "FND-013",
        "FND-014",
        "FND-015",
        "FND-016",
        "FND-017",
        "FND-018",
    }
)
EXPECTED_OPERATION_COUNT = 52
EXPECTED_MODULE_COUNT = 29
EXPECTED_PLACEMENTS = frozenset(
    {
        "builtin_operator",
        "bundled_builtin_module",
        "compiler_builtin_type",
        "compiler_intrinsic",
        "internal_runtime",
        "interop_only",
        "optional_module",
        "stdlib_compute",
        "stdlib_dataset",
        "stdlib_io",
    }
)
EXPECTED_MODULE_CLASSIFICATIONS = frozenset(
    {
        "core_language",
        "internal",
        "interoperability",
        "optional",
        "out_of_scope",
        "preserve_only",
        "standard_library",
    }
)


def load_capabilities() -> list[dict[str, object]]:
    """
    title: Load capability objects from the checked-in manifest.
    returns:
      type: list[dict[str, object]]
    """
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    capabilities = value.get("capabilities")
    assert isinstance(capabilities, list)
    assert all(isinstance(item, dict) for item in capabilities)
    return cast(list[dict[str, object]], capabilities)


def load_foundations() -> list[dict[str, object]]:
    """
    title: Load foundation objects from the checked-in manifest.
    returns:
      type: list[dict[str, object]]
    """
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    foundations = value.get("foundations")
    assert isinstance(foundations, list)
    assert all(isinstance(item, dict) for item in foundations)
    return cast(list[dict[str, object]], foundations)


def load_operations() -> list[dict[str, object]]:
    """
    title: Load operation objects from the checked-in manifest.
    returns:
      type: list[dict[str, object]]
    """
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    operations = value.get("operations")
    assert isinstance(operations, list)
    assert all(isinstance(item, dict) for item in operations)
    return cast(list[dict[str, object]], operations)


def load_distribution() -> dict[str, object]:
    """
    title: Load the accepted native distribution decision.
    returns:
      type: dict[str, object]
    """
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    distribution = value.get("distribution")
    assert isinstance(distribution, dict)
    return cast(dict[str, object], distribution)


def load_abi_contract() -> dict[str, object]:
    """
    title: Load the accepted unified Arrow C ABI contract.
    returns:
      type: dict[str, object]
    """
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    abi = value.get("abi")
    assert isinstance(abi, dict)
    return cast(dict[str, object], abi)


def load_modules() -> list[dict[str, object]]:
    """
    title: Load the upstream Arrow module classifications.
    returns:
      type: list[dict[str, object]]
    """
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    modules = value.get("modules")
    assert isinstance(modules, list)
    assert all(isinstance(item, dict) for item in modules)
    return cast(list[dict[str, object]], modules)


def test_required_arrow_24_capabilities_are_classified() -> None:
    """
    title: Every required Arrow 24 family has one stable capability row.
    """
    capabilities = load_capabilities()
    identifiers = [item.get("id") for item in capabilities]

    assert len(identifiers) == len(set(identifiers))
    assert set(identifiers) == REQUIRED_ARROW_24_CAPABILITY_IDS


def test_required_arrow_foundations_have_tracked_rows() -> None:
    """
    title: Every required Arrow foundation has one stable tracked row.
    """
    foundations = load_foundations()
    identifiers = [item.get("id") for item in foundations]

    assert len(identifiers) == len(set(identifiers))
    assert set(identifiers) == REQUIRED_FOUNDATION_IDS


def test_public_operation_catalog_is_builtin_first_and_unqualified() -> None:
    """
    title: Public operations use every approved layer and no Arrow namespace.
    """
    operations = load_operations()
    identifiers = [item.get("id") for item in operations]
    placements = {item.get("placement") for item in operations}
    public_modules: set[str] = set()

    for item in operations:
        if item.get("visibility") != "public":
            continue
        module = item.get("module")
        surface = item.get("surface")
        assert isinstance(module, str)
        assert isinstance(surface, str)
        assert "arrow" not in {part.lower() for part in module.split(".")}
        assert "arrow." not in surface.lower()
        public_modules.add(module)

    assert len(identifiers) == EXPECTED_OPERATION_COUNT
    assert len(identifiers) == len(set(identifiers))
    assert placements == EXPECTED_PLACEMENTS
    assert {
        "stdlib.compute",
        "stdlib.dataset",
        "stdlib.io",
    }.issubset(public_modules)


def test_nullable_surface_reuses_existing_union_syntax() -> None:
    """
    title: Nullable values use T union none instead of new punctuation.
    """
    operations = load_operations()
    nullable = next(
        item for item in operations if item.get("id") == "type-nullable-scalar"
    )

    assert nullable.get("surface") == "T | none"


def test_runtime_schema_projection_requires_an_expected_type() -> None:
    """
    title: Dynamic projection records a checked expected element type.
    """
    operations = load_operations()
    projection = next(
        item for item in operations if item.get("id") == "core-project-field"
    )

    assert 'value.column<T>("field")' in str(projection.get("surface"))


def test_native_ownership_primitives_remain_compiler_only() -> None:
    """
    title: Retain and release primitives are not public Arx operations.
    """
    operations = load_operations()
    ownership = next(
        item for item in operations if item.get("id") == "core-ownership"
    )

    assert ownership.get("placement") == "internal_runtime"
    assert ownership.get("module") == "internal"
    assert ownership.get("visibility") == "compiler_only"


def test_recoverable_errors_have_a_builtin_result_type() -> None:
    """
    title: Recoverable native failures use an ambient typed result value.
    """
    operations = load_operations()
    result_type = next(
        item for item in operations if item.get("id") == "type-result-error"
    )

    assert result_type.get("surface") == "result[T, data_error]"
    assert result_type.get("placement") == "compiler_builtin_type"
    assert result_type.get("module") == "ambient"


def test_native_distribution_uses_dedicated_runtime_wheels() -> None:
    """
    title: Production native builds do not depend on PyArrow libraries.
    """
    distribution = load_distribution()

    assert distribution.get("strategy") == "dedicated_runtime_wheels"
    assert distribution.get("core_package") == "arx-arrowcpp-runtime"
    assert (
        distribution.get("pyarrow_role")
        == "optional_arxpy_interop_and_test_bootstrap"
    )
    assert (
        distribution.get("compiled_output_policy")
        == "bundle_activated_libraries"
    )


def test_unified_arrow_abi_starts_at_version_one() -> None:
    """
    title: The unified ABI has one stable prefix and compatibility rule.
    """
    abi = load_abi_contract()

    assert (abi.get("major"), abi.get("minor"), abi.get("patch")) == (1, 0, 0)
    assert abi.get("symbol_prefix") == "irx_arrow_"
    assert abi.get("legacy_prefixes") == ["irx_rb_"]
    assert abi.get("compatibility") == "same_major_runtime_minor_gte_consumer"


def test_upstream_arrow_modules_have_explicit_product_scope() -> None:
    """
    title: Arrow 24 module groups cover every approved product scope.
    """
    modules = load_modules()
    identifiers = [item.get("id") for item in modules]
    classifications = {item.get("classification") for item in modules}

    assert len(identifiers) == EXPECTED_MODULE_COUNT
    assert len(identifiers) == len(set(identifiers))
    assert classifications == EXPECTED_MODULE_CLASSIFICATIONS
    for item in modules:
        public_module = item.get("public_module")
        assert isinstance(public_module, str)
        assert "arrow" not in {
            part.lower() for part in public_module.split(".")
        }


def test_generated_arrow_capability_matrix_is_current() -> None:
    """
    title: The generated matrix matches its manifest and dependency pins.
    """
    completed = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
