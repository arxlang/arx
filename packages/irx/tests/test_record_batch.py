"""
tests/builder/runtime/test_record_batch.py

Integration tests for RecordBatch streaming via the Arrow C++ bridge.

These tests run the full native path:
  Python API → ctypes → libirx_record_batch.so → Arrow C++ → IPC bytes

They are skipped automatically when the native library has not been compiled
(e.g. in documentation-only CI jobs).
"""

from __future__ import annotations

import math

import pyarrow as pa
import pytest

# ---------------------------------------------------------------------------
# Skip guard — skip all tests when the native lib is unavailable
# ---------------------------------------------------------------------------

try:
    from irx.record_batch import (
        IrxColumnType,
        RecordBatchBuilder,
        RecordBatchSchema,
        RecordBatchStreamReader,
        RecordBatchStreamWriter,
        _get_lib,
    )

    _get_lib()  # trigger load; raises if lib not found
    _NATIVE_AVAILABLE = True
except Exception:
    _NATIVE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _NATIVE_AVAILABLE,
    reason="IRx native library not compiled; skipping record_batch tests",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_simple_schema() -> RecordBatchSchema:
    """Schema with one INT32 column and one FLOAT64 column."""
    schema = RecordBatchSchema()
    schema.add_field("id", IrxColumnType.INT32, nullable=False)
    schema.add_field("value", IrxColumnType.FLOAT64, nullable=True)
    return schema


def fill_builder(builder: RecordBatchBuilder, n: int) -> None:
    """Append n rows: id=i, value=i*1.5."""
    for i in range(n):
        builder.append_int32(0, i)
        builder.append_float64(1, i * 1.5)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchema:
    def test_empty_schema(self):
        s = RecordBatchSchema()
        assert s.num_fields == 0
        s.release()

    def test_add_fields(self):
        s = RecordBatchSchema()
        s.add_field("a", IrxColumnType.INT32)
        s.add_field("b", IrxColumnType.FLOAT64, nullable=False)
        assert s.num_fields == 2
        s.release()

    def test_all_types(self):
        s = RecordBatchSchema()
        for ct in IrxColumnType:
            s.add_field(ct.name.lower(), ct)
        assert s.num_fields == len(IrxColumnType)
        s.release()

    def test_double_release_is_safe(self):
        s = RecordBatchSchema()
        s.release()
        s.release()  # must not crash


# ---------------------------------------------------------------------------
# Builder / batch tests
# ---------------------------------------------------------------------------


class TestBuilder:
    def test_build_and_inspect(self):
        schema = make_simple_schema()
        builder = RecordBatchBuilder(schema)
        fill_builder(builder, 4)
        batch = builder.finish()

        assert batch.num_rows == 4
        assert batch.num_columns == 2

        for i in range(4):
            assert batch.get_int32(0, i) == i
            assert math.isclose(batch.get_float64(1, i), i * 1.5)

        batch.release()
        builder.release()
        schema.release()

    def test_null_values(self):
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32, nullable=True)
        builder = RecordBatchBuilder(schema)
        builder.append_int32(0, 42)
        builder.append_null(0)
        builder.append_int32(0, 7)
        batch = builder.finish()

        assert batch.is_null(0, 0) is False
        assert batch.is_null(0, 1) is True
        assert batch.is_null(0, 2) is False
        assert batch.get_int32(0, 0) == 42
        assert batch.get_int32(0, 2) == 7

        batch.release()
        builder.release()
        schema.release()

    def test_bool_column(self):
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
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="out of bounds"):
            builder.append_int32(99, 0)
        builder.release()
        schema.release()

    def test_type_mismatch_raises(self):
        schema = RecordBatchSchema()
        schema.add_field("x", IrxColumnType.INT32)
        builder = RecordBatchBuilder(schema)
        with pytest.raises(RuntimeError, match="type mismatch"):
            builder.append_float64(0, 3.14)
        builder.release()
        schema.release()

    def test_empty_batch(self):
        schema = make_simple_schema()
        builder = RecordBatchBuilder(schema)
        batch = builder.finish()
        assert batch.num_rows == 0
        batch.release()
        builder.release()
        schema.release()


# ---------------------------------------------------------------------------
# Stream writer / reader round-trip — in-memory buffer
# ---------------------------------------------------------------------------


class TestBufferRoundTrip:
    def _write_batches(self, schema, batches_data):
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
        schema = make_simple_schema()
        data = self._write_batches(schema, [range(10)])

        reader = RecordBatchStreamReader.open_buffer(data)
        batch = reader.next_batch()
        assert batch is not None
        assert batch.num_rows == 10
        for i in range(10):
            assert batch.get_int32(0, i) == i
            assert math.isclose(batch.get_float64(1, i), float(i))
        batch.release()

        assert reader.next_batch() is None  # EOF
        reader.close()
        schema.release()

    def test_multiple_batches_round_trip(self):
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
        assert batch.get_int32(0, 0) == 99
        batch.release()
        reader.close()
        schema.release()


# ---------------------------------------------------------------------------
# Stream writer / reader round-trip — file
# ---------------------------------------------------------------------------


class TestFileRoundTrip:
    def test_file_round_trip(self, tmp_path):
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
        assert rb.num_rows == 20
        for i in range(20):
            assert rb.get_int32(0, i) == i
            assert math.isclose(rb.get_float64(1, i), i * 0.5)
        rb.release()
        assert reader.next_batch() is None
        reader.close()
        schema.release()

    def test_missing_file_raises(self):
        with pytest.raises(RuntimeError):
            RecordBatchStreamReader.open_file("/nonexistent/path.arrows")


# ---------------------------------------------------------------------------
# Large batch stress test
# ---------------------------------------------------------------------------


class TestLargeBatch:
    @pytest.mark.parametrize("n", [1_000, 100_000])
    def test_large_batch(self, n):
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


# ---------------------------------------------------------------------------
# PyArrow IPC interop — the core ecosystem-compatibility guarantee
# ---------------------------------------------------------------------------


class TestPyArrowInterop:
    """IRx emits standard Arrow IPC stream bytes; verify PyArrow reads them
    (and vice-versa), including null masks."""

    def test_irx_buffer_read_by_pyarrow(self):
        """IRx writes a stream buffer; PyArrow imports and matches values."""
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

        assert table.num_rows == 5
        assert table.column_names == ["id", "value"]
        assert table.schema.field("id").type == pa.int32()
        assert table.schema.field("value").type == pa.float64()
        assert table.column("id").to_pylist() == [0, 1, 2, 3, 4]
        assert table.column("value").to_pylist() == [0.0, None, 3.0, None, 6.0]

    def test_pyarrow_buffer_read_by_irx(self):
        """PyArrow writes an IPC stream; the IRx reader imports it back."""
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
        assert rb.num_rows == 3
        assert rb.num_columns == 2
        assert rb.get_int32(0, 0) == 10
        assert rb.get_int32(0, 2) == 30
        assert math.isclose(rb.get_float64(1, 0), 1.5)
        assert rb.is_null(1, 1) is True
        assert math.isclose(rb.get_float64(1, 2), 4.5)
        rb.release()
        assert reader.next_batch() is None
        reader.close()

    def test_irx_pyarrow_all_numeric_types(self):
        """Every supported fixed-width column survives the IRx -> PyArrow trip."""
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
