"""
title: Owned external C Data, exact bitmap bounds and failure-safe publication.
"""

import ctypes

import pyarrow as pa
import pytest

from .test_array_value_runtime import export_array
from .test_arrow_runtime import (
    ArrowArrayStruct,
    ArrowSchemaStruct,
    _capsule_pointer,
    _release_c_schema,
)
from .test_logical_scalar_runtime import runtime  # noqa: F401

TYPE_MISMATCH = 103
OUT_OF_MEMORY = 200
INVALID_ARGUMENT = 100


def import_bytes(lib: ctypes.CDLL, values: list[int]) -> ctypes.c_void_p:
    """
    title: Copy bounded nonnullable byte arrays into a native owner.
    parameters:
      lib:
        type: ctypes.CDLL
      values:
        type: list[int]
    returns:
      type: ctypes.c_void_p
    """
    schema, array = pa.array(values, type=pa.uint8()).__arrow_c_array__()
    result = ctypes.c_void_p()
    assert (
        lib.irx_arrow_array_import_copy(
            _capsule_pointer(array, b"arrow_array"),
            _capsule_pointer(schema, b"arrow_schema"),
            ctypes.byref(result),
        )
        == 0
    )
    return result


def field_owner(lib: ctypes.CDLL, field: pa.Field) -> ctypes.c_void_p:
    """
    title: Import a complete expected field with immutable native ownership.
    parameters:
      lib:
        type: ctypes.CDLL
      field:
        type: pa.Field
    returns:
      type: ctypes.c_void_p
    """
    schema = ArrowSchemaStruct()
    field._export_to_c(ctypes.addressof(schema))
    result = ctypes.c_void_p()
    try:
        assert (
            lib.irx_arrow_field_import_copy(
                ctypes.byref(schema), ctypes.byref(result)
            )
            == 0
        )
    finally:
        _release_c_schema(schema)
    return result


@pytest.mark.parametrize(
    "source",
    [
        pa.array(["discard", "λ", None]).slice(1),
        pa.array([[1, None], None, []]),
        pa.array([], type=pa.bool_()),
        pa.array(["a", "b", "a"]).dictionary_encode(),
    ],
)
def test_external_c_data_owner(runtime: ctypes.CDLL, source: pa.Array) -> None:
    """
    title: Consume callbacks once and retain metadata and values past parents.
    parameters:
      runtime:
        type: ctypes.CDLL
      source:
        type: pa.Array
    """
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(array))
    expected = pa.field(
        "payload", source.type, metadata={b"origin": b"\0\xff"}
    )
    expected._export_to_c(ctypes.addressof(schema))
    owner, result = ctypes.c_void_p(), ctypes.c_void_p()
    field = field_owner(runtime, expected)
    try:
        assert (
            runtime.irx_arrow_c_data_import_move(
                ctypes.byref(array), ctypes.byref(schema), ctypes.byref(owner)
            )
            == 0
        )
        assert not array.release and not schema.release
        assert (
            runtime.irx_arrow_c_data_export(
                owner, ctypes.byref(array), ctypes.byref(schema)
            )
            == 0
        )
        restored_field = pa.Field._import_from_c(ctypes.addressof(schema))
        restored = pa.Array._import_from_c(
            ctypes.addressof(array), restored_field.type
        )
        assert restored_field.equals(expected, check_metadata=True)
        assert restored.equals(source)
        assert (
            runtime.irx_arrow_array_from_c_data(
                owner, field, ctypes.byref(result)
            )
            == 0
        )
        assert runtime.irx_arrow_c_data_release(ctypes.byref(owner)) == 0
        assert export_array(runtime, result).equals(source)
    finally:
        if array.release:
            ctypes.CFUNCTYPE(None, ctypes.POINTER(ArrowArrayStruct))(
                array.release
            )(ctypes.byref(array))
        _release_c_schema(schema)
        runtime.irx_arrow_c_data_release(ctypes.byref(owner))
        runtime.irx_arrow_array_release(ctypes.byref(result))
        runtime.irx_arrow_field_release(ctypes.byref(field))


def test_packed_buffers_and_error_outputs(runtime: ctypes.CDLL) -> None:
    """
    title: Check packed offsets, short buffers, overflow and nullability.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    field = field_owner(runtime, pa.field("", pa.bool_()))
    required = field_owner(runtime, pa.field("", pa.bool_(), nullable=False))
    data, bitmap = import_bytes(runtime, [10]), import_bytes(runtime, [6])
    output = ctypes.c_void_p()
    try:
        assert (
            runtime.irx_arrow_array_from_buffers(
                field, data, bitmap, 3, 1, ctypes.byref(output)
            )
            == 0
        )
        assert export_array(runtime, output).to_pylist() == [True, False, None]
        runtime.irx_arrow_array_release(ctypes.byref(output))
        for length, offset, expected in [
            (9, 0, 100),
            (2**63 - 1, 1, 106),
            (-1, 0, 106),
        ]:
            output.value = 1
            assert (
                runtime.irx_arrow_array_from_buffers(
                    field, data, bitmap, length, offset, ctypes.byref(output)
                )
                == expected
            )
            assert output.value is None
        assert (
            runtime.irx_arrow_array_from_buffers(
                required, data, bitmap, 3, 1, ctypes.byref(output)
            )
            == TYPE_MISMATCH
        )
        assert output.value is None
        assert (
            runtime.irx_arrow_array_with_validity(
                data, bitmap, 8, ctypes.byref(output)
            )
            == INVALID_ARGUMENT
        )
        assert output.value is None
    finally:
        runtime.irx_arrow_field_release(ctypes.byref(field))
        runtime.irx_arrow_field_release(ctypes.byref(required))
        for owner in (data, bitmap, output):
            runtime.irx_arrow_array_release(ctypes.byref(owner))


def test_import_move_preflight_failure_preserves_producer(
    runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Failed owner reservation leaves producer callbacks reusable.
    parameters:
      runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    pa.array([1, 2])._export_to_c(
        ctypes.addressof(array), ctypes.addressof(schema)
    )
    output = ctypes.c_void_p(1)
    try:
        monkeypatch.setenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION", "1")
        assert (
            runtime.irx_arrow_c_data_import_move(
                ctypes.byref(array), ctypes.byref(schema), ctypes.byref(output)
            )
            == OUT_OF_MEMORY
        )
        assert not output.value and array.release and schema.release
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION")
        assert (
            runtime.irx_arrow_c_data_import_move(
                ctypes.byref(array), ctypes.byref(schema), ctypes.byref(output)
            )
            == 0
        )
        assert not array.release and not schema.release
    finally:
        if array.release:
            ctypes.CFUNCTYPE(None, ctypes.POINTER(ArrowArrayStruct))(
                array.release
            )(ctypes.byref(array))
        _release_c_schema(schema)
        runtime.irx_arrow_c_data_release(ctypes.byref(output))


def test_import_move_post_reservation_failure_consumes_both(
    runtime: ctypes.CDLL,
) -> None:
    """
    title: A malformed schema after reservation consumes both callbacks once.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    pa.array([1])._export_to_c(
        ctypes.addressof(array), ctypes.addressof(schema)
    )
    schema.format = b"invalid-format"
    output = ctypes.c_void_p(1)
    assert (
        runtime.irx_arrow_c_data_import_move(
            ctypes.byref(array), ctypes.byref(schema), ctypes.byref(output)
        )
        != 0
    )
    assert not output.value and not array.release and not schema.release


def test_buffer_copy_allocation_failures_are_atomic(
    runtime: ctypes.CDLL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Byte/bitmap copying clears failed outputs and permits a clean retry.
    parameters:
      runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    field = field_owner(runtime, pa.field("", pa.bool_()))
    data = import_bytes(runtime, [7])
    bitmap = import_bytes(runtime, [5])
    output = ctypes.c_void_p(1)
    try:
        for variable in (
            "IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION",
            "IRX_ARROW_TEST_FAIL_POOL_ALLOCATION",
        ):
            monkeypatch.setenv(variable, "1")
            assert (
                runtime.irx_arrow_array_from_buffers(
                    field, data, bitmap, 3, 0, ctypes.byref(output)
                )
                == OUT_OF_MEMORY
            )
            assert not output.value
            monkeypatch.delenv(variable)
        assert (
            runtime.irx_arrow_array_from_buffers(
                field, data, bitmap, 3, 0, ctypes.byref(output)
            )
            == 0
        )
        assert export_array(runtime, output).to_pylist() == [True, None, True]
    finally:
        runtime.irx_arrow_field_release(ctypes.byref(field))
        for owner in (data, bitmap, output):
            runtime.irx_arrow_array_release(ctypes.byref(owner))
