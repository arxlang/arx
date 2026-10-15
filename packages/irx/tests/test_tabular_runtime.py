"""
title: Native tabular schema checks, metadata and independent owner lifetimes.
"""

from __future__ import annotations

import ctypes

from collections.abc import Iterator

import pyarrow as pa
import pytest

from .test_arrow_runtime import (
    ArrowArrayStruct,
    ArrowSchemaStruct,
    _capsule_pointer,
    _load_arrow_runtime_library,
    _release_c_schema,
)

SCHEMA_MISMATCH = 104
INDEX_OUT_OF_BOUNDS = 105
OUT_OF_MEMORY = 200
TYPE_MISMATCH = 103


@pytest.fixture(scope="module")
def runtime() -> Iterator[ctypes.CDLL]:
    """
    title: Load the checked tabular ABI with failure injection enabled.
    returns:
      type: Iterator[ctypes.CDLL]
    """
    with _load_arrow_runtime_library(failure_injection=True) as library:
        yield library


def import_batch(
    library: ctypes.CDLL, value: pa.RecordBatch
) -> ctypes.c_void_p:
    """
    title: Move a PyArrow C Data export into an independent runtime owner.
    parameters:
      library:
        type: ctypes.CDLL
      value:
        type: pa.RecordBatch
    returns:
      type: ctypes.c_void_p
    """
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    value._export_to_c(ctypes.addressof(array), ctypes.addressof(schema))
    owner = ctypes.c_void_p()
    assert (
        library.irx_arrow_record_batch_import_move(
            ctypes.byref(array), ctypes.byref(schema), ctypes.byref(owner)
        )
        == 0
    )
    assert not array.release and not schema.release
    return owner


def export_batch(
    library: ctypes.CDLL, owner: ctypes.c_void_p
) -> pa.RecordBatch:
    """
    title: Transfer a fresh C Data export into PyArrow without consuming input.
    parameters:
      library:
        type: ctypes.CDLL
      owner:
        type: ctypes.c_void_p
    returns:
      type: pa.RecordBatch
    """
    array, schema = ArrowArrayStruct(), ArrowSchemaStruct()
    assert (
        library.irx_arrow_record_batch_export(
            owner, ctypes.byref(array), ctypes.byref(schema)
        )
        == 0
    )
    return pa.RecordBatch._import_from_c(
        ctypes.addressof(array), ctypes.addressof(schema)
    )


@pytest.mark.parametrize("as_table", [False, True])
@pytest.mark.parametrize(
    "indices,status",
    [
        (pa.array([], type=pa.int64()), 0),
        (pa.array([9, 1, 0, 0], type=pa.int64()).slice(1), 0),
        (pa.array([-1], type=pa.int64()), INDEX_OUT_OF_BOUNDS),
        (pa.array([2], type=pa.int64()), INDEX_OUT_OF_BOUNDS),
        (pa.array([None], type=pa.int64()), TYPE_MISMATCH),
        (pa.array([0], type=pa.int32()), TYPE_MISMATCH),
    ],
)
def test_tabular_take_checked_indices(
    runtime: ctypes.CDLL,
    as_table: bool,
    indices: pa.Array,
    status: int,
) -> None:
    """
    title: Select repeated sliced indices or clear invalid selection output.
    parameters:
      runtime:
        type: ctypes.CDLL
      as_table:
        type: bool
      indices:
        type: pa.Array
      status:
        type: int
    """
    source = pa.record_batch(
        [pa.array(["λ", None]), pa.array([[1, None], []])],
        schema=pa.schema(
            [
                pa.field("text", pa.string(), metadata={b"field": b"x"}),
                pa.field("items", pa.list_(pa.int64())),
            ],
            metadata={b"origin": b"\0\xff"},
        ),
    )
    batch = import_batch(runtime, source)
    table, order, output, restored = (ctypes.c_void_p() for _ in range(4))
    schema_capsule, array_capsule = indices.__arrow_c_array__()
    kind = "table" if as_table else "batch"
    release = (
        runtime.irx_arrow_table_release
        if as_table
        else runtime.irx_arrow_record_batch_release
    )
    try:
        assert (
            runtime.irx_arrow_array_import_copy(
                _capsule_pointer(array_capsule, b"arrow_array"),
                _capsule_pointer(schema_capsule, b"arrow_schema"),
                ctypes.byref(order),
            )
            == 0
        )
        if as_table:
            assert (
                runtime.irx_arrow_batch_to_table(batch, ctypes.byref(table))
                == 0
            )
        output.value = 1
        assert (
            getattr(runtime, f"irx_arrow_{kind}_take")(
                table if as_table else batch, order, ctypes.byref(output)
            )
            == status
        )
        if status:
            assert not output.value
            assert export_batch(runtime, batch).equals(
                source, check_metadata=True
            )
            return
        assert runtime.irx_arrow_record_batch_release(ctypes.byref(batch)) == 0
        assert runtime.irx_arrow_table_release(ctypes.byref(table)) == 0
        assert runtime.irx_arrow_array_release(ctypes.byref(order)) == 0
        if as_table:
            assert (
                runtime.irx_arrow_table_to_batch(
                    output, ctypes.byref(restored)
                )
                == 0
            )
            assert release(ctypes.byref(output)) == 0
        result = export_batch(runtime, restored if as_table else output)
        assert result.equals(source.take(indices), check_metadata=True)
    finally:
        assert runtime.irx_arrow_record_batch_release(ctypes.byref(batch)) == 0
        assert runtime.irx_arrow_table_release(ctypes.byref(table)) == 0
        assert runtime.irx_arrow_array_release(ctypes.byref(order)) == 0
        assert release(ctypes.byref(output)) == 0
        assert (
            runtime.irx_arrow_record_batch_release(ctypes.byref(restored)) == 0
        )


def test_imported_nested_tabular_views(runtime: ctypes.CDLL) -> None:
    """
    title: Preserve sliced recursive columns and metadata through native views.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    source = pa.record_batch(
        [pa.array(["discard", "λ", None]), pa.array([[0], [], [1, None]])],
        schema=pa.schema(
            [
                pa.field("text", pa.string()),
                pa.field("items", pa.list_(pa.int64())),
            ],
            metadata={b"origin": b"\0\xff"},
        ),
    ).slice(1, 2)
    batch = import_batch(runtime, source)
    table, view, restored = (ctypes.c_void_p() for _ in range(3))
    schema_owner = ctypes.c_void_p()
    try:
        assert (
            runtime.irx_arrow_batch_to_table(batch, ctypes.byref(table)) == 0
        )
        assert runtime.irx_arrow_record_batch_release(ctypes.byref(batch)) == 0
        assert (
            runtime.irx_arrow_table_slice(table, 0, 2, ctypes.byref(view)) == 0
        )
        assert runtime.irx_arrow_table_release(ctypes.byref(table)) == 0
        assert (
            runtime.irx_arrow_table_schema(view, ctypes.byref(schema_owner))
            == 0
        )
        assert (
            runtime.irx_arrow_table_to_batch(view, ctypes.byref(restored)) == 0
        )
        assert runtime.irx_arrow_table_release(ctypes.byref(view)) == 0
        result = export_batch(runtime, restored)
        assert result.equals(source, check_metadata=True)
        exported = ArrowSchemaStruct()
        assert (
            runtime.irx_arrow_schema_export(
                schema_owner, ctypes.byref(exported)
            )
            == 0
        )
        expected = pa.Schema._import_from_c(ctypes.addressof(exported))
        assert expected.equals(source.schema, check_metadata=True)
    finally:
        for owner, release in (
            (batch, runtime.irx_arrow_record_batch_release),
            (table, runtime.irx_arrow_table_release),
            (view, runtime.irx_arrow_table_release),
            (restored, runtime.irx_arrow_record_batch_release),
            (schema_owner, runtime.irx_arrow_schema_release),
        ):
            assert release(ctypes.byref(owner)) == 0


def test_tabular_rejects_mismatched_field_and_bad_bounds(
    runtime: ctypes.CDLL,
) -> None:
    """
    title: Clear failed outputs and leave parent owners reusable after errors.
    parameters:
      runtime:
        type: ctypes.CDLL
    """
    source = pa.record_batch(
        [pa.array([1, None], type=pa.int32())], names=["a"]
    )
    batch = import_batch(runtime, source)
    field, output = ctypes.c_void_p(), ctypes.c_void_p(1)
    exported = ArrowSchemaStruct()
    pa.field("a", pa.int32(), nullable=False)._export_to_c(
        ctypes.addressof(exported)
    )
    try:
        assert (
            runtime.irx_arrow_field_import_copy(
                ctypes.byref(exported), ctypes.byref(field)
            )
            == 0
        )
        _release_c_schema(exported)
        assert (
            runtime.irx_arrow_batch_column_checked(
                batch, 0, field, ctypes.byref(output)
            )
            == SCHEMA_MISMATCH
        )
        assert output.value is None
        for offset, length in ((-1, 1), (0, -1), (2, 1), (1, 2**63 - 1)):
            assert (
                runtime.irx_arrow_batch_slice(
                    batch, offset, length, ctypes.byref(output)
                )
                == INDEX_OUT_OF_BOUNDS
            )
            assert output.value is None
        assert (
            runtime.irx_arrow_batch_slice(batch, 2, 0, ctypes.byref(output))
            == 0
        )
        assert export_batch(runtime, output).num_rows == 0
        assert (
            runtime.irx_arrow_record_batch_release(ctypes.byref(output)) == 0
        )
        duplicate = (ctypes.c_int64 * 2)(0, 0)
        assert (
            runtime.irx_arrow_batch_select(
                batch, duplicate, 2, ctypes.byref(output)
            )
            != 0
        )
        assert output.value is None
        assert export_batch(runtime, batch).equals(source)
    finally:
        _release_c_schema(exported)
        assert runtime.irx_arrow_field_release(ctypes.byref(field)) == 0
        assert (
            runtime.irx_arrow_record_batch_release(ctypes.byref(output)) == 0
        )
        assert runtime.irx_arrow_record_batch_release(ctypes.byref(batch)) == 0


def test_tabular_allocation_failure_is_retryable(
    runtime: ctypes.CDLL, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Allocation failure publishes no owner and preserves borrowed input.
    parameters:
      runtime:
        type: ctypes.CDLL
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    source = pa.record_batch([pa.array([1, None])], names=["a"])
    batch = import_batch(runtime, source)
    table = ctypes.c_void_p(1)
    try:
        monkeypatch.setenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION", "1")
        assert (
            runtime.irx_arrow_batch_to_table(batch, ctypes.byref(table))
            == OUT_OF_MEMORY
        )
        assert table.value is None
        monkeypatch.delenv("IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION")
        assert (
            runtime.irx_arrow_batch_to_table(batch, ctypes.byref(table)) == 0
        )
        assert export_batch(runtime, batch).equals(source)
    finally:
        monkeypatch.delenv(
            "IRX_ARROW_TEST_FAIL_HANDLE_ALLOCATION", raising=False
        )
        assert runtime.irx_arrow_table_release(ctypes.byref(table)) == 0
        assert runtime.irx_arrow_record_batch_release(ctypes.byref(batch)) == 0
