"""
title: Arrow ABI manifest tests.
"""

from __future__ import annotations

import json

from pathlib import Path
from typing import cast

RUNTIME_ROOT = (
    Path(__file__).parents[1] / "src" / "irx" / "builder" / "runtime" / "arrow"
)
ABI_MANIFEST_PATH = RUNTIME_ROOT / "abi.json"
ABI_HEADER_PATH = RUNTIME_ROOT / "native" / "irx_arrow_runtime.h"
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
