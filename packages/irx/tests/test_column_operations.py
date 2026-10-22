"""
title: Native extended Series kernels and failure-atomic element updates.
"""

import ctypes

from collections.abc import Iterator
from contextlib import contextmanager

import pyarrow as pa
import pytest

from .test_arrow_interop import import_batch, native  # noqa: F401
from .test_dataframe_conversion import import_schema
from .test_nullable_kernels import bind_kernels, compute


@contextmanager
def owned_column(
    native: ctypes.CDLL, values: list[int | None], type_: pa.DataType
) -> Iterator[ctypes.c_void_p]:
    """
    title: >-
      Retain only a column after releasing imported batch and table owners.
    parameters:
      native:
        type: ctypes.CDLL
      values:
        type: list[int | None]
      type_:
        type: pa.DataType
    returns:
      type: Iterator[ctypes.c_void_p]
    """
    bind_kernels(native)
    batch = pa.record_batch([pa.array(values, type=type_)], names=["x"])
    source, schema = (
        import_batch(native, batch),
        import_schema(native, batch.schema),
    )
    table, column = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        assert (
            native.irx_rb_batch_to_table(source, schema, ctypes.byref(table))
            == 0
        )
        assert (
            native.irx_arrow_table_column_by_index(
                table, 0, ctypes.byref(column)
            )
            == 0
        )
    finally:
        native.irx_rb_batch_release(source)
        native.irx_rb_schema_release(schema)
        native.irx_arrow_table_release(table)
    try:
        yield column
    finally:
        native.irx_arrow_chunked_array_release(column)


def read_value(
    native: ctypes.CDLL, column: ctypes.c_void_p, index: int, type_id: int = 1
) -> int | None:
    """
    title: Decode a successful checked scalar access.
    parameters:
      native:
        type: ctypes.CDLL
      column:
        type: ctypes.c_void_p
      index:
        type: int
      type_id:
        type: int
    returns:
      type: int | None
    """
    bits, valid = ctypes.c_uint64(), ctypes.c_int32()
    assert (
        native.irx_arrow_series_index(
            column, index, type_id, ctypes.byref(bits), ctypes.byref(valid)
        )
        == 0
    )
    return ctypes.c_int64(bits.value).value if valid.value else None


@pytest.mark.parametrize(
    "bounds",
    [
        (None, None, -1),
        (None, None, 2),
        (-100, 100, 1),
        (100, -100, -2),
        (2, 1, 1),
        (None, None, -(2**63)),
        (None, None, 2**63 - 1),
    ],
)
@pytest.mark.parametrize("rows", [[], [1, None, 3, 4]])
def test_native_slices(
    native: ctypes.CDLL,
    bounds: tuple[int | None, int | None, int],
    rows: list[int | None],
) -> None:
    """
    title: Match Python clipping and stride semantics including extreme bounds.
    parameters:
      native:
        type: ctypes.CDLL
      bounds:
        type: tuple[int | None, int | None, int]
      rows:
        type: list[int | None]
    """
    pointer = ctypes.c_void_p
    native.irx_arrow_series_slice.argtypes = [
        pointer,
        ctypes.c_int64,
        ctypes.c_int64,
        ctypes.c_int64,
        ctypes.c_int32,
        ctypes.POINTER(pointer),
    ]
    native.irx_arrow_series_slice.restype = ctypes.c_int
    start, stop, step = bounds
    mask = int(start is not None) | (int(stop is not None) << 1)
    output = pointer(123)
    with owned_column(native, rows, pa.int32()) as column:
        assert (
            native.irx_arrow_series_slice(
                column, 0, 0, 0, 0, ctypes.byref(output)
            )
            != 0
        )
        assert output.value is None
        assert (
            native.irx_arrow_series_slice(
                column, start or 0, stop or 0, step, mask, ctypes.byref(output)
            )
            == 0
        )
    try:
        expected = rows[slice(start, stop, step)]
        assert [
            read_value(native, output, i) for i in range(len(expected))
        ] == expected
    finally:
        native.irx_arrow_chunked_array_release(output)
    assert (
        native.irx_arrow_series_slice(None, 0, 0, 0, 0, ctypes.byref(output))
        != 0
    )
    assert output.value is None


def test_native_updates(native: ctypes.CDLL) -> None:
    """
    title: >-
      Bounds, type and nullability errors leave the previous column intact.
    parameters:
      native:
        type: ctypes.CDLL
    """
    native.irx_arrow_series_set.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int64,
        ctypes.c_int32,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    native.irx_arrow_series_set.restype = ctypes.c_int
    with owned_column(native, [1, None, 3], pa.int32()) as column:
        for index, type_id, valid, nullable in [
            (-1, 1, 1, 1),
            (3, 1, 1, 1),
            (0, 8, 1, 1),
            (0, 1, 0, 0),
        ]:
            assert (
                native.irx_arrow_series_set(
                    column, index, type_id, 9, valid, nullable
                )
                != 0
            )
            assert [read_value(native, column, i) for i in range(3)] == [
                1,
                None,
                3,
            ]
        assert native.irx_arrow_series_set(column, 1, 1, 9, 1, 1) == 0
        assert native.irx_arrow_series_set(column, 0, 1, 0, 0, 1) == 0
        assert [read_value(native, column, i) for i in range(3)] == [
            None,
            9,
            3,
        ]


@pytest.mark.parametrize(
    "rows,status,expected",
    [
        ([], 0, None),
        ([None], 0, None),
        ([2, None, -1], 0, 1),
        ([2**63 - 1, 1], 1, None),
        ([-(2**63), -1], 1, None),
    ],
)
def test_checked_sum(
    native: ctypes.CDLL,
    rows: list[int | None],
    status: int,
    expected: int | None,
) -> None:
    """
    title: Integer reductions skip nulls and diagnose accumulator overflow.
    parameters:
      native:
        type: ctypes.CDLL
      rows:
        type: list[int | None]
      status:
        type: int
      expected:
        type: int | None
    """
    with owned_column(native, rows, pa.int64()) as column:
        output, bits, valid = (
            ctypes.c_void_p(123),
            ctypes.c_uint64(123),
            ctypes.c_int32(123),
        )
        result = native.irx_arrow_column_compute(
            b"sum",
            4,
            column,
            0,
            1,
            None,
            0,
            0,
            ctypes.byref(output),
            ctypes.byref(bits),
            ctypes.byref(valid),
        )
        assert (result != 0) == bool(status)
        assert output.value is None
        assert bool(valid.value) == (expected is not None)
        assert bits.value == (expected or 0)


def test_checked_unary(native: ctypes.CDLL) -> None:
    """
    title: Unary numeric overflow and null propagation retain the scalar ABI.
    parameters:
      native:
        type: ctypes.CDLL
    """
    assert compute(native, b"negate_checked", 1, 2, 0) == (0, 2**64 - 2, 1)
    assert compute(native, b"negate_checked", 1, 2, 0, False) == (0, 0, 0)
    assert compute(native, b"negate_checked", 1, 1 << 31, 0)[0] != 0
    assert compute(native, b"invert", 11, 1, 0) == (0, 0, 1)


def test_ipc_literal_ownership_and_errors(native: ctypes.CDLL) -> None:
    """
    title: Literal tables own input buffers and clear outputs on malformed IPC.
    parameters:
      native:
        type: ctypes.CDLL
    """
    bind_kernels(native)
    pointer = ctypes.c_void_p
    native.irx_arrow_table_from_ipc.argtypes = [
        pointer,
        ctypes.c_int64,
        ctypes.POINTER(pointer),
    ]
    native.irx_arrow_table_from_ipc.restype = ctypes.c_int
    batch = pa.record_batch([pa.array([7], type=pa.int32())], names=["x"])
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, batch.schema) as writer:
        writer.write_batch(batch)
    payload = sink.getvalue().to_pybytes()
    buffer = ctypes.create_string_buffer(payload)
    table, column = pointer(), pointer()
    assert (
        native.irx_arrow_table_from_ipc(
            buffer, len(payload), ctypes.byref(table)
        )
        == 0
    )
    buffer.raw = bytes(len(buffer))
    try:
        assert (
            native.irx_arrow_table_column_by_index(
                table, 0, ctypes.byref(column)
            )
            == 0
        )
    finally:
        native.irx_arrow_table_release(table)
    try:
        assert read_value(native, column, 0) == batch.column(0)[0].as_py()
    finally:
        native.irx_arrow_chunked_array_release(column)
    for invalid in (b"", b"bad ipc", payload[:12]):
        table.value = 123
        assert (
            native.irx_arrow_table_from_ipc(
                invalid, len(invalid), ctypes.byref(table)
            )
            != 0
        )
        assert table.value is None
    assert native.irx_arrow_table_from_ipc(payload, len(payload), None) != 0
