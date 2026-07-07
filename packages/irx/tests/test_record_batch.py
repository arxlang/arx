"""
title: Record batch streaming API.
"""

from __future__ import annotations

import math

from pathlib import Path

import pyarrow as pa
import pytest

from irx.record_batch import (
    IrxColumnType,
    RecordBatchBuilder,
    RecordBatchSchema,
    RecordBatchStreamReader,
    RecordBatchStreamWriter,
)

# Helpers

EXPECTED_FIELD_COUNT = 2
ROW_COUNT = 4
NULL_ROW_INDEX = 2
INT32_VALUE = 42
INT32_VALUE_ALT = 7
BATCH_ROW_COUNT = 10
BATCH_ROW_COUNT_LARGE = 20
PYARROW_ROW_COUNT = 5
PYARROW_BATCH_ROW_COUNT = 3
PYARROW_BATCH_COLUMN_COUNT = 2
PYARROW_FIRST_INT32_VALUE = 10
PYARROW_LAST_INT32_VALUE = 30
PYARROW_CONTEXT_MANAGER_INT32_VALUE = 99


def make_simple_schema() -> RecordBatchSchema:
    """
    title: Create a simple schema with one int32 and one float64 column.
    returns:
      type: RecordBatchSchema
    """
    schema = RecordBatchSchema()
    schema.add_field("id", IrxColumnType.INT32, nullable=False)
    schema.add_field("value", IrxColumnType.FLOAT64, nullable=True)
    return schema


def fill_builder(builder: RecordBatchBuilder, n: int) -> None:
    """
    title: Append a simple pattern of rows to a record-batch builder.
    parameters:
      builder:
        type: RecordBatchBuilder
      n:
        type: int
    """
    for i in range(n):
        builder.append_int32(0, i)
        builder.append_float64(1, i * 1.5)


# Schema tests


class TestSchema:
    def test_empty_schema(self):
        """
        title: Ensure an empty schema reports zero fields.
        """
        s = RecordBatchSchema()
        assert s.num_fields == 0
        s.release()

    def test_add_fields(self):
        """
        title: Ensure schema fields can be added and counted.
        """
        s = RecordBatchSchema()
        s.add_field("a", IrxColumnType.INT32)
        s.add_field("b", IrxColumnType.FLOAT64, nullable=False)
        assert s.num_fields == EXPECTED_FIELD_COUNT
        s.release()

    def test_all_types(self):
        """
        title: Ensure every supported column type can be registered.
        """
        s = RecordBatchSchema()
        for ct in IrxColumnType:
            s.add_field(ct.name.lower(), ct)
        assert s.num_fields == len(IrxColumnType)
        s.release()

    def test_double_release_is_safe(self):
        """
        title: Ensure releasing a schema more than once is harmless.
        """
        s = RecordBatchSchema()
        s.release()
        s.release()  # must not crash


# Builder / batch tests


class TestBuilder:
    def test_build_and_inspect(self):
        """
        title: Ensure builders can create and inspect a simple batch.
        """
        schema = make_simple_schema()
        builder = RecordBatchBuilder(schema)
        fill_builder(builder, 4)
        batch = builder.finish()

        assert batch.num_rows == ROW_COUNT
        assert batch.num_columns == EXPECTED_FIELD_COUNT

        for i in range(ROW_COUNT):
            assert batch.get_int32(0, i) == i
            assert math.isclose(batch.get_float64(1, i), i * 1.5)

        batch.release()
        builder.release()
        schema.release()

    def test_null_values(self):
        """
        title: Ensure null values are reported correctly.
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32, nullable=True)
        builder = RecordBatchBuilder(schema)
        builder.append_int32(0, 42)
        builder.append_null(0)
        builder.append_int32(0, 7)
        batch = builder.finish()

        assert batch.is_null(0, 0) is False
        assert batch.is_null(0, 1) is True
        assert batch.is_null(0, NULL_ROW_INDEX) is False
        assert batch.get_int32(0, 0) == INT32_VALUE
        assert batch.get_int32(0, NULL_ROW_INDEX) == INT32_VALUE_ALT

        batch.release()
        builder.release()
        schema.release()

    def test_bool_column(self):
        """
        title: Ensure boolean columns round-trip through the builder.
        """
        schema = RecordBatchSchema()
        schema.add_field("flag", IrxColumnType.BOOL)
        builder = RecordBatchBuilder(schema)
        builder.append_bool(0, True)
        builder.append_bool(0, False)
        builder.append_bool(0, True)
        batch = builder.finish()

        assert batch.get_bool(0, 0) is True
        assert batch.get_bool(0, 1) is False
        assert batch.get_bool(0, 2) is True
        batch.release()
        builder.release()
        schema.release()

    def test_all_numeric_types(self):
        """
        title: Ensure all numeric column types are supported.
        """
        schema = RecordBatchSchema()
        types_and_appenders = [
            (IrxColumnType.INT8, "append_int8", "get_int8", -1),
            (IrxColumnType.INT16, "append_int16", "get_int16", -2),
            (IrxColumnType.INT32, "append_int32", "get_int32", -3),
            (IrxColumnType.INT64, "append_int64", "get_int64", -4),
            (IrxColumnType.UINT8, "append_uint8", "get_uint8", 5),
            (IrxColumnType.UINT16, "append_uint16", "get_uint16", 6),
            (IrxColumnType.UINT32, "append_uint32", "get_uint32", 7),
            (IrxColumnType.UINT64, "append_uint64", "get_uint64", 8),
            (IrxColumnType.FLOAT32, "append_float32", "get_float32", 1.5),
            (IrxColumnType.FLOAT64, "append_float64", "get_float64", 2.5),
        ]
        for i, (ct, _, _, _) in enumerate(types_and_appenders):
            schema.add_field(f"col_{i}", ct)

        builder = RecordBatchBuilder(schema)
        for i, (_, append_fn, _, value) in enumerate(types_and_appenders):
            getattr(builder, append_fn)(i, value)
        batch = builder.finish()

        for i, (_, _, get_fn, expected) in enumerate(types_and_appenders):
            got = getattr(batch, get_fn)(i, 0)
            assert math.isclose(got, expected, rel_tol=1e-5), (
                f"col {i}: got {got!r}, expected {expected!r}"
            )

        batch.release()
        builder.release()
        schema.release()

    def test_oob_column_raises(self):
        """
        title: Ensure out-of-bounds columns raise a runtime error.
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="out of bounds"):
            builder.append_int32(99, 0)
        builder.release()
        schema.release()

    def test_type_mismatch_raises(self):
        """
        title: Ensure type mismatches raise a runtime error.
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_float64(0, 3.14)
        builder.release()
        schema.release()

    def test_empty_batch(self):
        """
        title: Ensure an empty batch can be produced and inspected.
        """
        schema = make_simple_schema()
        builder = RecordBatchBuilder(schema)
        batch = builder.finish()
        assert batch.num_rows == 0
        batch.release()
        builder.release()
        schema.release()


# Stream writer / reader round-trip — in-memory buffer


class TestBufferRoundTrip:
    def _write_batches(
        self, schema: RecordBatchSchema, batches_data: list
    ) -> bytes:
        """
        title: Write a list of batches into an in-memory stream.
        parameters:
          schema:
            type: RecordBatchSchema
          batches_data:
            type: list
        returns:
          type: bytes
        """
        writer = RecordBatchStreamWriter.open_buffer(schema)
        for rows in batches_data:
            builder = RecordBatchBuilder(schema)
            for i in rows:
                builder.append_int32(0, i)
                builder.append_float64(1, float(i))
            batch = builder.finish()
            writer.write_batch(batch)
            batch.release()
            builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        return data

    def test_single_batch_round_trip(self):
        """
        title: Ensure a single batch survives a buffer round-trip.
        """
        schema = make_simple_schema()
        data = self._write_batches(schema, [range(10)])

        reader = RecordBatchStreamReader.open_buffer(data)
        batch = reader.next_batch()
        assert batch is not None
        assert batch.num_rows == BATCH_ROW_COUNT
        for i in range(BATCH_ROW_COUNT):
            assert batch.get_int32(0, i) == i
            assert math.isclose(batch.get_float64(1, i), float(i))
        batch.release()

        assert reader.next_batch() is None  # EOF
        reader.close()
        schema.release()

    def test_multiple_batches_round_trip(self):
        """
        title: Ensure multiple batches survive a buffer round-trip.
        """
        schema = make_simple_schema()
        data = self._write_batches(
            schema, [range(5), range(5, 10), range(10, 15)]
        )

        reader = RecordBatchStreamReader.open_buffer(data)
        all_ids = []
        for batch in reader:  # uses __iter__
            for row in range(batch.num_rows):
                all_ids.append(batch.get_int32(0, row))
        reader.close()

        assert all_ids == list(range(15))
        schema.release()

    def test_empty_stream(self):
        """
        title: Ensure an empty stream yields no batches.
        """
        schema = make_simple_schema()
        writer = RecordBatchStreamWriter.open_buffer(schema)
        writer.close()
        data = writer.buffer_data()
        writer.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        assert reader.next_batch() is None
        reader.close()
        schema.release()

    def test_context_manager(self):
        """
        title: Ensure the writer and reader work as context managers.
        """
        schema = make_simple_schema()
        with RecordBatchStreamWriter.open_buffer(schema) as writer:
            builder = RecordBatchBuilder(schema)
            builder.append_int32(0, 99)
            builder.append_float64(1, 99.0)
            batch = builder.finish()
            writer.write_batch(batch)
            batch.release()
            builder.release()
            writer.close()
            data = writer.buffer_data()

        reader = RecordBatchStreamReader.open_buffer(data)
        batch = reader.next_batch()
        assert batch is not None
        assert batch.get_int32(0, 0) == PYARROW_CONTEXT_MANAGER_INT32_VALUE
        batch.release()
        reader.close()
        schema.release()


# Stream writer / reader round-trip — file


class TestFileRoundTrip:
    def test_file_round_trip(self, tmp_path: Path) -> None:
        """
        title: Ensure file-based streams round-trip correctly.
        parameters:
          tmp_path:
            type: Path
        """
        path = tmp_path / "test.arrows"
        schema = make_simple_schema()

        writer = RecordBatchStreamWriter.open_file(schema, path)
        builder = RecordBatchBuilder(schema)
        for i in range(20):
            builder.append_int32(0, i)
            builder.append_float64(1, i * 0.5)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        writer.release()

        assert path.exists()
        assert path.stat().st_size > 0

        reader = RecordBatchStreamReader.open_file(str(path))
        rb = reader.next_batch()
        assert rb is not None
        assert rb.num_rows == BATCH_ROW_COUNT_LARGE
        for i in range(BATCH_ROW_COUNT_LARGE):
            assert rb.get_int32(0, i) == i
            assert math.isclose(rb.get_float64(1, i), i * 0.5)
        rb.release()
        assert reader.next_batch() is None
        reader.close()
        schema.release()

    def test_missing_file_raises(self):
        """
        title: Ensure opening a missing file raises a runtime error.
        """
        with pytest.raises(RuntimeError):
            RecordBatchStreamReader.open_file("/nonexistent/path.arrows")


# Large batch stress test


class TestLargeBatch:
    @pytest.mark.parametrize("n", [1_000, 100_000])
    def test_large_batch(self, n: int) -> None:
        """
        title: Ensure large batches can be written and read back.
        parameters:
          n:
            type: int
        """
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT64)
        schema.add_field("y", IrxColumnType.FLOAT64)

        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        for i in range(n):
            builder.append_int64(0, i)
            builder.append_float64(1, i * 3.14)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.num_rows == n
        assert rb.get_int64(0, n - 1) == n - 1
        assert math.isclose(
            rb.get_float64(1, n - 1), (n - 1) * 3.14, rel_tol=1e-9
        )
        rb.release()
        reader.close()
        schema.release()


# PyArrow IPC interop — the core ecosystem-compatibility guarantee


class TestPyArrowInterop:
    """
    title: TestPyArrowInterop.
    """

    def test_irx_buffer_read_by_pyarrow(self):
        """
        title: Ensure PyArrow can read IRx-written IPC bytes.
        """
        schema = make_simple_schema()  # id INT32 non-null, value FLOAT64 null
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        for i in range(5):
            builder.append_int32(0, i)
            if i % 2 == 0:
                builder.append_float64(1, i * 1.5)
            else:
                builder.append_null(1)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        # PyArrow consumes the IRx-produced IPC bytes directly.
        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()

        assert table.num_rows == PYARROW_ROW_COUNT
        assert table.column_names == ["id", "value"]
        assert table.schema.field("id").type == pa.int32()
        assert table.schema.field("value").type == pa.float64()
        assert table.column("id").to_pylist() == [0, 1, 2, 3, 4]
        assert table.column("value").to_pylist() == [0.0, None, 3.0, None, 6.0]

    def test_pyarrow_buffer_read_by_irx(self):
        """
        title: Ensure the IRx reader can import PyArrow-written IPC bytes.
        """
        pa_schema = pa.schema(
            [
                pa.field("id", pa.int32(), nullable=False),
                pa.field("value", pa.float64(), nullable=True),
            ]
        )
        record_batch = pa.record_batch(
            [
                pa.array([10, 20, 30], type=pa.int32()),
                pa.array([1.5, None, 4.5], type=pa.float64()),
            ],
            schema=pa_schema,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, pa_schema) as pa_writer:
            pa_writer.write_batch(record_batch)
        data = sink.getvalue().to_pybytes()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.num_rows == PYARROW_BATCH_ROW_COUNT
        assert rb.num_columns == PYARROW_BATCH_COLUMN_COUNT
        assert rb.get_int32(0, 0) == PYARROW_FIRST_INT32_VALUE
        assert rb.get_int32(0, 2) == PYARROW_LAST_INT32_VALUE
        assert math.isclose(rb.get_float64(1, 0), 1.5)
        assert rb.is_null(1, 1) is True
        assert math.isclose(rb.get_float64(1, 2), 4.5)
        rb.release()
        assert reader.next_batch() is None
        reader.close()

    def test_irx_pyarrow_all_numeric_types(self):
        """
        title: >-
          Ensure fixed-width numeric types survive the IRx to PyArrow trip.
        """
        schema = RecordBatchSchema()
        schema.add_field("i8", IrxColumnType.INT8)
        schema.add_field("u32", IrxColumnType.UINT32)
        schema.add_field("f32", IrxColumnType.FLOAT32)
        schema.add_field("b", IrxColumnType.BOOL)

        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        builder.append_int8(0, -5)
        builder.append_uint32(1, 4_000_000_000)
        builder.append_float32(2, 1.25)
        builder.append_bool(3, True)
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
        assert table.schema.field("i8").type == pa.int8()
        assert table.schema.field("u32").type == pa.uint32()
        assert table.schema.field("f32").type == pa.float32()
        assert table.schema.field("b").type == pa.bool_()
        assert table.column("i8").to_pylist() == [-5]
        assert table.column("u32").to_pylist() == [4_000_000_000]
        assert math.isclose(table.column("f32").to_pylist()[0], 1.25)
        assert table.column("b").to_pylist() == [True]


# UTF-8 string types — utf8 and large_utf8


class TestStringTypes:
    """
    title: TestStringTypes.
    """

    def test_build_and_inspect_utf8(self):
        """
        title: Build a utf8 column and read the values back.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.UTF8, nullable=False)
        builder = RecordBatchBuilder(schema)
        words = ["alpha", "", "gamma"]
        for w in words:
            builder.append_string(0, w)
        batch = builder.finish()
        assert batch.num_rows == len(words)
        for i, w in enumerate(words):
            assert batch.get_string(0, i) == w
        batch.release()
        builder.release()
        schema.release()

    def test_unicode_round_trip(self):
        """
        title: Ensure multi-byte UTF-8 survives a byte-length round-trip.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.UTF8, nullable=False)
        builder = RecordBatchBuilder(schema)
        words = ["héllo", "日本語", "😀🎉"]
        for w in words:
            builder.append_string(0, w)
        batch = builder.finish()
        for i, w in enumerate(words):
            assert batch.get_string(0, i) == w
        batch.release()
        builder.release()
        schema.release()

    def test_string_nulls(self):
        """
        title: Ensure null slots in a string column read back as null.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.UTF8, nullable=True)
        builder = RecordBatchBuilder(schema)
        builder.append_string(0, "present")
        builder.append_null(0)
        builder.append_string(0, "again")
        batch = builder.finish()
        assert batch.is_null(0, 0) is False
        assert batch.is_null(0, 1) is True
        assert batch.get_string(0, 0) == "present"
        assert batch.get_string(0, 2) == "again"
        batch.release()
        builder.release()
        schema.release()

    def test_large_utf8(self):
        """
        title: Ensure the large_utf8 (64-bit offset) column works.
        """
        schema = RecordBatchSchema()
        schema.add_field("s", IrxColumnType.LARGE_UTF8, nullable=False)
        builder = RecordBatchBuilder(schema)
        words = ["one", "two", "three"]
        for w in words:
            builder.append_string(0, w)
        batch = builder.finish()
        for i, w in enumerate(words):
            assert batch.get_string(0, i) == w
        batch.release()
        builder.release()
        schema.release()

    def test_wrong_column_type_raises(self):
        """
        title: Ensure appending a string to a numeric column is rejected.
        """
        schema = RecordBatchSchema()
        schema.add_field("n", IrxColumnType.INT32, nullable=False)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError):
            builder.append_string(0, "nope")
        builder.release()
        schema.release()

    def test_buffer_round_trip(self):
        """
        title: Ensure string columns survive an in-memory stream round-trip.
        """
        schema = RecordBatchSchema()
        schema.add_field("name", IrxColumnType.UTF8, nullable=True)
        schema.add_field("tag", IrxColumnType.LARGE_UTF8, nullable=False)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        names = ["ann", None, "cat"]
        for i, nm in enumerate(names):
            if nm is None:
                builder.append_null(0)
            else:
                builder.append_string(0, nm)
            builder.append_string(1, f"t{i}")
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        for i, nm in enumerate(names):
            if nm is None:
                assert rb.is_null(0, i) is True
            else:
                assert rb.get_string(0, i) == nm
            assert rb.get_string(1, i) == f"t{i}"
        rb.release()
        reader.close()
        schema.release()

    def test_irx_strings_read_by_pyarrow(self):
        """
        title: Ensure PyArrow reads IRx-written utf8 and large_utf8 columns.
        """
        schema = RecordBatchSchema()
        schema.add_field("name", IrxColumnType.UTF8, nullable=True)
        schema.add_field("tag", IrxColumnType.LARGE_UTF8, nullable=False)
        writer = RecordBatchStreamWriter.open_buffer(schema)
        builder = RecordBatchBuilder(schema)
        builder.append_string(0, "x")
        builder.append_null(0)
        builder.append_string(1, "a")
        builder.append_string(1, "b")
        batch = builder.finish()
        writer.write_batch(batch)
        batch.release()
        builder.release()
        writer.close()
        data = writer.buffer_data()
        writer.release()
        schema.release()

        table = pa.ipc.open_stream(pa.py_buffer(data)).read_all()
        assert table.schema.field("name").type == pa.utf8()
        assert table.schema.field("tag").type == pa.large_utf8()
        assert table.column("name").to_pylist() == ["x", None]
        assert table.column("tag").to_pylist() == ["a", "b"]

    def test_pyarrow_strings_read_by_irx(self):
        """
        title: Ensure the IRx reader imports PyArrow-written string columns.
        """
        pa_schema = pa.schema(
            [
                pa.field("name", pa.utf8(), nullable=True),
                pa.field("tag", pa.large_utf8(), nullable=False),
            ]
        )
        record_batch = pa.record_batch(
            [
                pa.array(["foo", None, "baz"], type=pa.utf8()),
                pa.array(["p", "q", "r"], type=pa.large_utf8()),
            ],
            schema=pa_schema,
        )
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, pa_schema) as pa_writer:
            pa_writer.write_batch(record_batch)
        data = sink.getvalue().to_pybytes()

        reader = RecordBatchStreamReader.open_buffer(data)
        rb = reader.next_batch()
        assert rb is not None
        assert rb.get_string(0, 0) == "foo"
        assert rb.is_null(0, 1) is True
        assert rb.get_string(0, 2) == "baz"
        assert rb.get_string(1, 0) == "p"
        assert rb.get_string(1, 2) == "r"
        rb.release()
        reader.close()
