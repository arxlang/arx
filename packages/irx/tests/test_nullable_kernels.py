"""
title: Nullable native ABI status, overflow, validity and lifetime contracts.
"""

import ctypes
import struct

import pyarrow as pa
import pytest

from .test_arrow_interop import import_batch, native  # noqa: F401
from .test_dataframe_conversion import import_schema


def bind_kernels(native: ctypes.CDLL) -> None:
    """
    title: Declare the exact scalar/column ABI for ctypes callers.
    parameters:
      native:
        type: ctypes.CDLL
    """
    pointer = ctypes.c_void_p
    native.irx_arrow_column_compute.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int32,
        pointer,
        ctypes.c_uint64,
        ctypes.c_int32,
        pointer,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.POINTER(pointer),
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int32),
    ]
    native.irx_arrow_column_compute.restype = ctypes.c_int
    native.irx_arrow_series_index.argtypes = [
        pointer,
        ctypes.c_int64,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_int32),
    ]
    native.irx_arrow_series_index.restype = ctypes.c_int
    native.irx_arrow_table_column_by_index.argtypes = [
        pointer,
        ctypes.c_int32,
        ctypes.POINTER(pointer),
    ]
    native.irx_arrow_table_column_by_index.restype = ctypes.c_int
    for name in ("irx_arrow_table_release", "irx_arrow_chunked_array_release"):
        getattr(native, name).argtypes = [pointer]
        getattr(native, name).restype = None


def compute(
    native: ctypes.CDLL,
    kernel: bytes,
    type_id: int,
    left: int,
    right: int,
    left_valid: bool = True,
    right_valid: bool = True,
) -> tuple[int, int, int]:
    """
    title: Invoke a scalar kernel and return status plus defined output slots.
    parameters:
      native:
        type: ctypes.CDLL
      kernel:
        type: bytes
      type_id:
        type: int
      left:
        type: int
      right:
        type: int
      left_valid:
        type: bool
      right_valid:
        type: bool
    returns:
      type: tuple[int, int, int]
    """
    bind_kernels(native)
    output = ctypes.c_void_p(123)
    bits, valid = ctypes.c_uint64(123), ctypes.c_int32(123)
    status = native.irx_arrow_column_compute(
        kernel,
        type_id,
        None,
        left,
        int(left_valid),
        None,
        right,
        int(right_valid),
        ctypes.byref(output),
        ctypes.byref(bits),
        ctypes.byref(valid),
    )
    assert output.value is None
    return status, bits.value, valid.value


@pytest.mark.parametrize(
    "type_id,width,signed",
    [
        (1, 32, True),
        (2, 8, True),
        (3, 16, True),
        (4, 64, True),
        (5, 8, False),
        (6, 16, False),
        (7, 32, False),
        (8, 64, False),
    ],
)
def test_integer_kernels(
    native: ctypes.CDLL, type_id: int, width: int, signed: bool
) -> None:
    """
    title: Checked arithmetic preserves every signed and unsigned width.
    parameters:
      native:
        type: ctypes.CDLL
      type_id:
        type: int
      width:
        type: int
      signed:
        type: bool
    """
    assert compute(native, b"add_checked", type_id, 2, 3) == (0, 5, 1)
    maximum = 2 ** (width - int(signed)) - 1
    status, bits, valid = compute(native, b"add_checked", type_id, maximum, 1)
    assert status != 0 and bits == 0 and valid == 0
    assert compute(native, b"add_checked", type_id, maximum, 1, False) == (
        0,
        0,
        0,
    )
    assert compute(native, b"divide_checked", type_id, 1, 0)[0] != 0
    assert compute(native, b"divide_checked", type_id, 1, 0, False) == (
        0,
        0,
        0,
    )
    assert compute(native, b"coalesce", type_id, 0, maximum, False) == (
        0,
        maximum,
        1,
    )
    expected_negative = -2
    if signed:
        status, bits, valid = compute(
            native, b"subtract_checked", type_id, 1, 3
        )
        assert (
            status == 0
            and ctypes.c_int64(bits).value == expected_negative
            and valid == 1
        )
        assert (
            compute(
                native,
                b"divide_checked",
                type_id,
                1 << (width - 1),
                (1 << width) - 1,
            )[0]
            != 0
        )


@pytest.mark.parametrize("type_id,format_", [(9, "f"), (10, "d")])
def test_float_kernels(
    native: ctypes.CDLL, type_id: int, format_: str
) -> None:
    """
    title: Floating bit transport does not numerically convert or truncate.
    parameters:
      native:
        type: ctypes.CDLL
      type_id:
        type: int
      format_:
        type: str
    """
    left = int.from_bytes(struct.pack("<" + format_, 1.5), "little")
    right = int.from_bytes(struct.pack("<" + format_, 2.0), "little")
    expected = int.from_bytes(struct.pack("<" + format_, 3.5), "little")
    assert compute(native, b"add_checked", type_id, left, right) == (
        0,
        expected,
        1,
    )
    assert compute(native, b"less", type_id, left, right) == (0, 1, 1)
    assert compute(
        native, b"equal", type_id, left, right, right_valid=False
    ) == (0, 0, 0)


def test_boolean_masks_and_fail_closed(native: ctypes.CDLL) -> None:
    """
    title: >-
      Strict boolean null propagation and invalid kernels fail predictably.
    parameters:
      native:
        type: ctypes.CDLL
    """
    assert compute(native, b"and", 11, 0, 1, right_valid=False) == (0, 0, 0)
    assert compute(native, b"is_null", 11, 0, 0, False) == (0, 1, 1)
    assert compute(native, b"not_a_kernel", 1, 1, 1)[0] != 0
    assert compute(native, b"add_checked", -1, 1, 1)[0] != 0


@pytest.mark.parametrize("missing", ["column", "bits", "valid"])
def test_missing_compute_outputs(native: ctypes.CDLL, missing: str) -> None:
    """
    title: Clear all provided outputs even when a required output is absent.
    parameters:
      native:
        type: ctypes.CDLL
      missing:
        type: str
    """
    bind_kernels(native)
    column = ctypes.c_void_p(123)
    bits, valid = ctypes.c_uint64(123), ctypes.c_int32(123)
    status = native.irx_arrow_column_compute(
        b"add_checked",
        1,
        None,
        1,
        1,
        None,
        1,
        1,
        None if missing == "column" else ctypes.byref(column),
        None if missing == "bits" else ctypes.byref(bits),
        None if missing == "valid" else ctypes.byref(valid),
    )
    assert status != 0
    if missing != "column":
        assert column.value is None
    if missing != "bits":
        assert bits.value == 0
    if missing != "valid":
        assert valid.value == 0


@pytest.mark.parametrize("missing", ["bits", "valid"])
def test_missing_index_outputs(native: ctypes.CDLL, missing: str) -> None:
    """
    title: Invalid output arguments cannot leave stale scalar payloads.
    parameters:
      native:
        type: ctypes.CDLL
      missing:
        type: str
    """
    bind_kernels(native)
    bits, valid = ctypes.c_uint64(123), ctypes.c_int32(123)
    status = native.irx_arrow_series_index(
        None,
        0,
        1,
        None if missing == "bits" else ctypes.byref(bits),
        None if missing == "valid" else ctypes.byref(valid),
    )
    assert status != 0
    if missing != "bits":
        assert bits.value == 0
    if missing != "valid":
        assert valid.value == 0


@pytest.mark.parametrize("rows", [[], [1, None, 3], [None, None]])
def test_series_index_lifetime(
    native: ctypes.CDLL, rows: list[int | None]
) -> None:
    """
    title: Column references outlive sources; invalid indices clear outputs.
    parameters:
      native:
        type: ctypes.CDLL
      rows:
        type: list[int | None]
    """
    bind_kernels(native)
    batch = pa.record_batch([pa.array(rows, type=pa.int32())], names=["x"])
    handle = import_batch(native, batch)
    schema = import_schema(native, batch.schema)
    table, column = ctypes.c_void_p(), ctypes.c_void_p()
    assert (
        native.irx_rb_batch_to_table(handle, schema, ctypes.byref(table)) == 0
    )
    assert (
        native.irx_arrow_table_column_by_index(table, 0, ctypes.byref(column))
        == 0
    )
    native.irx_rb_batch_release(handle)
    native.irx_rb_schema_release(schema)
    native.irx_arrow_table_release(table)
    try:
        bits, valid = ctypes.c_uint64(), ctypes.c_int32()
        for index, value in enumerate(rows):
            assert (
                native.irx_arrow_series_index(
                    column, index, 1, ctypes.byref(bits), ctypes.byref(valid)
                )
                == 0
            )
            assert bits.value == (value or 0) and valid.value == int(
                value is not None
            )
        doubled = ctypes.c_void_p()
        assert (
            native.irx_arrow_column_compute(
                b"add_checked",
                1,
                column,
                0,
                1,
                column,
                0,
                1,
                ctypes.byref(doubled),
                ctypes.byref(bits),
                ctypes.byref(valid),
            )
            == 0
        )
        try:
            for index, value in enumerate(rows):
                assert (
                    native.irx_arrow_series_index(
                        doubled,
                        index,
                        1,
                        ctypes.byref(bits),
                        ctypes.byref(valid),
                    )
                    == 0
                )
                assert bits.value == (0 if value is None else value * 2)
                assert valid.value == int(value is not None)
        finally:
            native.irx_arrow_chunked_array_release(doubled)
        for index in (-1, len(rows)):
            bits.value, valid.value = 123, 123
            assert (
                native.irx_arrow_series_index(
                    column, index, 1, ctypes.byref(bits), ctypes.byref(valid)
                )
                != 0
            )
            assert bits.value == 0 and valid.value == 0
        assert (
            native.irx_arrow_series_index(
                column, 0, 8, ctypes.byref(bits), ctypes.byref(valid)
            )
            != 0
        )
    finally:
        native.irx_arrow_chunked_array_release(column)


def test_schema_ipc_contract(native: ctypes.CDLL) -> None:
    """
    title: IPC schema imports own descriptors and reject malformed input.
    parameters:
      native:
        type: ctypes.CDLL
    """
    native.irx_rb_schema_from_ipc.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int64,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    native.irx_rb_schema_from_ipc.restype = ctypes.c_int
    schema = pa.schema([pa.field("x", pa.decimal128(12, 3))])
    payload = schema.serialize().to_pybytes()
    output = ctypes.c_void_p()
    assert (
        native.irx_rb_schema_from_ipc(
            payload, len(payload), ctypes.byref(output)
        )
        == 0
    )
    native.irx_rb_schema_release(output)
    for bad in (b"", b"not ipc", payload[:12]):
        output.value = 123
        assert (
            native.irx_rb_schema_from_ipc(bad, len(bad), ctypes.byref(output))
            != 0
        )
        assert output.value is None


@pytest.mark.parametrize("parent_null", [False, True])
def test_nested_required_fields(
    native: ctypes.CDLL, parent_null: bool
) -> None:
    """
    title: Required nested values reject nulls unless a null parent masks them.
    parameters:
      native:
        type: ctypes.CDLL
      parent_null:
        type: bool
    """
    type_ = pa.list_(pa.field("item", pa.int32(), nullable=False))
    values = [None] if parent_null else [[None]]
    batch = pa.record_batch([pa.array(values, type=type_)], names=["x"])
    source = import_batch(native, batch)
    schema = import_schema(native, batch.schema)
    table = ctypes.c_void_p(123)
    try:
        status = native.irx_rb_batch_to_table(
            source, schema, ctypes.byref(table)
        )
        if parent_null:
            assert status == 0
            bind_kernels(native)
            native.irx_arrow_table_release(table)
        else:
            assert status != 0 and table.value is None
    finally:
        native.irx_rb_schema_release(schema)
        native.irx_rb_batch_release(source)
