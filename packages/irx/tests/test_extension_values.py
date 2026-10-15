"""
title: Native extension values preserve storage, identity and opaque metadata.
"""

import ctypes

import astx
import pyarrow as pa
import pytest

from irx.schema_interop import schema_from_pyarrow

from .test_array_value_runtime import export_array
from .test_arrow_runtime import (
    ArrowArrayStruct,
    ArrowSchemaStruct,
    _release_c_schema,
)
from .test_interchange_values import field_owner, import_bytes
from .test_logical_scalar_runtime import runtime, type_owner  # noqa: F401

TYPE_MISMATCH = 103
OUT_OF_MEMORY = 200
INVALID_ARGUMENT = 100


@pytest.mark.parametrize(
    "type_,values",
    [
        (pa.uuid(), [b"0123456789abcdef", None]),
        (pa.bool8(), [1, 0, None]),
        (pa.json_(), ["{}", None, "[]"]),
        (pa.json_(pa.large_string()), ["{}", None]),
        (pa.opaque(pa.int32(), "value", "vendor"), [1, None]),
        (pa.fixed_shape_tensor(pa.int32(), [2]), [[1, 2], None]),
    ],
)
def test_extension_array_roundtrip(
    runtime: ctypes.CDLL, type_: pa.BaseExtensionType, values: list[object]
) -> None:
    """
    title: Import extensions, inspect storage and rebuild without type erasure.
    parameters:
      runtime:
        type: ctypes.CDLL
      type_:
        type: pa.BaseExtensionType
      values:
        type: list[object]
    """
    source = pa.ExtensionArray.from_storage(
        type_, pa.array(values, type=type_.storage_type)
    )
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(array), ctypes.addressof(schema))
    token, owner, scalar, storage, wrapped, copied = (
        ctypes.c_void_p() for _ in range(6)
    )
    expected = field_owner(runtime, pa.field("", type_))
    descriptor = type_owner(runtime, type_)
    try:
        assert (
            runtime.irx_arrow_c_data_import_move(
                ctypes.byref(array), ctypes.byref(schema), ctypes.byref(token)
            )
            == 0
        )
        assert not array.release and not schema.release
        assert (
            runtime.irx_arrow_array_from_c_data(
                token, expected, ctypes.byref(owner)
            )
            == 0
        )
        assert runtime.irx_arrow_c_data_release(ctypes.byref(token)) == 0
        assert (
            runtime.irx_arrow_array_get_scalar(owner, 0, ctypes.byref(scalar))
            == 0
        )
        assert (
            runtime.irx_arrow_scalar_storage(scalar, ctypes.byref(storage))
            == 0
        )
        assert (
            runtime.irx_arrow_scalar_wrap(
                descriptor, storage, ctypes.byref(wrapped)
            )
            == 0
        )
        equal = ctypes.c_int32()
        assert (
            runtime.irx_arrow_scalar_equal(
                scalar, wrapped, ctypes.byref(equal)
            )
            == 0
        )
        assert equal.value == 1
        assert runtime.irx_arrow_array_copy(owner, ctypes.byref(copied)) == 0
        assert runtime.irx_arrow_array_release(ctypes.byref(owner)) == 0
        restored = export_array(runtime, copied)
        assert restored.equals(source)
        assert restored.type == type_
    finally:
        runtime.irx_arrow_type_release(ctypes.byref(descriptor))
        runtime.irx_arrow_field_release(ctypes.byref(expected))
        runtime.irx_arrow_c_data_release(ctypes.byref(token))
        for handle in (owner, copied):
            runtime.irx_arrow_array_release(ctypes.byref(handle))
        for handle in (scalar, storage, wrapped):
            runtime.irx_arrow_scalar_release(ctypes.byref(handle))


def test_extension_storage_mismatch_and_failures(
    runtime: ctypes.CDLL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Mismatch or owner allocation failure never publishes partial values.
    parameters:
      runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    descriptor = type_owner(runtime, pa.uuid())
    storage_type = type_owner(runtime, pa.binary(16))
    wrong_type = type_owner(runtime, pa.string())
    storage, wrong, wrapped, result = (ctypes.c_void_p() for _ in range(4))
    try:
        assert (
            runtime.irx_arrow_scalar_parse(
                storage_type, b"0123456789abcdef", ctypes.byref(storage)
            )
            == 0
        )
        assert (
            runtime.irx_arrow_scalar_parse(
                wrong_type, b"0123456789abcdef", ctypes.byref(wrong)
            )
            == 0
        )
        result.value = 1
        assert (
            runtime.irx_arrow_scalar_wrap(
                descriptor, wrong, ctypes.byref(result)
            )
            == TYPE_MISMATCH
        )
        assert not result.value
        monkeypatch.setenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION", "1")
        assert (
            runtime.irx_arrow_scalar_wrap(
                descriptor, storage, ctypes.byref(result)
            )
            == OUT_OF_MEMORY
        )
        assert not result.value
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION")
        assert (
            runtime.irx_arrow_scalar_wrap(
                descriptor, storage, ctypes.byref(wrapped)
            )
            == 0
        )
        monkeypatch.setenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION", "1")
        assert (
            runtime.irx_arrow_scalar_storage(wrapped, ctypes.byref(result))
            == OUT_OF_MEMORY
        )
        assert not result.value
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION")
        assert (
            runtime.irx_arrow_scalar_storage(wrapped, ctypes.byref(result))
            == 0
        )
    finally:
        monkeypatch.delenv(
            "IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION", raising=False
        )
        for handle in (descriptor, storage_type, wrong_type):
            runtime.irx_arrow_type_release(ctypes.byref(handle))
        for handle in (storage, wrong, wrapped, result):
            runtime.irx_arrow_scalar_release(ctypes.byref(handle))


def test_opaque_extension_identity(runtime: ctypes.CDLL) -> None:
    """
    title: Preserve unregistered identity and binary metadata without a codec.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    source = pa.array([1, None], type=pa.int32())
    name = b"arx.test.unregistered.storage"
    metadata = {
        b"ARROW:extension:name": name,
        b"ARROW:extension:metadata": b"\0\xffversion1",
    }
    field = pa.field("value", pa.int32(), metadata=metadata)
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(array))
    field._export_to_c(ctypes.addressof(schema))
    owner, value = ctypes.c_void_p(), ctypes.c_void_p()
    wrong = field_owner(
        runtime,
        pa.field(
            "value",
            pa.int32(),
            metadata={**metadata, b"ARROW:extension:metadata": b"different"},
        ),
    )
    try:
        assert (
            runtime.irx_arrow_c_data_import_move(
                ctypes.byref(array), ctypes.byref(schema), ctypes.byref(owner)
            )
            == 0
        )
        assert (
            runtime.irx_arrow_array_from_c_data(
                owner, wrong, ctypes.byref(value)
            )
            == TYPE_MISMATCH
        )
        assert not value.value
        assert (
            runtime.irx_arrow_c_data_export(
                owner, ctypes.byref(array), ctypes.byref(schema)
            )
            == 0
        )
        restored = pa.Field._import_from_c(ctypes.addressof(schema))
        logical = schema_from_pyarrow(pa.schema([restored])).fields[0].type_
        parameters = {item.kind: item.value for item in logical.parameters}
        assert parameters[astx.ParameterKind.EXTENSION_NAME] == name.decode()
        assert (
            parameters[astx.ParameterKind.EXTENSION_METADATA]
            == b"\0\xffversion1"
        )
        imported = pa.Array._import_from_c(
            ctypes.addressof(array), restored.type
        )
        assert isinstance(imported, pa.ExtensionArray)
        assert imported.storage.equals(source)
    finally:
        if array.release:
            ctypes.CFUNCTYPE(None, ctypes.POINTER(ArrowArrayStruct))(
                array.release
            )(ctypes.byref(array))
        _release_c_schema(schema)
        runtime.irx_arrow_c_data_release(ctypes.byref(owner))
        runtime.irx_arrow_array_release(ctypes.byref(value))
        runtime.irx_arrow_field_release(ctypes.byref(wrong))


@pytest.mark.parametrize(
    "name,metadata,storage,values",
    [
        (
            "arrow.variable_shape_tensor",
            b"{}",
            pa.struct(
                [
                    pa.field("data", pa.list_(pa.int32())),
                    pa.field("shape", pa.list_(pa.int32(), 1)),
                ]
            ),
            [{"data": [3, 5], "shape": [2]}, None],
        ),
        (
            "arrow.parquet.variant",
            b"",
            pa.struct(
                [
                    pa.field("metadata", pa.binary(), nullable=False),
                    pa.field("value", pa.binary(), nullable=False),
                ]
            ),
            [None],
        ),
    ],
)
def test_native_only_canonical_extensions(
    runtime: ctypes.CDLL,
    name: str,
    metadata: bytes,
    storage: pa.DataType,
    values: list[object],
) -> None:
    """
    title: Retain canonical codecs not exposed by PyArrow factory functions.
    parameters:
      runtime:
        type: ctypes.CDLL
      name:
        type: str
      metadata:
        type: bytes
      storage:
        type: pa.DataType
      values:
        type: list[object]
    """
    source = pa.array(values, type=storage)
    field = pa.field(
        "",
        storage,
        metadata={
            b"ARROW:extension:name": name.encode(),
            b"ARROW:extension:metadata": metadata,
        },
    )
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(array))
    field._export_to_c(ctypes.addressof(schema))
    owner = ctypes.c_void_p()
    try:
        assert (
            runtime.irx_arrow_c_data_import_move(
                ctypes.byref(array), ctypes.byref(schema), ctypes.byref(owner)
            )
            == 0
        )
        assert (
            runtime.irx_arrow_c_data_export(
                owner, ctypes.byref(array), ctypes.byref(schema)
            )
            == 0
        )
        restored = pa.Field._import_from_c(ctypes.addressof(schema))
        logical = schema_from_pyarrow(pa.schema([restored])).fields[0].type_
        parameters = {item.kind: item.value for item in logical.parameters}
        assert parameters[astx.ParameterKind.EXTENSION_NAME] == name
        imported = pa.Array._import_from_c(
            ctypes.addressof(array), restored.type
        )
        assert isinstance(imported, pa.ExtensionArray)
        assert imported.storage.equals(source)
    finally:
        if array.release:
            ctypes.CFUNCTYPE(None, ctypes.POINTER(ArrowArrayStruct))(
                array.release
            )(ctypes.byref(array))
        _release_c_schema(schema)
        runtime.irx_arrow_c_data_release(ctypes.byref(owner))


def test_extension_storage_logical_nulls(runtime: ctypes.CDLL) -> None:
    """
    title: Extension storage without a parent bitmap retains logical nulls.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    source = pa.RunEndEncodedArray.from_arrays(
        pa.array([2, 3], type=pa.int16()), pa.array([None, "x"])
    )
    field = pa.field(
        "",
        source.type,
        metadata={
            b"ARROW:extension:name": b"arx.test.run_storage",
            b"ARROW:extension:metadata": b"opaque",
        },
    )
    expected = field_owner(runtime, field)
    required = field_owner(runtime, field.with_nullable(False))
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(array))
    field._export_to_c(ctypes.addressof(schema))
    token, owner, scalar, descriptor, chunks, masked = (
        ctypes.c_void_p() for _ in range(6)
    )
    bitmap = import_bytes(runtime, [7])
    try:
        assert (
            runtime.irx_arrow_c_data_import_move(
                ctypes.byref(array), ctypes.byref(schema), ctypes.byref(token)
            )
            == 0
        )
        assert (
            runtime.irx_arrow_array_from_c_data(
                token, required, ctypes.byref(owner)
            )
            == TYPE_MISMATCH
        )
        assert not owner.value
        assert (
            runtime.irx_arrow_array_from_c_data(
                token, expected, ctypes.byref(owner)
            )
            == 0
        )
        assert runtime.irx_arrow_array_null_count(
            owner
        ) == source.to_pylist().count(None)
        assert (
            runtime.irx_arrow_array_get_scalar(owner, 0, ctypes.byref(scalar))
            == 0
        ), runtime.irx_arrow_last_error()
        assert not scalar.value
        assert (
            runtime.irx_arrow_field_type(expected, ctypes.byref(descriptor))
            == 0
        )
        pointers = (ctypes.c_void_p * 2)(owner.value, owner.value)
        assert (
            runtime.irx_arrow_chunked_new_logical(
                descriptor, 1, pointers, 2, ctypes.byref(chunks)
            )
            == 0
        )
        assert (
            runtime.irx_arrow_chunked_get_scalar(
                chunks, 3, ctypes.byref(scalar)
            )
            == 0
        )
        assert not scalar.value
        assert (
            runtime.irx_arrow_array_with_validity(
                owner, bitmap, 0, ctypes.byref(masked)
            )
            == 0
        )
        assert runtime.irx_arrow_array_null_count(
            masked
        ) == source.to_pylist().count(None)
    finally:
        if array.release:
            ctypes.CFUNCTYPE(None, ctypes.POINTER(ArrowArrayStruct))(
                array.release
            )(ctypes.byref(array))
        _release_c_schema(schema)
        runtime.irx_arrow_c_data_release(ctypes.byref(token))
        runtime.irx_arrow_array_release(ctypes.byref(owner))
        runtime.irx_arrow_array_release(ctypes.byref(bitmap))
        runtime.irx_arrow_array_release(ctypes.byref(masked))
        runtime.irx_arrow_type_release(ctypes.byref(descriptor))
        runtime.irx_arrow_chunked_array_release(ctypes.byref(chunks))
        runtime.irx_arrow_scalar_release(ctypes.byref(scalar))
        for handle in (expected, required):
            runtime.irx_arrow_field_release(ctypes.byref(handle))
