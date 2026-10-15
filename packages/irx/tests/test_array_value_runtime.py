"""
title: Primitive scalar extraction, bit offsets and independent array owners.
"""

from __future__ import annotations

import ctypes

from collections.abc import Iterator

import pyarrow as pa
import pytest

from .test_arrow_runtime import (
    ARROW_STATUS_TYPE_MISMATCH,
    ArrowArrayStruct,
    ArrowSchemaStruct,
    _capsule_pointer,
    _import_exported_array,
    _load_arrow_runtime_library,
)

ARROW_STATUS_INDEX_OUT_OF_BOUNDS = 105


@pytest.fixture(scope="module")
def array_runtime() -> Iterator[ctypes.CDLL]:
    """
    title: Reuse one native library for offset and ownership regressions.
    returns:
      type: Iterator[ctypes.CDLL]
    """
    with _load_arrow_runtime_library() as library:
        yield library


def export_array(library: ctypes.CDLL, owner: ctypes.c_void_p) -> pa.Array:
    """
    title: Export an independent C Data owner back into PyArrow.
    parameters:
      library:
        type: ctypes.CDLL
      owner:
        type: ctypes.c_void_p
    returns:
      type: pa.Array
    """
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    assert (
        library.irx_arrow_array_export(
            owner, ctypes.byref(array), ctypes.byref(schema)
        )
        == 0
    )
    return _import_exported_array(array, schema)


@pytest.mark.parametrize(
    "type_,suffix",
    [
        (type_(), "int")
        for type_ in (pa.int8, pa.int16, pa.int32, pa.int64, pa.bool_)
    ]
    + [
        (type_(), "uint")
        for type_ in (pa.uint8, pa.uint16, pa.uint32, pa.uint64)
    ]
    + [(type_(), "double") for type_ in (pa.float16, pa.float32, pa.float64)],
)
def test_scalar_offsets_copy_and_parent_release(
    array_runtime: ctypes.CDLL, type_: pa.DataType, suffix: str
) -> None:
    """
    title: Read all storage families safely through nonzero bitmap offsets.
    parameters:
      array_runtime:
        type: ctypes.CDLL
      type_:
        type: pa.DataType
      suffix:
        type: str
    """
    library = array_runtime
    payload = (
        True
        if pa.types.is_boolean(type_)
        else (2**64 - 1 if type_ == pa.uint64() else 7)
    )
    source = pa.array(
        [payload, payload, None, payload, None], type=type_
    ).slice(1, 3)
    schema_capsule, array_capsule = source.__arrow_c_array__()
    owner, child, copied = (
        ctypes.c_void_p(),
        ctypes.c_void_p(),
        ctypes.c_void_p(),
    )
    try:
        assert (
            library.irx_arrow_array_import_copy(
                _capsule_pointer(array_capsule, b"arrow_array"),
                _capsule_pointer(schema_capsule, b"arrow_schema"),
                ctypes.byref(owner),
            )
            == 0
        )
        assert (
            library.irx_arrow_array_slice(owner, 1, 2, ctypes.byref(child))
            == 0
        )
        assert library.irx_arrow_array_copy(child, ctypes.byref(copied)) == 0
        assert library.irx_arrow_array_offset(child) > 0
        original_view = export_array(library, child)
        copied_view = export_array(library, copied)
        assert (
            original_view.to_pylist()
            == copied_view.to_pylist()
            == [None, payload]
        )
        assert (
            original_view.buffers()[1].address
            != copied_view.buffers()[1].address
        )
        assert copied_view.offset == 0
        assert library.irx_arrow_array_release(ctypes.byref(owner)) == 0
        assert owner.value is None
        assert library.irx_arrow_array_release(ctypes.byref(copied)) == 0
        assert copied_view.to_pylist() == [None, payload]
        value_class = {
            "int": ctypes.c_int64,
            "uint": ctypes.c_uint64,
            "double": ctypes.c_double,
        }[suffix]
        value, valid = value_class(42), ctypes.c_int32(42)
        get = getattr(library, f"irx_arrow_array_get_{suffix}")
        assert get(child, 0, ctypes.byref(valid), ctypes.byref(value)) == 0
        assert valid.value == 0
        assert get(child, 1, ctypes.byref(valid), ctypes.byref(value)) == 0
        assert valid.value == 1 and value.value == payload
        for index in (-1, 2, 2**63 - 1):
            assert (
                get(child, index, ctypes.byref(valid), ctypes.byref(value))
                == ARROW_STATUS_INDEX_OUT_OF_BOUNDS
            )
            assert valid.value == 0
        assert (
            library.irx_arrow_array_slice(
                child, 1, 2**63 - 1, ctypes.byref(copied)
            )
            == ARROW_STATUS_INDEX_OUT_OF_BOUNDS
        )
        assert copied.value is None
        assert library.irx_arrow_array_release(ctypes.byref(child)) == 0
        assert original_view.to_pylist() == [None, payload]
    finally:
        for token in (owner, child, copied):
            assert library.irx_arrow_array_release(ctypes.byref(token)) == 0


def test_empty_all_null_and_wrong_accessor(array_runtime: ctypes.CDLL) -> None:
    """
    title: Preserve empty and all-null data while rejecting typed ABI mismatch.
    parameters:
      array_runtime:
        type: ctypes.CDLL
    """
    library = array_runtime
    for values in ([], [None, None]):
        source = pa.array(values, type=pa.int32())
        schema_capsule, array_capsule = source.__arrow_c_array__()
        owner, joined = ctypes.c_void_p(), ctypes.c_void_p()
        try:
            assert (
                library.irx_arrow_array_import_copy(
                    _capsule_pointer(array_capsule, b"arrow_array"),
                    _capsule_pointer(schema_capsule, b"arrow_schema"),
                    ctypes.byref(owner),
                )
                == 0
            )
            assert (
                library.irx_arrow_array_concat(
                    owner, owner, ctypes.byref(joined)
                )
                == 0
            )
            assert export_array(library, joined).to_pylist() == values + values
            valid, output = ctypes.c_int32(1), ctypes.c_double(3)
            assert (
                library.irx_arrow_array_get_double(
                    owner, 0, ctypes.byref(valid), ctypes.byref(output)
                )
                == ARROW_STATUS_TYPE_MISMATCH
            )
            assert valid.value == 0
        finally:
            assert library.irx_arrow_array_release(ctypes.byref(owner)) == 0
            assert library.irx_arrow_array_release(ctypes.byref(joined)) == 0


def test_typed_finish_preserves_builder_on_nullability_failure(
    array_runtime: ctypes.CDLL,
) -> None:
    """
    title: Reject invalid nullability before consuming the builder owner.
    parameters:
      array_runtime:
        type: ctypes.CDLL
    """
    library = array_runtime
    builder, result = ctypes.c_void_p(), ctypes.c_void_p()
    try:
        assert (
            library.irx_arrow_array_builder_int32_new(ctypes.byref(builder))
            == 0
        )
        assert library.irx_arrow_array_builder_append_null(builder, 1) == 0
        assert (
            library.irx_arrow_array_builder_finish_typed(
                ctypes.byref(builder), 0, ctypes.byref(result)
            )
            == ARROW_STATUS_TYPE_MISMATCH
        )
        assert builder.value is not None and result.value is None
        assert (
            library.irx_arrow_array_builder_finish_typed(
                ctypes.byref(builder), 1, ctypes.byref(result)
            )
            == 0
        )
        assert builder.value is None
        assert export_array(library, result).to_pylist() == [None]
        assert library.irx_arrow_array_is_nullable(result) == 1
        assert library.irx_arrow_array_release(ctypes.byref(result)) == 0
        assert (
            library.irx_arrow_array_builder_int32_new(ctypes.byref(builder))
            == 0
        )
        assert (
            library.irx_arrow_array_builder_finish_typed(
                ctypes.byref(builder), 0, ctypes.byref(result)
            )
            == 0
        )
        assert library.irx_arrow_array_is_nullable(result) == 0
    finally:
        assert (
            library.irx_arrow_array_builder_release(ctypes.byref(builder)) == 0
        )
        assert library.irx_arrow_array_release(ctypes.byref(result)) == 0
