"""
title: Arrow ABI manifest tests.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys

from pathlib import Path
from typing import cast

from irx.builder.runtime.array.feature import build_array_runtime_feature
from irx.builder.runtime.arrow.abi_generated import (
    ABI_SYMBOLS,
    CTYPES_SIGNATURES,
    FEATURE_SYMBOLS,
    RUNTIME_FEATURE_IDS,
    RUNTIME_FEATURE_PACKED_VERSIONS,
    RUNTIME_FEATURE_VERSIONS,
)
from irx.builder.runtime.arrow.llvm_abi_generated import (
    LLVM_RUNTIME_FEATURE_IDS,
    LLVM_RUNTIME_FEATURE_VERSIONS,
    LLVM_SIGNATURES,
)
from irx.builder.runtime.dataframe.feature import (
    build_dataframe_runtime_feature,
)
from irx.builder.runtime.record_batch import (
    RECORD_BATCH_SYMBOLS,
    build_record_batch_runtime_feature,
)
from irx.builder.runtime.tensor.feature import build_tensor_runtime_feature

REPOSITORY_ROOT = Path(__file__).parents[3]
RUNTIME_ROOT = (
    Path(__file__).parents[1] / "src" / "irx" / "builder" / "runtime" / "arrow"
)
ABI_MANIFEST_PATH = RUNTIME_ROOT / "abi.json"
ABI_HEADER_PATH = RUNTIME_ROOT / "native" / "irx_arrow_abi_generated.h"
ABI_WRAPPER_PATH = RUNTIME_ROOT / "native" / "irx_arrow_runtime.h"
ABI_SOURCE_PATH = RUNTIME_ROOT / "native" / "irx_arrow_runtime.cc"
ABI_SYMBOLS_PATH = RUNTIME_ROOT / "symbols.generated.txt"
EXPECTED_HANDLE_NAMES = (
    "error",
    "type",
    "schema",
    "scalar",
    "array_builder",
    "array",
    "chunked_array",
    "record_batch",
    "table",
    "tensor_builder",
    "tensor",
    "stream",
    "dataset",
    "execution_plan",
)
EXPECTED_RUNTIME_FEATURES = {
    "core": 1,
    "array": 2,
    "tensor": 3,
    "dataframe": 4,
    "record_batch": 5,
}


def _load_handles() -> list[dict[str, object]]:
    """
    title: Load handle records from the Arrow ABI manifest.
    returns:
      type: list[dict[str, object]]
    """
    manifest = cast(
        dict[str, object],
        json.loads(ABI_MANIFEST_PATH.read_text(encoding="utf-8")),
    )
    assert manifest["abi_version"] == "1.0.0"
    return cast(list[dict[str, object]], manifest["handles"])


def _load_runtime_features() -> list[dict[str, object]]:
    """
    title: Load runtime-feature records from the Arrow ABI manifest.
    returns:
      type: list[dict[str, object]]
    """
    manifest = cast(
        dict[str, object],
        json.loads(ABI_MANIFEST_PATH.read_text(encoding="utf-8")),
    )
    return cast(
        list[dict[str, object]],
        manifest["runtime_features"],
    )


def test_arrow_abi_manifest_defines_stable_opaque_handle_kinds() -> None:
    """
    title: Every planned opaque handle should have one stable kind.
    """
    handles = _load_handles()
    header = ABI_HEADER_PATH.read_text(encoding="utf-8")

    assert [record["id"] for record in handles] == list(
        range(1, len(handles) + 1)
    )
    assert tuple(record["name"] for record in handles) == (
        EXPECTED_HANDLE_NAMES
    )
    assert len({record["name"] for record in handles}) == len(handles)
    assert len({record["c_type"] for record in handles}) == len(handles)

    for record in handles:
        handle_id = cast(int, record["id"])
        name = cast(str, record["name"])
        c_type = cast(str, record["c_type"])
        enum_name = name.upper()
        assert f"IRX_ARROW_HANDLE_KIND_{enum_name} = {handle_id}" in header
        assert f"typedef struct {c_type} {c_type};" in header


def test_arrow_abi_manifest_defines_ownership_contracts() -> None:
    """
    title: Handle ownership should determine retain and release operations.
    """
    handles = _load_handles()
    header = ABI_HEADER_PATH.read_text(encoding="utf-8")

    for record in handles:
        ownership = record["ownership"]
        retain = record["retain"]
        release = record["release"]
        availability = cast(str, record["availability"])

        assert ownership in {"shared", "unique"}
        assert record["thread_safety"] in {
            "immutable_shared",
            "thread_confined",
        }
        assert isinstance(release, str) and release
        if ownership == "shared":
            assert isinstance(retain, str) and retain
        else:
            assert retain is None

        if availability == "implemented":
            assert release in header
            if retain is not None:
                assert retain in header
        else:
            assert availability.startswith("planned_m")


def test_arrow_abi_manifest_defines_versioned_runtime_features() -> None:
    """
    title: Runtime-feature IDs and contract versions should have exact parity.
    """
    features = _load_runtime_features()
    header = ABI_HEADER_PATH.read_text(encoding="utf-8")

    assert {
        cast(str, feature["name"]): cast(int, feature["id"])
        for feature in features
    } == EXPECTED_RUNTIME_FEATURES
    assert all(feature["contract_version"] == "1.0.0" for feature in features)
    assert all(
        feature["availability"] == "implemented" for feature in features
    )
    assert RUNTIME_FEATURE_IDS == EXPECTED_RUNTIME_FEATURES
    assert RUNTIME_FEATURE_VERSIONS == {
        name: (1, 0, 0) for name in EXPECTED_RUNTIME_FEATURES
    }
    assert RUNTIME_FEATURE_PACKED_VERSIONS == {
        name: 0x00010000 for name in EXPECTED_RUNTIME_FEATURES
    }
    assert LLVM_RUNTIME_FEATURE_IDS == RUNTIME_FEATURE_IDS
    assert LLVM_RUNTIME_FEATURE_VERSIONS == (RUNTIME_FEATURE_PACKED_VERSIONS)

    for name, feature_id in EXPECTED_RUNTIME_FEATURES.items():
        prefix = f"IRX_ARROW_RUNTIME_FEATURE_{name.upper()}"
        assert f"{prefix} = {feature_id}" in header
        assert f"{prefix}_CONTRACT_VERSION" in header


def test_arrow_abi_generated_outputs_are_current() -> None:
    """
    title: Generated ABI declarations should match the checked-in manifest.
    """
    result = subprocess.run(
        [sys.executable, "scripts/gen_arrow_abi.py", "--check"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_arrow_abi_declaration_sets_have_exact_symbol_parity() -> None:
    """
    title: C, Python, LLVM, and symbol declarations should have exact parity.
    """
    header = ABI_HEADER_PATH.read_text(encoding="utf-8")
    source = ABI_SOURCE_PATH.read_text(encoding="utf-8")
    wrapper = ABI_WRAPPER_PATH.read_text(encoding="utf-8")
    inventory = tuple(
        ABI_SYMBOLS_PATH.read_text(encoding="utf-8").splitlines()
    )
    header_symbols = tuple(
        re.findall(r"\b(irx_arrow_[a-z0-9_]+)\s*\(", header)
    )
    source_symbols = tuple(
        re.findall(
            r"^(?:const\s+)?(?:char|int64_t)\*\s+"
            r"(irx_arrow_[a-z0-9_]+)\s*\("
            r"|^(?:uint32_t|int32_t|int64_t|void|irx_arrow_status|"
            r"irx_arrow_status_category)\s+"
            r"(irx_arrow_[a-z0-9_]+)\s*\(",
            source,
            flags=re.MULTILINE,
        )
    )
    flattened_source_symbols = tuple(
        first or second for first, second in source_symbols
    )

    assert '#include "irx_arrow_abi_generated.h"' in wrapper
    assert header_symbols == ABI_SYMBOLS
    assert inventory == ABI_SYMBOLS
    assert set(flattened_source_symbols) == set(ABI_SYMBOLS)
    assert len(flattened_source_symbols) == len(ABI_SYMBOLS)
    assert tuple(CTYPES_SIGNATURES) == ABI_SYMBOLS
    assert CTYPES_SIGNATURES == LLVM_SIGNATURES


def test_arrow_runtime_features_use_generated_symbol_tables() -> None:
    """
    title: Runtime features should use only their generated ABI symbols.
    """
    features = {
        "array": build_array_runtime_feature(),
        "tensor": build_tensor_runtime_feature(),
        "dataframe": build_dataframe_runtime_feature(),
    }

    for name, feature in features.items():
        assert tuple(feature.symbols) == FEATURE_SYMBOLS[name]

    record_batch = build_record_batch_runtime_feature()
    assert set(FEATURE_SYMBOLS["record_batch"]).issubset(record_batch.symbols)
    assert RECORD_BATCH_SYMBOLS.issubset(record_batch.symbols)
    assert record_batch.metadata["compatibility_prefix"] == "irx_rb_"
    assert record_batch.metadata["removal_abi_major"] == 2  # noqa: PLR2004


def test_fallible_generated_declarations_use_explicit_error_outputs() -> None:
    """
    title: Every fallible generated declaration should own its error output.
    """
    infallible = {
        "irx_arrow_abi_version",
        "irx_arrow_status_get_category",
        "irx_arrow_tensor_release_callback",
        "irx_arrow_last_error",
    }

    for name, (return_type, parameters) in CTYPES_SIGNATURES.items():
        if name in infallible:
            assert not parameters or parameters[-1] != "error_pointer"
            continue
        assert return_type == "status"
        assert parameters[-1] == "error_pointer"
