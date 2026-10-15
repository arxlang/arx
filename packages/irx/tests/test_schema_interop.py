"""
title: Logical schema C Data, native ownership, and IPC round-trip tests.
"""

from __future__ import annotations

import ctypes

from collections.abc import Iterator

import pyarrow as pa
import pytest

from astx.schema import LogicalKind, LogicalType, Schema, SchemaField
from irx.analysis.schema import canonical_schema
from irx.schema_interop import schema_from_pyarrow, schema_to_pyarrow

from .schema_cases import logical_type_cases
from .test_arrow_runtime import (
    ArrowSchemaStruct,
    _assert_arrow_ok,
    _load_arrow_runtime_library,
    _release_c_schema,
)


@pytest.fixture(scope="module")
def schema_runtime() -> Iterator[ctypes.CDLL]:
    """
    title: Build and load the registered native Arrow runtime for schema tests.
    returns:
      type: Iterator[ctypes.CDLL]
    """
    with _load_arrow_runtime_library(failure_injection=True) as library:
        yield library


@pytest.mark.parametrize(
    "type_", logical_type_cases(), ids=lambda value: value.kind.value
)
def test_descriptor_c_data_and_ipc_roundtrip(type_: LogicalType) -> None:
    """
    title: >-
      Every logical family preserves nested names, metadata and nullability.
    parameters:
      type_:
        type: LogicalType
    """
    descriptor = canonical_schema(
        Schema(
            (
                SchemaField(
                    "λ",
                    type_,
                    nullable=True,
                    metadata=((b"\x00key", b"\x00\xffvalue"),),
                ),
            ),
            metadata=((b"schema", b"\x00\xff"),),
        )
    )
    schema = schema_to_pyarrow(descriptor)
    assert schema_from_pyarrow(schema) == descriptor
    assert (
        schema_from_pyarrow(pa.ipc.read_schema(schema.serialize()))
        == descriptor
    )


@pytest.mark.parametrize(
    "type_", logical_type_cases(), ids=lambda value: value.kind.value
)
def test_native_schema_copy_preserves_recursive_descriptor(
    schema_runtime: ctypes.CDLL,
    type_: LogicalType,
) -> None:
    """
    title: >-
      Native schema copies outlive producers and retain all recursive metadata.
    parameters:
      schema_runtime:
        type: ctypes.CDLL
      type_:
        type: LogicalType
    """
    descriptor = canonical_schema(
        Schema(
            (
                SchemaField(
                    "value",
                    type_,
                    nullable=True,
                    metadata=((b"field", b"\x00\xff"),),
                ),
            ),
            metadata=((b"schema", b"\x00data"),),
        )
    )
    source = schema_to_pyarrow(descriptor)
    input_schema = ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(input_schema))
    input_release = input_schema.release
    owner = ctypes.c_void_p()
    retained = ctypes.c_void_p()
    output = ArrowSchemaStruct()
    try:
        _assert_arrow_ok(
            schema_runtime,
            schema_runtime.irx_arrow_schema_import_copy(
                ctypes.byref(input_schema),
                ctypes.byref(owner),
            ),
        )
        assert input_schema.release == input_release
        _release_c_schema(input_schema)
        del source
        _assert_arrow_ok(
            schema_runtime,
            schema_runtime.irx_arrow_schema_retain(
                owner,
                ctypes.byref(retained),
            ),
        )
        _assert_arrow_ok(
            schema_runtime,
            schema_runtime.irx_arrow_schema_release(ctypes.byref(owner)),
        )
        _assert_arrow_ok(
            schema_runtime,
            schema_runtime.irx_arrow_schema_export(
                retained,
                ctypes.byref(output),
            ),
        )
        _assert_arrow_ok(
            schema_runtime,
            schema_runtime.irx_arrow_schema_release(ctypes.byref(retained)),
        )
        restored = pa.Schema._import_from_c(ctypes.addressof(output))
        assert schema_from_pyarrow(restored) == descriptor
        assert output.release is None
    finally:
        _release_c_schema(input_schema)
        _release_c_schema(output)
        schema_runtime.irx_arrow_schema_release(ctypes.byref(owner))
        schema_runtime.irx_arrow_schema_release(ctypes.byref(retained))


def test_empty_schema_and_empty_struct_roundtrip() -> None:
    """
    title: Empty structural values must not become dynamic or missing schemas.
    """
    for descriptor in (
        Schema(),
        Schema((SchemaField("empty", LogicalType(LogicalKind.STRUCT)),)),
    ):
        assert schema_from_pyarrow(schema_to_pyarrow(descriptor)) == descriptor


def test_native_schema_failed_import_preserves_source(
    schema_runtime: ctypes.CDLL,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: An allocation failure leaves output null and source retryable.
    parameters:
      schema_runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    source = schema_to_pyarrow(
        Schema((SchemaField("x", LogicalType(LogicalKind.STRING)),))
    )
    input_schema = ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(input_schema))
    owner = ctypes.c_void_p(123)
    release = input_schema.release
    try:
        monkeypatch.setenv(
            "IRX_ARROW_TEST_FAIL_OPERATION", "schema_import_copy"
        )
        status = schema_runtime.irx_arrow_schema_import_copy(
            ctypes.byref(input_schema), ctypes.byref(owner)
        )
        assert status != 0
        assert owner.value is None
        assert input_schema.release == release
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_OPERATION")
        _assert_arrow_ok(
            schema_runtime,
            schema_runtime.irx_arrow_schema_import_copy(
                ctypes.byref(input_schema),
                ctypes.byref(owner),
            ),
        )
    finally:
        _release_c_schema(input_schema)
        schema_runtime.irx_arrow_schema_release(ctypes.byref(owner))


def test_native_schema_invalid_export_clears_output(
    schema_runtime: ctypes.CDLL,
) -> None:
    """
    title: Failed export must never leave a stale producer callback in output.
    parameters:
      schema_runtime:
        type: ctypes.CDLL
    """
    output = ArrowSchemaStruct()
    output.release = 123
    assert (
        schema_runtime.irx_arrow_schema_export(None, ctypes.byref(output)) != 0
    )
    assert output.release is None


@pytest.mark.parametrize("damage", ["released", "negative_children", "cycle"])
def test_native_malformed_schema_trees_leave_producer_untouched(
    schema_runtime: ctypes.CDLL,
    damage: str,
) -> None:
    """
    title: >-
      Invalid recursive descriptors fail without consuming producer storage.
    parameters:
      schema_runtime:
        type: ctypes.CDLL
      damage:
        type: str
    """
    source = pa.schema([pa.field("x", pa.int32())])
    input_schema = ArrowSchemaStruct()
    source._export_to_c(ctypes.addressof(input_schema))
    owner = ctypes.c_void_p(123)
    release = input_schema.release
    children = input_schema.children
    count = input_schema.n_children
    cycle = (ctypes.c_void_p * 1)(ctypes.addressof(input_schema))
    try:
        if damage == "released":
            input_schema.release = None
        elif damage == "negative_children":
            input_schema.n_children = -1
        else:
            input_schema.children = ctypes.addressof(cycle)
        status = schema_runtime.irx_arrow_schema_import_copy(
            ctypes.byref(input_schema),
            ctypes.byref(owner),
        )
        assert status != 0
        assert owner.value is None
        assert input_schema.release == (
            None if damage == "released" else release
        )
    finally:
        input_schema.release = release
        input_schema.children = children
        input_schema.n_children = count
        _release_c_schema(input_schema)
        schema_runtime.irx_arrow_schema_release(ctypes.byref(owner))


@pytest.mark.parametrize("type_", [pa.uuid(), pa.json_(), pa.bool8()])
def test_registered_extension_schema_roundtrip(type_: pa.DataType) -> None:
    """
    title: Registered Arrow extension schemas preserve storage and identity.
    parameters:
      type_:
        type: pa.DataType
    """
    original = pa.schema([pa.field("value", type_, nullable=True)])
    descriptor = schema_from_pyarrow(original)
    assert descriptor.fields[0].type_.kind is LogicalKind.EXTENSION
    assert schema_to_pyarrow(descriptor).equals(original, check_metadata=True)
    assert (
        schema_from_pyarrow(pa.ipc.read_schema(original.serialize()))
        == descriptor
    )
