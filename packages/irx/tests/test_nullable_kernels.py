"""
title: Nullable native ABI status, overflow, validity and lifetime contracts.
"""

import ctypes
import math
import struct

from typing import get_args

import pyarrow as pa
import pytest

from irx.builder.runtime.arrow_compute import (
    COMPUTE_ABI_VERSION,
    COMPUTE_SIGNATURES,
)
from irx.builtins.collections.array_primitives import (
    ARRAY_PRIMITIVE_TYPE_SPECS,
)
from irx.native import COMPUTE_CATALOG, ComputeKernel

from .test_arrow_interop import import_batch, native  # noqa: F401
from .test_arrow_math_contract import (
    FINITE,
    SPECIAL,
    assert_result,
    decimal_reference,
)
from .test_dataframe_conversion import import_schema

IRX_ERR_OVERFLOW = -8
IRX_ERR_DIVZERO = -9


def bind_kernels(native: ctypes.CDLL) -> None:
    """
    title: Declare the exact scalar/column ABI for ctypes callers.
    parameters:
      native:
        type: ctypes.CDLL
    """
    pointer = ctypes.c_void_p
    types = {
        "v": None,
        "p": pointer,
        "pp": ctypes.POINTER(pointer),
        "i32": ctypes.c_int32,
        "i64": ctypes.c_uint64,
        "i32p": ctypes.POINTER(ctypes.c_int32),
        "i64p": ctypes.POINTER(ctypes.c_uint64),
    }
    for name, signature in COMPUTE_SIGNATURES.items():
        function = getattr(native, name)
        function.restype = types[signature[0]]
        function.argtypes = [types[item] for item in signature[1:]]
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


@pytest.mark.parametrize("kernel", get_args(ComputeKernel))
def test_versioned_math_abi(
    native: ctypes.CDLL, kernel: ComputeKernel
) -> None:
    """
    title: Reuse independent scalar oracles through the two-kernel native ABI.
    parameters:
      native:
        type: ctypes.CDLL
      kernel:
        type: ComputeKernel
    """
    bind_kernels(native)
    assert native.irx_arrow_compute_abi_version() == COMPUTE_ABI_VERSION
    operation = COMPUTE_CATALOG[kernel].operation_id
    assert (
        native.irx_arrow_compute_supports(2, operation, 1, 0, 12, 1, 12) == 0
    )
    vectors = [
        (arguments, decimal_reference(kernel, arguments))
        for arguments in FINITE[kernel]
    ] + list(SPECIAL[kernel])
    for (value,), expected in vectors:
        payload = (
            0x7FF0000000000001  # Invalid (signaling NaN) payload is ignored.
            if value is None
            else struct.unpack("=Q", struct.pack("=d", value))[0]
        )
        column = ctypes.c_void_p(123)
        bits, valid = ctypes.c_uint64(123), ctypes.c_int32(123)
        assert (
            native.irx_arrow_compute(
                2,
                operation,
                1,
                0,
                12,
                1,
                12,
                None,
                payload,
                int(value is not None),
                0,
                None,
                0,
                0,
                12,
                ctypes.byref(column),
                ctypes.byref(bits),
                ctypes.byref(valid),
            )
            == 0
        )
        assert column.value is None
        actual = (
            struct.unpack("=d", struct.pack("=Q", bits.value))[0]
            if valid.value
            else None
        )
        assert_result(kernel, pa.scalar(actual, type=pa.float64()), expected)
        if not valid.value:
            assert bits.value == 0


@pytest.mark.parametrize("kernel", get_args(ComputeKernel))
@pytest.mark.parametrize("rows", [[], [None, None], [0.0, None, 4.0]])
def test_math_series_ownership(
    native: ctypes.CDLL, kernel: ComputeKernel, rows: list[float | None]
) -> None:
    """
    title: Owned compute results survive release of borrowed input and parents.
    parameters:
      native:
        type: ctypes.CDLL
      kernel:
        type: ComputeKernel
      rows:
        type: list[float | None]
    """
    bind_kernels(native)
    values = pa.array([99.0, *rows], type=pa.float64()).slice(1)
    batch = pa.record_batch([values], names=["x"])
    handle = import_batch(native, batch)
    schema = import_schema(native, batch.schema)
    table, column, result = (ctypes.c_void_p() for _ in range(3))
    bits, valid = ctypes.c_uint64(123), ctypes.c_int32(123)
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
        assert (
            native.irx_arrow_compute(
                2,
                COMPUTE_CATALOG[kernel].operation_id,
                1,
                0,
                12,
                2,
                12,
                column,
                0,
                0,
                0,
                None,
                0,
                0,
                12,
                ctypes.byref(result),
                ctypes.byref(bits),
                ctypes.byref(valid),
            )
            == 0
        )
        assert result.value and (bits.value, valid.value) == (0, 0)
        assert native.irx_arrow_chunked_array_retain(result) == 0
        native.irx_arrow_chunked_array_release(result)
    finally:
        native.irx_arrow_chunked_array_release(column)
    try:
        for index, value in enumerate(rows):
            assert (
                native.irx_arrow_series_index(
                    result, index, 10, ctypes.byref(bits), ctypes.byref(valid)
                )
                == 0
            )
            actual = struct.unpack("=d", struct.pack("=Q", bits.value))[0]
            expected = (
                None if value is None else decimal_reference(kernel, (value,))
            )
            assert_result(
                kernel,
                pa.scalar(actual if valid.value else None, type=pa.float64()),
                expected,
            )
    finally:
        native.irx_arrow_chunked_array_release(result)


@pytest.mark.parametrize(
    "abi,operation,arity,options,dtype,shape,column,bits,valid,status",
    [
        (3, 1, 1, 0, 12, 2, 1, 0, 0, -6),  # ABI before pointer access.
        (2, 999, 1, 0, 12, 1, None, 0, 1, -6),
        (2, 1, 2, 0, 12, 1, None, 0, 1, -6),
        (2, 1, 1, 1, 12, 1, None, 0, 1, -6),
        (2, 1, 1, 0, 10, 1, None, 0, 1, -4),  # Legacy ID is not f64.
        (2, 1, 1, 0, 12, 3, None, 0, 1, -4),
        (2, 1, 1, 0, 12, 1, None, 0, 2, -4),
        (2, 1, 1, 0, 12, 1, 1, 0, 1, -4),
        (2, 1, 1, 0, 12, 2, None, 0, 0, -4),
    ],
)
def test_math_abi_fail_closed(
    native: ctypes.CDLL,
    abi: int,
    operation: int,
    arity: int,
    options: int,
    dtype: int,
    shape: int,
    column: int | None,
    bits: int,
    valid: int,
    status: int,
) -> None:
    """
    title: Reject unsupported descriptors and clear poison outputs.
    parameters:
      native:
        type: ctypes.CDLL
      abi:
        type: int
      operation:
        type: int
      arity:
        type: int
      options:
        type: int
      dtype:
        type: int
      shape:
        type: int
      column:
        type: int | None
      bits:
        type: int
      valid:
        type: int
      status:
        type: int
    """
    bind_kernels(native)
    output = ctypes.c_void_p(123)
    out_bits, out_valid = ctypes.c_uint64(123), ctypes.c_int32(123)
    assert (
        native.irx_arrow_compute(
            abi,
            operation,
            arity,
            options,
            dtype,
            shape,
            dtype,
            column,
            bits,
            valid,
            0,
            None,
            0,
            0,
            12,
            ctypes.byref(output),
            ctypes.byref(out_bits),
            ctypes.byref(out_valid),
        )
        == status
    )
    assert (output.value, out_bits.value, out_valid.value) == (None, 0, 0)


def invoke_compute(
    native: ctypes.CDLL,
    kernel: bytes,
    storage_id: int,
    lhs: ctypes.c_void_p | None,
    lhs_bits: int,
    lhs_valid: int,
    rhs: ctypes.c_void_p | None,
    rhs_bits: int,
    rhs_valid: int,
    output: object,
    bits: object,
    valid: object,
) -> int:
    """
    title: Run existing storage/index vectors through the typed compute ABI.
    parameters:
      native:
        type: ctypes.CDLL
      kernel:
        type: bytes
      storage_id:
        type: int
      lhs:
        type: ctypes.c_void_p | None
      lhs_bits:
        type: int
      lhs_valid:
        type: int
      rhs:
        type: ctypes.c_void_p | None
      rhs_bits:
        type: int
      rhs_valid:
        type: int
      output:
        type: object
      bits:
        type: object
      valid:
        type: object
    returns:
      type: int
    """
    capability = COMPUTE_CATALOG.get(kernel.decode())
    primitive = next(
        (
            pa.type_for_alias(spec.name)
            for spec in ARRAY_PRIMITIVE_TYPE_SPECS.values()
            if spec.type_id == storage_id
        ),
        None,
    )
    dtype = primitive.id if primitive is not None else storage_id
    arity = capability.arity if capability else 2
    binary = arity != 1
    result_kind = capability.result if capability else "SAME"
    reduction = result_kind in {
        "SUM",
        "MINMAX",
        "MEAN",
        "COUNT",
        "BOOL_REDUCE",
    }
    result_dtype = {
        "BOOL": pa.bool_().id,
        "BOOL_REDUCE": pa.bool_().id,
        "COUNT": pa.int64().id,
        "MEAN": pa.float64().id,
    }.get(result_kind, dtype)
    if result_kind == "SUM":
        assert primitive is not None
        if pa.types.is_integer(primitive):
            result_dtype = (
                pa.uint64().id
                if pa.types.is_unsigned_integer(primitive)
                else pa.int64().id
            )
        else:
            result_dtype = pa.float64().id
    return int(
        native.irx_arrow_compute(
            COMPUTE_ABI_VERSION,
            capability.operation_id if capability else 0,
            arity,
            0,
            dtype,
            1 if reduction or not (lhs or rhs) else 2,
            dtype,
            lhs,
            lhs_bits,
            0 if lhs else lhs_valid,
            dtype if binary else 0,
            rhs if binary else None,
            rhs_bits if binary else 0,
            (0 if rhs else rhs_valid) if binary else 0,
            result_dtype,
            output,
            bits,
            valid,
        )
    )


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
    status = invoke_compute(
        native,
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
    assert status == IRX_ERR_OVERFLOW and bits == 0 and valid == 0
    assert compute(native, b"add_checked", type_id, maximum, 1, False) == (
        0,
        0,
        0,
    )
    assert (
        compute(native, b"divide_checked", type_id, 1, 0)[0] == IRX_ERR_DIVZERO
    )
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
    status = invoke_compute(
        native,
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
            invoke_compute(
                native,
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


@pytest.mark.parametrize(
    "floating,empty", [(False, False), (True, False), (False, True)]
)
def test_sequence_snapshot_chunked_nulls_and_replacement(
    native: ctypes.CDLL, floating: bool, empty: bool
) -> None:
    """
    title: >-
      Snapshots retain chunk buffers and validity across source replacement.
    summary: >-
      IPC batches deliberately preserve multiple chunks. NaN/Inf are values,
      not nulls; large integer bits survive without an intermediate float.
    parameters:
      native:
        type: ctypes.CDLL
      floating:
        type: bool
      empty:
        type: bool
    """
    bind_kernels(native)
    pointer = ctypes.c_void_p
    native.irx_arrow_table_from_ipc.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int64,
        ctypes.POINTER(pointer),
    ]
    native.irx_arrow_table_from_ipc.restype = ctypes.c_int
    native.irx_arrow_sequence_snapshot.argtypes = [
        pointer,
        ctypes.POINTER(pointer),
    ]
    native.irx_arrow_sequence_snapshot.restype = ctypes.c_int
    native.irx_arrow_sequence_length.argtypes = [pointer]
    native.irx_arrow_sequence_length.restype = ctypes.c_int64
    native.irx_arrow_sequence_read.argtypes = (
        native.irx_arrow_series_index.argtypes
    )
    native.irx_arrow_sequence_read.restype = ctypes.c_int
    native.irx_arrow_series_set.argtypes = [
        pointer,
        ctypes.c_int64,
        ctypes.c_int32,
        ctypes.c_uint64,
        ctypes.c_int32,
        ctypes.c_int32,
    ]
    native.irx_arrow_series_set.restype = ctypes.c_int
    type_ = pa.float64() if floating else pa.int64()
    type_id = 10 if floating else 4
    values = (
        [float("nan"), None, float("inf"), -float("inf")]
        if floating
        else [2**53 + 1, None, 2**63 - 1, -(2**63)]
    )
    if empty:
        values = []
    schema = pa.schema([pa.field("x", type_)])
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        for chunk in (values[:2], values[2:]):
            writer.write_batch(
                pa.record_batch([pa.array(chunk, type=type_)], schema=schema)
            )
    payload = sink.getvalue().to_pybytes()
    table, column, snapshot = pointer(), pointer(), pointer()
    assert (
        native.irx_arrow_table_from_ipc(
            payload, len(payload), ctypes.byref(table)
        )
        == 0
    )
    assert (
        native.irx_arrow_table_column_by_index(table, 0, ctypes.byref(column))
        == 0
    )
    assert (
        native.irx_arrow_sequence_snapshot(column, ctypes.byref(snapshot)) == 0
    )
    assert native.irx_arrow_sequence_length(snapshot) == len(values)
    # Update one alias after taking the snapshot, then discard every source.
    if values:
        assert native.irx_arrow_series_set(column, 0, type_id, 0, 1, 1) == 0
    native.irx_arrow_chunked_array_release(column)
    native.irx_arrow_table_release(table)
    try:
        bits, valid = ctypes.c_uint64(77), ctypes.c_int32(77)
        for index, value in enumerate(values):
            assert (
                native.irx_arrow_sequence_read(
                    snapshot,
                    index,
                    type_id,
                    ctypes.byref(bits),
                    ctypes.byref(valid),
                )
                == 0
            )
            assert valid.value == int(value is not None)
            if value is None:
                assert bits.value == 0
            elif floating:
                actual = struct.unpack("d", struct.pack("Q", bits.value))[0]
                if math.isnan(value):
                    assert math.isnan(actual)
                else:
                    assert actual == value
            else:
                assert bits.value == int(value) % (2**64)
        for index in (-1, len(values)):
            bits.value = valid.value = 77
            assert (
                native.irx_arrow_sequence_read(
                    snapshot,
                    index,
                    type_id,
                    ctypes.byref(bits),
                    ctypes.byref(valid),
                )
                != 0
            )
            assert (bits.value, valid.value) == (0, 0)
    finally:
        native.irx_arrow_chunked_array_release(snapshot)
    snapshot.value = 77
    assert (
        native.irx_arrow_sequence_snapshot(None, ctypes.byref(snapshot)) != 0
    )
    assert snapshot.value is None
