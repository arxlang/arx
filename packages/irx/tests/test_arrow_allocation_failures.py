"""
title: Real Arrow allocation failures preserve caller-owned state.
"""

from __future__ import annotations

import ctypes
import subprocess

from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest

from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import compile_native_artifacts

from .test_arrow_runtime import (
    BUILDER_CASES,
    IRX_ARROW_TYPE_INT32,
    ArrowArrayStruct,
    ArrowSchemaStruct,
    _arrow_runtime_feature,
    _assert_arrow_ok,
    _import_exported_array,
    _load_arrow_runtime_library,
    _pyarrow_c_array,
)

POOL_FAILURE = "IRX_ARROW_TEST_FAIL_POOL_ALLOCATION"
OUT_OF_MEMORY = 200
OVERFLOW = 106
GROWTH_NULL_COUNT = 512
PRIMITIVES = [(case[0], case[1], case[2]) for case in BUILDER_CASES]


@pytest.fixture(scope="module")
def failure_runtime() -> Iterator[ctypes.CDLL]:
    """
    title: Share one test-only runtime across allocation regressions.
    returns:
      type: Iterator[ctypes.CDLL]
    """
    with _load_arrow_runtime_library(failure_injection=True) as library:
        yield library


def export_values(
    library: ctypes.CDLL, array: ctypes.c_void_p
) -> list[object]:
    """
    title: Read a live runtime array using the standard C Data bridge.
    parameters:
      library:
        type: ctypes.CDLL
      array:
        type: ctypes.c_void_p
    returns:
      type: list[object]
    """
    c_array, c_schema = ArrowArrayStruct(), ArrowSchemaStruct()
    _assert_arrow_ok(
        library,
        library.irx_arrow_array_export(
            array, ctypes.byref(c_array), ctypes.byref(c_schema)
        ),
    )
    return _import_exported_array(c_array, c_schema).to_pylist()


@pytest.mark.parametrize(("name", "type_id", "kind"), PRIMITIVES)
@pytest.mark.parametrize("failure_index", [0, 1])
def test_first_append_pool_failure_is_retryable(
    failure_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    type_id: int,
    kind: str,
    failure_index: int,
) -> None:
    """
    title: Partial value/validity allocation leaves logical length unchanged.
    parameters:
      failure_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
      name:
        type: str
      type_id:
        type: int
      kind:
        type: str
      failure_index:
        type: int
    """
    library = failure_runtime
    builder, array = ctypes.c_void_p(), ctypes.c_void_p()
    _assert_arrow_ok(
        library,
        library.irx_arrow_array_builder_new(type_id, ctypes.byref(builder)),
    )
    append = getattr(library, f"irx_arrow_array_builder_append_{kind}")
    try:
        monkeypatch.setenv(POOL_FAILURE, str(failure_index))
        assert append(builder, 1) == OUT_OF_MEMORY
        monkeypatch.delenv(POOL_FAILURE)
        _assert_arrow_ok(library, append(builder, 1))
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_finish(
                ctypes.byref(builder), ctypes.byref(array)
            ),
        )
        assert export_values(library, array) == [True if name == "bool" else 1]
    finally:
        library.irx_arrow_array_builder_release(ctypes.byref(builder))
        library.irx_arrow_array_release(ctypes.byref(array))


@pytest.mark.parametrize(("name", "type_id", "kind"), PRIMITIVES)
@pytest.mark.parametrize("failure_index", [0, 1])
def test_finish_pool_failure_preserves_values_and_nulls(
    failure_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    type_id: int,
    kind: str,
    failure_index: int,
) -> None:
    """
    title: Retry a failed finish after appending more values to the owner.
    parameters:
      failure_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
      name:
        type: str
      type_id:
        type: int
      kind:
        type: str
      failure_index:
        type: int
    """
    library = failure_runtime
    builder, array = ctypes.c_void_p(), ctypes.c_void_p()
    _assert_arrow_ok(
        library,
        library.irx_arrow_array_builder_new(type_id, ctypes.byref(builder)),
    )
    append = getattr(library, f"irx_arrow_array_builder_append_{kind}")
    try:
        _assert_arrow_ok(library, append(builder, 1))
        _assert_arrow_ok(
            library, library.irx_arrow_array_builder_append_null(builder, 1)
        )
        original = builder.value
        array.value = 123
        monkeypatch.setenv(POOL_FAILURE, str(failure_index))
        assert (
            library.irx_arrow_array_builder_finish(
                ctypes.byref(builder), ctypes.byref(array)
            )
            == OUT_OF_MEMORY
        )
        assert array.value is None
        assert builder.value == original
        monkeypatch.delenv(POOL_FAILURE)
        _assert_arrow_ok(library, append(builder, 0))
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_finish(
                ctypes.byref(builder), ctypes.byref(array)
            ),
        )
        expected = [True, None, False] if name == "bool" else [1, None, 0]
        assert export_values(library, array) == expected
    finally:
        library.irx_arrow_array_builder_release(ctypes.byref(builder))
        library.irx_arrow_array_release(ctypes.byref(array))


@pytest.mark.parametrize("failure_index", [0, 1])
def test_null_growth_pool_failure_preserves_existing_values(
    failure_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
    failure_index: int,
) -> None:
    """
    title: Reallocation failure preserves a nonempty builder and its bitmap.
    parameters:
      failure_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
      failure_index:
        type: int
    """
    library = failure_runtime
    builder, array = ctypes.c_void_p(), ctypes.c_void_p()
    _assert_arrow_ok(
        library,
        library.irx_arrow_array_builder_new(
            IRX_ARROW_TYPE_INT32, ctypes.byref(builder)
        ),
    )
    try:
        _assert_arrow_ok(
            library, library.irx_arrow_array_builder_append_int(builder, 7)
        )
        monkeypatch.setenv(POOL_FAILURE, str(failure_index))
        assert (
            library.irx_arrow_array_builder_append_null(
                builder, GROWTH_NULL_COUNT
            )
            == OUT_OF_MEMORY
        )
        monkeypatch.delenv(POOL_FAILURE)
        assert (
            library.irx_arrow_array_builder_append_null(builder, 2**63 - 1)
            == OVERFLOW
        )
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_append_null(
                builder, GROWTH_NULL_COUNT
            ),
        )
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_finish(
                ctypes.byref(builder), ctypes.byref(array)
            ),
        )
        assert export_values(library, array) == [
            7,
            *([None] * GROWTH_NULL_COUNT),
        ]
    finally:
        library.irx_arrow_array_builder_release(ctypes.byref(builder))
        library.irx_arrow_array_release(ctypes.byref(array))


@pytest.mark.parametrize("failure_index", [0, 1])
def test_copy_import_pool_failure_does_not_consume_c_data(
    failure_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
    failure_index: int,
) -> None:
    """
    title: Failed import frees temporary buffers and preserves producer data.
    parameters:
      failure_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
      failure_index:
        type: int
    """
    library = failure_runtime
    source = _pyarrow_c_array([7, None, 9], pa.int32())
    c_schema = ArrowSchemaStruct.from_address(source[3])
    c_array = ArrowArrayStruct.from_address(source[4])
    releases = c_array.release, c_schema.release
    array = ctypes.c_void_p(123)
    try:
        monkeypatch.setenv(POOL_FAILURE, str(failure_index))
        assert (
            library.irx_arrow_array_import_copy(
                source[4], source[3], ctypes.byref(array)
            )
            == OUT_OF_MEMORY
        )
        assert array.value is None
        assert (c_array.release, c_schema.release) == releases
        monkeypatch.delenv(POOL_FAILURE)
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_import_copy(
                source[4], source[3], ctypes.byref(array)
            ),
        )
        assert export_values(library, array) == source[0].to_pylist()
    finally:
        library.irx_arrow_array_release(ctypes.byref(array))


def test_production_runtime_ignores_pool_failure_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test allocator controls must not affect production artifacts.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.setenv(POOL_FAILURE, "0")
    with _load_arrow_runtime_library() as library:
        builder, array = ctypes.c_void_p(), ctypes.c_void_p()
        try:
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_builder_new(
                    IRX_ARROW_TYPE_INT32, ctypes.byref(builder)
                ),
            )
            _assert_arrow_ok(
                library, library.irx_arrow_array_builder_append_int(builder, 1)
            )
            _assert_arrow_ok(
                library,
                library.irx_arrow_array_builder_finish(
                    ctypes.byref(builder), ctypes.byref(array)
                ),
            )
        finally:
            library.irx_arrow_array_builder_release(ctypes.byref(builder))
            library.irx_arrow_array_release(ctypes.byref(array))


@pytest.mark.parametrize("null_count", [0, 3])
def test_empty_and_all_null_finish_retries(
    failure_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
    null_count: int,
) -> None:
    """
    title: Empty and all-null owners remain releasable after failed finish.
    parameters:
      failure_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
      null_count:
        type: int
    """
    library = failure_runtime
    builder, array = ctypes.c_void_p(), ctypes.c_void_p()
    _assert_arrow_ok(
        library,
        library.irx_arrow_array_builder_new(
            IRX_ARROW_TYPE_INT32, ctypes.byref(builder)
        ),
    )
    try:
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_append_null(builder, null_count),
        )
        monkeypatch.setenv(POOL_FAILURE, "0")
        assert (
            library.irx_arrow_array_builder_finish(
                ctypes.byref(builder), ctypes.byref(array)
            )
            == OUT_OF_MEMORY
        )
        assert array.value is None and builder.value is not None
        monkeypatch.delenv(POOL_FAILURE)
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_finish(
                ctypes.byref(builder), ctypes.byref(array)
            ),
        )
        assert export_values(library, array) == [None] * null_count
    finally:
        library.irx_arrow_array_builder_release(ctypes.byref(builder))
        library.irx_arrow_array_release(ctypes.byref(array))


def test_tensor_pool_failure_does_not_publish_partial_builder(
    failure_runtime: ctypes.CDLL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Tensor storage allocation fails before publication and can retry.
    parameters:
      failure_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    library = failure_runtime
    shape = (ctypes.c_int64 * 1)(2)
    builder = ctypes.c_void_p(123)
    try:
        monkeypatch.setenv(POOL_FAILURE, "0")
        assert (
            library.irx_arrow_tensor_builder_new(
                IRX_ARROW_TYPE_INT32, 1, shape, None, ctypes.byref(builder)
            )
            == OUT_OF_MEMORY
        )
        assert builder.value is None
        monkeypatch.delenv(POOL_FAILURE)
        _assert_arrow_ok(
            library,
            library.irx_arrow_tensor_builder_new(
                IRX_ARROW_TYPE_INT32, 1, shape, None, ctypes.byref(builder)
            ),
        )
    finally:
        library.irx_arrow_tensor_builder_release(ctypes.byref(builder))


def test_cpp_allocation_failure_sweep(tmp_path: Path) -> None:
    """
    title: Fail C++ finish and descriptor import allocations and retry.
    parameters:
      tmp_path:
        type: Path
    """
    feature = _arrow_runtime_feature()
    harness = NativeArtifact(
        kind="cxx_source",
        path=Path(__file__).parent / "native" / "arrow_allocation_failures.cc",
        include_dirs=feature.artifacts[0].include_dirs,
        compile_flags=("-std=c++20",),
    )
    inputs = compile_native_artifacts((*feature.artifacts, harness), tmp_path)
    executable = tmp_path / "allocation_failures"
    subprocess.run(
        [
            "c++",
            *(str(path) for path in inputs.objects),
            *inputs.linker_flags,
            *feature.linker_flags,
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [str(executable)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("failure_index", [0, 1])
def test_reusable_finish_pool_failure_preserves_builder(
    failure_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
    failure_index: int,
) -> None:
    """
    title: Snapshot finish keeps reusable builder data intact until success.
    parameters:
      failure_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
      failure_index:
        type: int
    """
    library = failure_runtime
    builder, array = ctypes.c_void_p(), ctypes.c_void_p()
    _assert_arrow_ok(
        library,
        library.irx_arrow_array_builder_new(
            IRX_ARROW_TYPE_INT32, ctypes.byref(builder)
        ),
    )
    try:
        _assert_arrow_ok(
            library, library.irx_arrow_array_builder_append_int(builder, 7)
        )
        _assert_arrow_ok(
            library, library.irx_arrow_array_builder_append_null(builder, 1)
        )
        original = builder.value
        monkeypatch.setenv(POOL_FAILURE, str(failure_index))
        assert (
            library.irx_arrow_array_builder_build(
                builder, 1, ctypes.byref(array)
            )
            == OUT_OF_MEMORY
        )
        assert array.value is None
        assert builder.value == original
        monkeypatch.delenv(POOL_FAILURE)
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_build(
                builder, 1, ctypes.byref(array)
            ),
        )
        assert export_values(library, array) == [7, None]
        length = ctypes.c_int64(-1)
        _assert_arrow_ok(
            library,
            library.irx_arrow_array_builder_length(
                builder, ctypes.byref(length)
            ),
        )
        assert length.value == 0
    finally:
        library.irx_arrow_array_builder_release(ctypes.byref(builder))
        library.irx_arrow_array_release(ctypes.byref(array))
