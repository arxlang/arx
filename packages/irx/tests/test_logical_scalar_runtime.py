"""
title: Logical scalar builders, C Data interchange and failure atomicity.
"""

from __future__ import annotations

import ctypes

from collections.abc import Iterator
from decimal import Decimal

import pyarrow as pa
import pytest

from .test_array_value_runtime import export_array
from .test_arrow_runtime import (
    ArrowSchemaStruct,
    BufferViewStruct,
    _assert_arrow_ok,
    _load_arrow_runtime_library,
    _release_c_schema,
)
from .test_tabular_runtime import import_batch


@pytest.fixture(scope="module")
def runtime() -> Iterator[ctypes.CDLL]:
    """
    title: Reuse the runtime with allocation failure injection enabled.
    returns:
      type: Iterator[ctypes.CDLL]
    """
    with _load_arrow_runtime_library(failure_injection=True) as library:
        yield library


def type_owner(lib: ctypes.CDLL, type_: pa.DataType) -> ctypes.c_void_p:
    """
    title: Import a checked logical descriptor without consuming the exporter.
    parameters:
      lib:
        type: ctypes.CDLL
      type_:
        type: pa.DataType
    returns:
      type: ctypes.c_void_p
    """
    schema = ArrowSchemaStruct()
    pa.field("", type_, nullable=False)._export_to_c(ctypes.addressof(schema))
    result = ctypes.c_void_p()
    try:
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_type_import_copy(
                ctypes.byref(schema), ctypes.byref(result)
            ),
        )
    finally:
        _release_c_schema(schema)
    return result


@pytest.mark.parametrize(
    "type_,text,expected",
    [
        *[
            (factory(), b"1", 1)
            for factory in (
                pa.int8,
                pa.int16,
                pa.int32,
                pa.int64,
                pa.uint8,
                pa.uint16,
                pa.uint32,
                pa.uint64,
            )
        ],
        *[
            (factory(), b"1.5", 1.5)
            for factory in (
                pa.float16,
                pa.float32,
                pa.float64,
            )
        ],
        (pa.bool_(), b"true", True),
        (pa.string(), b"hello", "hello"),
        (pa.large_string(), "λ".encode(), "λ"),
        (pa.string_view(), b"", ""),
        (pa.binary(), b"abc", b"abc"),
        (pa.large_binary(), b"abc", b"abc"),
        (pa.binary_view(), b"abc", b"abc"),
        (pa.binary(3), b"abc", b"abc"),
        (pa.decimal32(6, 2), b"12.34", Decimal("12.34")),
        (pa.decimal64(12, 2), b"12.34", Decimal("12.34")),
        (pa.decimal128(25, 2), b"12.34", Decimal("12.34")),
        (pa.decimal256(50, 2), b"12.34", Decimal("12.34")),
        (pa.date32(), b"2024-01-02", None),
        (pa.date64(), b"2024-01-02", None),
        (pa.time32("s"), b"12:34:56", None),
        (pa.time64("us"), b"12:34:56.123456", None),
        (pa.timestamp("ns", "UTC"), b"2024-01-02T03:04:05Z", None),
        (pa.duration("us"), b"123", None),
    ],
)
def test_scalar_builder_roundtrip(
    runtime: ctypes.CDLL, type_: pa.DataType, text: bytes, expected: object
) -> None:
    """
    title: Preserve logical array nulls, offsets and child lifetimes.
    parameters:
      runtime:
        type: ctypes.CDLL
      type_:
        type: pa.DataType
      text:
        type: bytes
      expected:
        type: object
    """
    lib = runtime
    descriptor = type_owner(lib, type_)
    scalar, builder, array, child, copy = (ctypes.c_void_p() for _ in range(5))
    try:
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_scalar_parse(descriptor, text, ctypes.byref(scalar)),
        )
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_array_builder_new_logical(
                descriptor, ctypes.byref(builder)
            ),
        )
        _assert_arrow_ok(
            lib, lib.irx_arrow_type_release(ctypes.byref(descriptor))
        )
        _assert_arrow_ok(
            lib, lib.irx_arrow_array_builder_append_scalar(builder, scalar)
        )
        _assert_arrow_ok(
            lib, lib.irx_arrow_array_builder_append_null(builder, 1)
        )
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_array_builder_build(builder, 1, ctypes.byref(array)),
        )
        restored = export_array(lib, array)
        assert restored.type == type_
        assert restored[1].as_py() is None
        if expected is not None:
            assert restored[0].as_py() == expected
        _assert_arrow_ok(
            lib, lib.irx_arrow_array_slice(array, 0, 1, ctypes.byref(copy))
        )
        _assert_arrow_ok(
            lib, lib.irx_arrow_array_get_scalar(copy, 0, ctypes.byref(child))
        )
        _assert_arrow_ok(lib, lib.irx_arrow_array_release(ctypes.byref(array)))
        _assert_arrow_ok(lib, lib.irx_arrow_array_release(ctypes.byref(copy)))
        equal = ctypes.c_int32()
        _assert_arrow_ok(
            lib, lib.irx_arrow_scalar_equal(child, scalar, ctypes.byref(equal))
        )
        assert equal.value == 1
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_array_builder_build(builder, 0, ctypes.byref(array)),
        )
        assert len(export_array(lib, array)) == 0
    finally:
        lib.irx_arrow_type_release(ctypes.byref(descriptor))
        lib.irx_arrow_scalar_release(ctypes.byref(scalar))
        lib.irx_arrow_scalar_release(ctypes.byref(child))
        lib.irx_arrow_array_builder_release(ctypes.byref(builder))
        lib.irx_arrow_array_release(ctypes.byref(array))
        lib.irx_arrow_array_release(ctypes.byref(copy))


def test_logical_builder_failure_atomicity(
    runtime: ctypes.CDLL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Failed append and finish preserve builder data for retry.
    parameters:
      runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    lib = runtime
    descriptor = type_owner(lib, pa.string())
    scalar, builder, output = (ctypes.c_void_p() for _ in range(3))
    try:
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_scalar_parse(
                descriptor, b"value", ctypes.byref(scalar)
            ),
        )
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_array_builder_new_logical(
                descriptor, ctypes.byref(builder)
            ),
        )
        _assert_arrow_ok(
            lib, lib.irx_arrow_array_builder_append_scalar(builder, scalar)
        )
        monkeypatch.setenv(
            "IRX_ARROW_TEST_FAIL_OPERATION", "array_builder_append"
        )
        assert lib.irx_arrow_array_builder_append_scalar(builder, scalar) != 0
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_OPERATION")
        monkeypatch.setenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION", "1")
        assert (
            lib.irx_arrow_array_builder_build(builder, 0, ctypes.byref(output))
            != 0
        )
        assert not output.value
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION")
        count = ctypes.c_int64()
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_array_builder_length(builder, ctypes.byref(count)),
        )
        assert count.value == 1
        _assert_arrow_ok(
            lib,
            lib.irx_arrow_array_builder_build(
                builder, 0, ctypes.byref(output)
            ),
        )
        assert export_array(lib, output).to_pylist() == ["value"]
    finally:
        lib.irx_arrow_type_release(ctypes.byref(descriptor))
        lib.irx_arrow_scalar_release(ctypes.byref(scalar))
        lib.irx_arrow_array_builder_release(ctypes.byref(builder))
        lib.irx_arrow_array_release(ctypes.byref(output))


@pytest.mark.parametrize(
    "type_,text",
    [
        (pa.decimal32(3, 2), b"100.00"),
        (pa.decimal64(6, 2), b"1.234"),
        (pa.decimal128(10, 0), b"not-a-number"),
        (pa.binary(3), b"wrong-size"),
        (pa.string(), b"\xff"),
        (pa.string_view(), b"\xff"),
        (pa.int8(), b"128"),
    ],
)
def test_scalar_failure_clears_output(
    runtime: ctypes.CDLL, type_: pa.DataType, text: bytes
) -> None:
    """
    title: Reject invalid scalar data before publishing an owner token.
    parameters:
      runtime:
        type: ctypes.CDLL
      type_:
        type: pa.DataType
      text:
        type: bytes
    """
    descriptor = type_owner(runtime, type_)
    output = ctypes.c_void_p(1)
    try:
        assert (
            runtime.irx_arrow_scalar_parse(
                descriptor, text, ctypes.byref(output)
            )
            != 0
        )
        assert not output.value
    finally:
        runtime.irx_arrow_type_release(ctypes.byref(descriptor))


def test_logical_finish_rejects_null_without_consuming(
    runtime: ctypes.CDLL,
) -> None:
    """
    title: Nonnullable consuming finish leaves null-containing builders intact.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    descriptor = type_owner(runtime, pa.string())
    builder, output = ctypes.c_void_p(), ctypes.c_void_p(1)
    try:
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_array_builder_new_logical(
                descriptor, ctypes.byref(builder)
            ),
        )
        _assert_arrow_ok(
            runtime, runtime.irx_arrow_array_builder_append_null(builder, 1)
        )
        assert (
            runtime.irx_arrow_array_builder_finish_typed(
                ctypes.byref(builder), 0, ctypes.byref(output)
            )
            != 0
        )
        assert builder.value and not output.value
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_array_builder_finish_typed(
                ctypes.byref(builder), 1, ctypes.byref(output)
            ),
        )
        assert not builder.value
        assert export_array(runtime, output).to_pylist() == [None]
    finally:
        runtime.irx_arrow_type_release(ctypes.byref(descriptor))
        runtime.irx_arrow_array_builder_release(ctypes.byref(builder))
        runtime.irx_arrow_array_release(ctypes.byref(output))


@pytest.mark.parametrize(
    "count,offset,stride,expected",
    [
        (2, 4, 8, [6, 8]),
        (2, 12, -8, [8, 6]),
        (0, 0, 4, []),
    ],
)
def test_buffer_constructor_copies_strides(
    runtime: ctypes.CDLL,
    count: int,
    offset: int,
    stride: int,
    expected: list[int],
) -> None:
    """
    title: >-
      Copy positive, negative and zero-length views independently of input.
    parameters:
      runtime:
        type: ctypes.CDLL
      count:
        type: int
      offset:
        type: int
      stride:
        type: int
      expected:
        type: list[int]
    """
    source = (ctypes.c_int32 * 4)(5, 6, 7, 8)
    shape, strides = (ctypes.c_int64 * 1)(count), (ctypes.c_int64 * 1)(stride)
    view = BufferViewStruct(
        ctypes.addressof(source) if count else None,
        None,
        4,
        1,
        shape,
        strides,
        offset,
        8,
    )
    output = ctypes.c_void_p()
    try:
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_array_from_buffer(
                1, ctypes.byref(view), ctypes.byref(output)
            ),
        )
        for index in range(4):
            source[index] = 0
        assert export_array(runtime, output).to_pylist() == expected
    finally:
        runtime.irx_arrow_array_release(ctypes.byref(output))


@pytest.mark.parametrize(
    "count,offset,stride,flags",
    [
        (2, 0, -4, 8),
        (-1, 0, 4, 8),
        (2**63 - 1, 0, 4, 8),
        (2, 2**63 - 4, 4, 8),
        (1, 0, 4, 128),
    ],
)
def test_buffer_constructor_rejects_invalid_layout(
    runtime: ctypes.CDLL, count: int, offset: int, stride: int, flags: int
) -> None:
    """
    title: Reject invalid dimensions, overflow and bitmap storage before reads.
    parameters:
      runtime:
        type: ctypes.CDLL
      count:
        type: int
      offset:
        type: int
      stride:
        type: int
      flags:
        type: int
    """
    source = ctypes.c_int32(3)
    shape, strides = (ctypes.c_int64 * 1)(count), (ctypes.c_int64 * 1)(stride)
    view = BufferViewStruct(
        ctypes.addressof(source), None, 4, 1, shape, strides, offset, flags
    )
    output = ctypes.c_void_p(1)
    assert (
        runtime.irx_arrow_array_from_buffer(
            1, ctypes.byref(view), ctypes.byref(output)
        )
        != 0
    )
    assert not output.value


def test_scalar_array_copy_detaches_dictionary(runtime: ctypes.CDLL) -> None:
    """
    title: Explicit nested copies detach dictionary buffers as well as indices.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    dictionary = pa.array(["one", "two"])
    source = pa.DictionaryArray.from_arrays(
        pa.array([0, 1], type=pa.int8()), dictionary
    )
    batch = import_batch(runtime, pa.record_batch([source], names=["value"]))
    schema = ArrowSchemaStruct()
    pa.field("value", source.type)._export_to_c(ctypes.addressof(schema))
    field, column, copied = (ctypes.c_void_p() for _ in range(3))
    try:
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_field_import_copy(
                ctypes.byref(schema), ctypes.byref(field)
            ),
        )
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_batch_column_checked(
                batch, 0, field, ctypes.byref(column)
            ),
        )
        _assert_arrow_ok(
            runtime, runtime.irx_arrow_array_copy(column, ctypes.byref(copied))
        )
        restored = export_array(runtime, copied)
        assert restored.equals(source)
        assert (
            restored.dictionary.buffers()[1].address
            != dictionary.buffers()[1].address
        )
        assert (
            restored.indices.buffers()[1].address
            != source.indices.buffers()[1].address
        )
    finally:
        _release_c_schema(schema)
        runtime.irx_arrow_field_release(ctypes.byref(field))
        runtime.irx_arrow_array_release(ctypes.byref(column))
        runtime.irx_arrow_array_release(ctypes.byref(copied))
        runtime.irx_arrow_record_batch_release(ctypes.byref(batch))


def test_builder_checks_nested_metadata(runtime: ctypes.CDLL) -> None:
    """
    title: Logical builder equality includes recursive field metadata.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    left = type_owner(
        runtime,
        pa.struct([pa.field("x", pa.int32(), metadata={b"unit": b"left"})]),
    )
    right = type_owner(
        runtime,
        pa.struct([pa.field("x", pa.int32(), metadata={b"unit": b"right"})]),
    )
    integer = type_owner(runtime, pa.int32())
    child, scalar, builder = (ctypes.c_void_p() for _ in range(3))
    try:
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_scalar_parse(integer, b"1", ctypes.byref(child)),
        )
        children = (ctypes.c_void_p * 1)(child)
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_scalar_from_fields(
                left, children, 1, ctypes.byref(scalar)
            ),
        )
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_array_builder_new_logical(
                right, ctypes.byref(builder)
            ),
        )
        assert (
            runtime.irx_arrow_array_builder_append_scalar(builder, scalar) != 0
        )
        length = ctypes.c_int64(-1)
        _assert_arrow_ok(
            runtime,
            runtime.irx_arrow_array_builder_length(
                builder, ctypes.byref(length)
            ),
        )
        assert length.value == 0
    finally:
        for descriptor in (left, right, integer):
            runtime.irx_arrow_type_release(ctypes.byref(descriptor))
        runtime.irx_arrow_scalar_release(ctypes.byref(child))
        runtime.irx_arrow_scalar_release(ctypes.byref(scalar))
        runtime.irx_arrow_array_builder_release(ctypes.byref(builder))
