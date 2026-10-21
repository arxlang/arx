"""
title: Checked native RecordBatch and DataFrame bridge contracts.
"""

import ctypes

from pathlib import Path

import pyarrow as pa
import pytest

from pyarrow.cffi import ffi

from .test_arrow_interop import address, import_batch, native  # noqa: F401


def import_schema(native: ctypes.CDLL, schema: pa.Schema) -> ctypes.c_void_p:
    """
    title: Import an independently owned expected schema.
    parameters:
      native:
        type: ctypes.CDLL
      schema:
        type: pa.Schema
    returns:
      type: ctypes.c_void_p
    """
    exported = ffi.new("struct ArrowSchema *")
    schema._export_to_c(address(exported))
    result = ctypes.c_void_p()
    assert (
        native.irx_rb_schema_import(address(exported), ctypes.byref(result))
        == 0
    )
    return result


@pytest.mark.parametrize("rows", [0, 3])
@pytest.mark.parametrize(
    "type_",
    [
        pa.int8(),
        pa.int16(),
        pa.int32(),
        pa.int64(),
        pa.float32(),
        pa.float64(),
        pa.bool_(),
    ],
)
def test_native_conversion_owns_buffers(
    native: ctypes.CDLL, rows: int, type_: pa.DataType
) -> None:
    """
    title: >-
      Both conversion directions survive source release and preserve physical
      types.
    parameters:
      native:
        type: ctypes.CDLL
      rows:
        type: int
      type_:
        type: pa.DataType
    """
    values = [True, False, True] if pa.types.is_boolean(type_) else [1, 2, 3]
    batch = pa.record_batch(
        [pa.array(values[:rows], type=type_)], names=["value"]
    )
    handle = import_batch(native, batch)
    expected = import_schema(
        native, pa.schema([pa.field("value", type_, nullable=False)])
    )
    table = ctypes.c_void_p()
    assert (
        native.irx_rb_batch_to_table(handle, expected, ctypes.byref(table))
        == 0
    )
    native.irx_rb_batch_release(handle)
    native.irx_rb_schema_release(expected)
    result = ctypes.c_void_p()
    assert native.irx_rb_table_to_batch(table, ctypes.byref(result)) == 0
    native.irx_arrow_table_release.argtypes = [ctypes.c_void_p]
    native.irx_arrow_table_release.restype = None
    native.irx_arrow_table_release(table)
    array = ffi.new("struct ArrowArray *")
    schema = ffi.new("struct ArrowSchema *")
    assert (
        native.irx_rb_batch_export(result, address(array), address(schema))
        == 0
    )
    native.irx_rb_batch_release(result)
    exported = pa.RecordBatch._import_from_c(address(array), address(schema))
    assert exported.num_rows == rows
    assert exported.column(0).equals(batch.column(0))
    assert not exported.schema.field(0).nullable


@pytest.mark.parametrize(
    "array, name, expected_type, message",
    [
        (
            pa.array([None], type=pa.int64()),
            "value",
            pa.int64(),
            "null values",
        ),
        (pa.array(["text"]), "value", pa.int64(), "keep this data"),
        (
            pa.array([1], type=pa.uint64()),
            "value",
            pa.int64(),
            "keep this data",
        ),
        (pa.array([1], type=pa.int64()), "value", pa.int32(), "expected"),
        (pa.array([1], type=pa.int64()), "other", pa.int64(), "expected"),
        (
            pa.array([0], type=pa.timestamp("ns")),
            "value",
            pa.int64(),
            "keep this data",
        ),
    ],
)
def test_conversion_rejects_without_publishing(
    native: ctypes.CDLL,
    array: pa.Array,
    name: str,
    expected_type: pa.DataType,
    message: str,
) -> None:
    """
    title: >-
      Unsupported data never publishes a partial table or consumes its source.
    parameters:
      native:
        type: ctypes.CDLL
      array:
        type: pa.Array
      name:
        type: str
      expected_type:
        type: pa.DataType
      message:
        type: str
    """
    handle = import_batch(native, pa.record_batch([array], names=[name]))
    expected = import_schema(
        native, pa.schema([pa.field("value", expected_type, nullable=False)])
    )
    output = ctypes.c_void_p(123)
    try:
        assert (
            native.irx_rb_batch_to_table(
                handle, expected, ctypes.byref(output)
            )
            < 0
        )
        assert not output.value
        assert message.encode() in native.irx_record_batch_errmsg()
        assert native.irx_rb_batch_num_rows(handle) == 1
    finally:
        native.irx_rb_schema_release(expected)
        native.irx_rb_batch_release(handle)


@pytest.mark.parametrize(
    "type_,value",
    [
        (pa.int8(), 12),
        (pa.int16(), 12),
        (pa.int32(), 12),
        (pa.int64(), 12),
        (pa.uint8(), 12),
        (pa.uint16(), 12),
        (pa.uint32(), 12),
        (pa.uint64(), 12),
        (pa.float32(), 1.25),
        (pa.float64(), 1.25),
        (pa.bool_(), True),
        (pa.string(), 'λ,"\n'),
        (pa.large_string(), ""),
        (pa.date32(), 1),
        (pa.date64(), 86400000),
        (pa.timestamp("s"), 1),
        (pa.timestamp("ms"), 1),
        (pa.timestamp("us"), 1),
        (pa.timestamp("ns"), 1),
        (pa.time32("s"), 1),
        (pa.time32("ms"), 1),
        (pa.time64("us"), 1),
        (pa.time64("ns"), 1),
    ],
)
def test_native_csv_scalar_contract(
    native: ctypes.CDLL, tmp_path: Path, type_: pa.DataType, value: object
) -> None:
    """
    title: Verify Arrow CSV read/write support for each advertised scalar type.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      type_:
        type: pa.DataType
      value:
        type: object
    """
    expected = pa.record_batch(
        [pa.array([value, None], type=type_)], names=["v"]
    )
    schema = import_schema(native, expected.schema)
    batch = import_batch(native, expected)
    writer = ctypes.c_void_p()
    path = str(tmp_path / "scalar.csv").encode()
    try:
        assert (
            native.irx_rb_csv_writer_open(
                schema, path, b",", 1, ctypes.byref(writer)
            )
            == 0
        )
        assert native.irx_rb_stream_writer_write_batch(writer, batch) == 0
        assert native.irx_rb_stream_writer_close(writer) == 0
    finally:
        native.irx_rb_stream_writer_release(writer)
        native.irx_rb_batch_release(batch)
    reader = ctypes.c_void_p()
    try:
        status = native.irx_rb_csv_reader_open(
            path, schema, b",", 1, 1048576, ctypes.byref(reader)
        )
        assert status == 0, native.irx_record_batch_errmsg()
        result = ctypes.c_void_p()
        assert (
            native.irx_rb_stream_reader_next_batch(
                reader, ctypes.byref(result)
            )
            == 0
        )
        array = ffi.new("struct ArrowArray *")
        exported = ffi.new("struct ArrowSchema *")
        assert (
            native.irx_rb_batch_export(
                result, address(array), address(exported)
            )
            == 0
        )
        native.irx_rb_batch_release(result)
        actual = pa.RecordBatch._import_from_c(
            address(array), address(exported)
        )
        assert actual.equals(expected)
    finally:
        native.irx_rb_stream_reader_close(reader)
        native.irx_rb_schema_release(schema)


def test_table_export_combines_all_chunks(tmp_path: Path) -> None:
    """
    title: >-
      Native table export includes every chunk, not merely the first batch.
    parameters:
      tmp_path:
        type: Path
    """
    import subprocess  # noqa: PLC0415

    from irx.builder.runtime.arrowcpp import (  # noqa: PLC0415
        arrowcpp_compile_flags,
        arrowcpp_include_dirs,
        arrowcpp_linker_flags,
    )

    runtime = Path(__file__).resolve().parents[1] / "src/irx/builder/runtime"
    source = tmp_path / "chunks.cc"
    source.write_text("""#include "irx_arrow_runtime.cc"
#include <cassert>
int main() {
    arrow::Int64Builder builder;
    assert(builder.AppendValues({1, 2}).ok());
    auto first = builder.Finish().ValueOrDie();
    assert(builder.AppendValues({3, 4, 5}).ok());
    auto second = builder.Finish().ValueOrDie();
    auto chunks = std::make_shared<arrow::ChunkedArray>(
        arrow::ArrayVector{first, second});
    irx_arrow_table_handle table;
    table.table = arrow::Table::Make(
        arrow::schema({arrow::field("v", arrow::int64(), false)}), {chunks});
    ArrowArray array{};
    ArrowSchema schema{};
    assert(irx_arrow_table_export_batch(&table, &array, &schema) == 0);
    table.table.reset();
    auto batch = arrow::ImportRecordBatch(&array, &schema).ValueOrDie();
    assert(batch->num_rows() == 5);
    auto values =
        std::static_pointer_cast<arrow::Int64Array>(batch->column(0));
    for (int64_t i = 0; i < 5; ++i) assert(values->Value(i) == i + 1);
    assert(!array.release && !schema.release);
}
""")
    binary = tmp_path / "chunks"
    subprocess.run(
        [
            "c++",
            str(source),
            "-o",
            str(binary),
            *arrowcpp_compile_flags(),
            f"-I{runtime / 'arrow/native'}",
            f"-I{runtime / 'buffer/native'}",
            *(f"-I{path}" for path in arrowcpp_include_dirs()),
            *arrowcpp_linker_flags(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run([str(binary)], check=True)
