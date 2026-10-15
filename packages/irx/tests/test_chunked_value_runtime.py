"""
title: Native builder reset, chunk shape, bounds and independent ownership.
"""

from __future__ import annotations

import ctypes

from collections.abc import Iterator

import pyarrow as pa
import pytest

from .test_array_value_runtime import export_array
from .test_arrow_runtime import (
    ARROW_STATUS_INVALID_ARGUMENT,
    ARROW_STATUS_OVERFLOW,
    ARROW_STATUS_TYPE_MISMATCH,
    _load_arrow_runtime_library,
)


@pytest.fixture(scope="module")
def runtime() -> Iterator[ctypes.CDLL]:
    """
    title: Compile one native library for the chunk and builder contract.
    returns:
      type: Iterator[ctypes.CDLL]
    """
    with _load_arrow_runtime_library() as library:
        yield library


def test_builder_finish_reset_and_recovery(runtime: ctypes.CDLL) -> None:
    """
    title: Reset only successful finishes and preserve nullability failures.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    b, a = ctypes.c_void_p(), ctypes.c_void_p()
    length = ctypes.c_int64(-1)
    try:
        assert runtime.irx_arrow_array_builder_new(1, ctypes.byref(b)) == 0
        assert (
            runtime.irx_arrow_array_builder_reserve(b, -1)
            == ARROW_STATUS_INVALID_ARGUMENT
        )
        assert runtime.irx_arrow_array_builder_append_null(b, 1) == 0
        assert (
            runtime.irx_arrow_array_builder_build(b, 0, ctypes.byref(a))
            == ARROW_STATUS_TYPE_MISMATCH
        )
        assert a.value is None
        assert (
            runtime.irx_arrow_array_builder_length(b, ctypes.byref(length))
            == 0
        )
        assert length.value == 1
        assert (
            runtime.irx_arrow_array_builder_build(b, 1, ctypes.byref(a)) == 0
        )
        assert export_array(runtime, a).to_pylist() == [None]
        assert runtime.irx_arrow_array_release(ctypes.byref(a)) == 0
        assert (
            runtime.irx_arrow_array_builder_length(b, ctypes.byref(length))
            == 0
        )
        assert length.value == 0
        assert (
            runtime.irx_arrow_array_builder_build(b, 0, ctypes.byref(a)) == 0
        )
        assert export_array(runtime, a).to_pylist() == []
        assert runtime.irx_arrow_array_builder_append_int(b, 42) == 0
        assert (
            runtime.irx_arrow_array_builder_reserve(b, 2**63 - 1)
            == ARROW_STATUS_OVERFLOW
        )
    finally:
        runtime.irx_arrow_array_release(ctypes.byref(a))
        runtime.irx_arrow_array_builder_release(ctypes.byref(b))


def test_chunk_views_outlive_all_parents(runtime: ctypes.CDLL) -> None:
    """
    title: Slice across chunks and retain both children and exported buffers.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    builder, first, second, chunks, sliced, child, combined = (
        ctypes.c_void_p() for _ in range(7)
    )
    try:
        assert (
            runtime.irx_arrow_array_builder_new(1, ctypes.byref(builder)) == 0
        )
        for number in (1, 2):
            assert (
                runtime.irx_arrow_array_builder_append_int(builder, number)
                == 0
            )
        assert (
            runtime.irx_arrow_array_builder_build(
                builder, 1, ctypes.byref(first)
            )
            == 0
        )
        assert runtime.irx_arrow_array_builder_append_null(builder, 1) == 0
        assert runtime.irx_arrow_array_builder_append_int(builder, 4) == 0
        assert (
            runtime.irx_arrow_array_builder_build(
                builder, 1, ctypes.byref(second)
            )
            == 0
        )
        values = (ctypes.c_void_p * 2)(first.value, second.value)
        assert (
            runtime.irx_arrow_chunked_new(
                1, 1, values, 2, ctypes.byref(chunks)
            )
            == 0
        )
        assert (
            runtime.irx_arrow_chunked_slice(chunks, 1, 3, ctypes.byref(sliced))
            == 0
        )
        assert (
            runtime.irx_arrow_chunked_chunk(sliced, 0, ctypes.byref(child))
            == 0
        )
        assert (
            runtime.irx_arrow_chunked_combine(sliced, ctypes.byref(combined))
            == 0
        )
        exported = export_array(runtime, combined)
        assert runtime.irx_arrow_array_release(ctypes.byref(first)) == 0
        assert runtime.irx_arrow_array_release(ctypes.byref(second)) == 0
        assert (
            runtime.irx_arrow_chunked_array_release(ctypes.byref(chunks)) == 0
        )
        assert (
            runtime.irx_arrow_chunked_array_release(ctypes.byref(sliced)) == 0
        )
        assert export_array(runtime, child).to_pylist() == [2]
        assert exported.equals(pa.array([2, None, 4], type=pa.int32()))
        assert runtime.irx_arrow_array_release(ctypes.byref(combined)) == 0
        assert exported.to_pylist() == [2, None, 4]
    finally:
        runtime.irx_arrow_array_builder_release(ctypes.byref(builder))
        for owner in (first, second, child, combined):
            runtime.irx_arrow_array_release(ctypes.byref(owner))
        for owner in (chunks, sliced):
            runtime.irx_arrow_chunked_array_release(ctypes.byref(owner))
