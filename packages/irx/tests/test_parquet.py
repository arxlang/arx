"""
title: Parquet native interoperability and unified format session contracts.
"""

import ctypes
import os
import subprocess
import sys

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from irx import record_batch as rb
from irx.record_batch import (
    CSV,
    Parquet,
    RecordBatch,
    RecordBatchSchema,
    RecordBatchStreamReader,
    RecordBatchStreamWriter,
)
from pyarrow.cffi import ffi
from typeguard import TypeCheckError

from .test_arrow_interop import address, import_batch, native  # noqa: F401
from .test_dataframe_conversion import import_schema

FLAT_TYPES = [
    pa.int8(),
    pa.int16(),
    pa.int32(),
    pa.int64(),
    pa.uint8(),
    pa.uint16(),
    pa.uint32(),
    pa.uint64(),
    pa.float32(),
    pa.float64(),
    pa.bool_(),
    pa.string(),
    pa.large_string(),
    pa.date32(),
    pa.timestamp("ms"),
    pa.timestamp("us"),
    pa.timestamp("ns", tz="America/Sao_Paulo"),
    pa.time32("ms"),
    pa.time64("us"),
    pa.time64("ns"),
]


def export_batch(native: ctypes.CDLL, batch: RecordBatch) -> pa.RecordBatch:
    """
    title: >-
      Export an independent Arrow snapshot for exact interoperability checks.
    parameters:
      native:
        type: ctypes.CDLL
      batch:
        type: RecordBatch
    returns:
      type: pa.RecordBatch
    """
    array = ffi.new("struct ArrowArray *")
    schema = ffi.new("struct ArrowSchema *")
    assert (
        native.irx_rb_batch_export(
            batch._handle, address(array), address(schema)
        )
        == 0
    )
    return pa.RecordBatch._import_from_c(address(array), address(schema))


@pytest.mark.parametrize("type_", FLAT_TYPES, ids=str)
def test_parquet_exact_types(
    native: ctypes.CDLL, tmp_path: Path, type_: pa.DataType
) -> None:
    """
    title: Preserve all supported types, nulls, field metadata and timezones.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      type_:
        type: pa.DataType
    """
    batch_size = 2
    values: list[object] = [0, None, 1, 2, 3]
    if pa.types.is_boolean(type_):
        values = [False, None, True, False, True]
    elif pa.types.is_string(type_) or pa.types.is_large_string(type_):
        values = ["", None, "λ", "embedded\0nul", "multiline\ntext"]
    schema = pa.schema(
        [pa.field("value", type_, metadata={b"field": b"\0\xff"})],
        metadata={b"schema": b"preserved"},
    )
    expected = pa.table([pa.array(values, type=type_)], schema=schema)
    path = tmp_path / "input.parquet"
    output = tmp_path / "output.parquet"
    pq.write_table(expected, path, row_group_size=2, version="2.6")
    with Parquet() as source, Parquet() as target:
        source.open_read(path, batch_size=batch_size)
        snapshot = source.schema()
        target.open_write(output, snapshot, row_group_size=3)
        snapshot.release()
        copied: list[pa.RecordBatch] = []
        while (batch := source.next_batch()) is not None:
            assert batch.num_rows <= batch_size
            target.write_batch(batch)
            copied.append(export_batch(native, batch))
            batch.release()
        assert source.next_batch() is None
        assert pa.Table.from_batches(copied).equals(
            expected, check_metadata=True
        )
    assert pq.read_table(output).equals(expected, check_metadata=True)
    file = pq.ParquetFile(output)
    assert file.metadata.format_version == "2.6"
    assert [
        file.metadata.row_group(i).num_rows for i in range(file.num_row_groups)
    ] == [3, 2]


@pytest.mark.parametrize("codec", ["snappy", "uncompressed", "zstd"])
def test_parquet_empty_and_schema_ownership(
    tmp_path: Path, codec: str
) -> None:
    """
    title: Empty output retains its schema and snapshots survive closed owners.
    parameters:
      tmp_path:
        type: Path
      codec:
        type: str
    """
    schema = RecordBatchSchema().add_field("id", rb.IrxColumnType.INT64, False)
    path = tmp_path / "empty.parquet"
    file = Parquet()
    file.open_write(path, schema, compression=codec)
    schema.release()
    snapshot = file.schema()
    file.close()
    file.close()
    assert snapshot.num_fields == 1
    file.open_read(path, schema=snapshot)
    inferred = file.schema()
    assert file.next_batch() is None
    file.close()
    assert inferred.num_fields == 1
    assert pq.ParquetFile(path).num_row_groups == 0
    assert pq.read_schema(path) == pa.schema(
        [pa.field("id", pa.int64(), False)]
    )
    snapshot.release()
    inferred.release()


@pytest.mark.parametrize(
    "type_", [pa.date64(), pa.timestamp("s"), pa.time32("s")]
)
def test_reject_temporal_normalization_before_truncation(
    native: ctypes.CDLL, tmp_path: Path, type_: pa.DataType
) -> None:
    """
    title: Reject coercing types and clear output slots before touching output.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      type_:
        type: pa.DataType
    """
    path = tmp_path / "sentinel"
    path.write_bytes(b"untouched")
    schema = import_schema(native, pa.schema([pa.field("bad", type_)]))
    out = ctypes.c_void_p(123)
    try:
        assert (
            native.irx_rb_parquet_writer_open(
                schema, os.fsencode(path), b"snappy", 100, ctypes.byref(out)
            )
            < 0
        )
        assert out.value is None
        message = native.irx_record_batch_errmsg().decode()
        assert "bad" in message and str(type_) in message
        assert "implicit coercion" in message
        assert path.read_bytes() == b"untouched"
    finally:
        native.irx_rb_schema_release(schema)


@pytest.mark.parametrize(
    "type_",
    [
        pa.binary(),
        pa.decimal128(10, 2),
        pa.list_(pa.int32()),
        pa.struct([("x", pa.int32())]),
        pa.null(),
    ],
)
def test_newly_supported_read_schema(
    tmp_path: Path, type_: pa.DataType
) -> None:
    """
    title: Read former exclusions through the owned recursive schema interface.
    parameters:
      tmp_path:
        type: Path
      type_:
        type: pa.DataType
    """
    path = tmp_path / "unsupported.parquet"
    pq.write_table(
        pa.table([pa.array([None], type=type_)], names=["bad"]), path
    )
    with Parquet() as file:
        file.open_read(path)
        schema = file.schema()
        assert schema.to_arrow().field("bad").type == type_
        schema.release()
        batch = file.next_batch()
        assert batch is not None
        assert batch.to_arrow().num_rows == 1
        batch.release()


@pytest.mark.parametrize("value", [0, -1, True, 2**63, "10", 1.5, None])
def test_invalid_sizes(tmp_path: Path, value: object) -> None:
    """
    title: >-
      Validate size types and bounds before ctypes truncation or file access.
    parameters:
      tmp_path:
        type: Path
      value:
        type: object
    """
    schema = RecordBatchSchema().add_field("id", rb.IrxColumnType.INT64)
    path = tmp_path / "sentinel"
    path.write_bytes(b"original")
    with Parquet() as file:
        with pytest.raises((ValueError, TypeCheckError)):
            file.open_read(path, batch_size=value)  # type: ignore[arg-type]
        with pytest.raises((ValueError, TypeCheckError)):
            file.open_write(path, schema, row_group_size=value)  # type: ignore[arg-type]
    assert path.read_bytes() == b"original"
    schema.release()


@pytest.mark.parametrize("format_", [CSV, Parquet])
def test_unified_modes_and_reopen(
    tmp_path: Path, format_: type[CSV] | type[Parquet]
) -> None:
    """
    title: >-
      Enforce one active mode, shared aliases and reusable successful close.
    parameters:
      tmp_path:
        type: Path
      format_:
        type: type[CSV] | type[Parquet]
    """
    schema = RecordBatchSchema().add_field("id", rb.IrxColumnType.INT64)
    path = tmp_path / "data"
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"unchanged")
    file = format_()
    alias = file
    with pytest.raises(RuntimeError, match="closed"):
        file.schema()
    file.open_write(path, schema)
    with pytest.raises(RuntimeError, match="requires read"):
        file.next_batch()
    with pytest.raises(RuntimeError, match="requires closed"):
        file.open_write(sentinel, schema)
    with pytest.raises(RuntimeError, match="requires closed"):
        file.open_read(sentinel)
    assert sentinel.read_bytes() == b"unchanged"
    alias.close()
    assert file.mode == "closed"
    # CSV needs an explicit schema for a header-only file.
    file.open_read(path, schema=schema)
    assert file.next_batch() is None
    with pytest.raises(RuntimeError, match="requires write"):
        file.write_batch(RecordBatch(ctypes.c_void_p(), rb._get_lib()))
    file.close()
    file.open_write(path, schema)
    file.close()
    schema.release()


@pytest.mark.parametrize(
    "changed", ["type", "name", "nullability", "metadata"]
)
def test_exact_expected_schema(tmp_path: Path, changed: str) -> None:
    """
    title: >-
      Expected Parquet schemas assert types and metadata without conversion.
    parameters:
      tmp_path:
        type: Path
      changed:
        type: str
    """
    path = tmp_path / "data.parquet"
    kwargs = (
        {"metadata": {b"custom": b"value"}} if changed == "metadata" else {}
    )
    dtype = pa.int32() if changed == "type" else pa.int64()
    schema = pa.schema(
        [
            pa.field(
                "other" if changed == "name" else "id",
                dtype,
                changed != "nullability",
            )
        ],
        **kwargs,
    )
    pq.write_table(pa.table([pa.array([1], type=dtype)], schema=schema), path)
    expected = RecordBatchSchema().add_field("id", rb.IrxColumnType.INT64)
    with pytest.raises(RuntimeError, match="schema mismatch"):
        RecordBatchStreamReader.open_parquet(path, schema=expected)
    expected.release()


def test_retained_batch_and_schema(
    native: ctypes.CDLL, tmp_path: Path
) -> None:
    """
    title: Schema and data snapshots survive reader closure and writer release.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    path = tmp_path / "data.parquet"
    expected = pa.table({"id": [1, None]})
    pq.write_table(expected, path)
    with RecordBatchStreamReader.open_parquet(path) as reader:
        batch = reader.next_batch()
        schema = reader.schema()
    assert batch is not None
    assert export_batch(native, batch).equals(expected.to_batches()[0])
    with RecordBatchStreamWriter.open_parquet(
        schema, tmp_path / "copy.parquet"
    ) as writer:
        schema.release()
        writer.write_batch(batch)
    batch.release()


def test_native_stream_transfer(native: ctypes.CDLL, tmp_path: Path) -> None:
    """
    title: >-
      Exported readers own the parent Parquet reader and random-access file.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    path = tmp_path / "data.parquet"
    expected = pa.table({"id": range(100)})
    pq.write_table(expected, path, row_group_size=7)
    handle = ctypes.c_void_p()
    assert (
        native.irx_rb_parquet_reader_open(
            os.fsencode(path), None, 3, ctypes.byref(handle)
        )
        == 0
    )
    stream = ffi.new("struct ArrowArrayStream *")
    assert native.irx_rb_stream_reader_export(handle, address(stream)) == 0
    native.irx_rb_stream_reader_close(handle)
    reader = pa.RecordBatchReader._import_from_c(address(stream))
    assert reader.read_all().equals(expected)
    reader.close()


def test_nonnullable_actual_nulls(native: ctypes.CDLL, tmp_path: Path) -> None:
    """
    title: Reject physical nulls despite a non-nullable schema declaration.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    schema = pa.schema([pa.field("id", pa.int64(), False)])
    handle = import_batch(
        native,
        pa.record_batch([pa.array([None], type=pa.int64())], schema=schema),
    )
    schema_handle = import_schema(native, schema)
    writer = ctypes.c_void_p()
    try:
        assert (
            native.irx_rb_parquet_writer_open(
                schema_handle,
                os.fsencode(tmp_path / "bad.parquet"),
                b"snappy",
                10,
                ctypes.byref(writer),
            )
            == 0
        )
        assert native.irx_rb_stream_writer_write_batch(writer, handle) < 0
        assert b"contains nulls" in native.irx_record_batch_errmsg()
    finally:
        native.irx_rb_stream_writer_release(writer)
        native.irx_rb_schema_release(schema_handle)
        native.irx_rb_batch_release(handle)


def test_failed_session_and_exception_cleanup(tmp_path: Path) -> None:
    """
    title: >-
      Preserve the first write failure and forbid reopening failed sessions.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "input.parquet"
    pq.write_table(pa.table({"other": [1]}), path)
    schema = RecordBatchSchema().add_field("id", rb.IrxColumnType.INT64)
    file = Parquet()
    with pytest.raises(RuntimeError, match="schema mismatch"):
        with file, Parquet() as source:
            source.open_read(path)
            file.open_write(tmp_path / "output.parquet", schema)
            for batch in source:
                file.write_batch(batch)
    assert file.mode == "failed"
    assert file.writer is None
    with pytest.raises(RuntimeError, match="File session failed"):
        file.close()
    with pytest.raises(RuntimeError, match="current mode is failed"):
        file.open_read(path)
    schema.release()


def test_invalid_paths_options_and_corruption(tmp_path: Path) -> None:
    """
    title: >-
      Errors during open leave the owner closed and validation is
      nondestructive.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "data"
    schema = RecordBatchSchema().add_field("id", rb.IrxColumnType.INT64)
    with Parquet() as file:
        for candidate in [path, tmp_path]:
            with pytest.raises(RuntimeError):
                file.open_read(candidate)
        with pytest.raises(ValueError, match="NUL"):
            file.open_read("bad\0path")
        if os.name != "nt":
            with pytest.raises(RuntimeError, match="RecordBatch error"):
                file.open_read(tmp_path / "bad\udcff")
        path.write_bytes(b"not parquet")
        with pytest.raises(RuntimeError):
            file.open_read(path)
        for codec in ["unknown", "", "snappy\0junk"]:
            with pytest.raises(ValueError, match="compression"):
                file.open_write(path, schema, compression=codec)
        assert path.read_bytes() == b"not parquet"
    schema.release()


def test_missing_optional_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    title: >-
      Old overrides report actionable errors only when Parquet is requested.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.setattr(rb, "_get_lib", object)
    with Parquet() as file:
        with pytest.raises(
            RuntimeError, match="lacks Parquet support; rebuild"
        ):
            file.open_read("unopened.parquet")


@pytest.mark.skipif(
    sys.platform != "linux", reason="Linux file-size limit fault injection"
)
def test_footer_failure_is_sticky(tmp_path: Path) -> None:
    """
    title: >-
      Real finalization failures are not reported as successful repeated close.
    parameters:
      tmp_path:
        type: Path
    """
    script = """
import resource, signal, sys
from irx.record_batch import IrxColumnType, RecordBatchSchema, Parquet
schema = RecordBatchSchema().add_field("id", IrxColumnType.INT64)
f = Parquet()
f.open_write(sys.argv[1], schema)
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (8, 8))
for attempt in range(2):
    try:
        f.close()
    except RuntimeError:
        pass
    else:
        raise AssertionError("footer failure was hidden")
assert f.mode == "failed" and f.writer is None
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "full.parquet")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("codec", ["snappy", "uncompressed", "zstd"])
def test_codec_properties_and_zero_row_write(
    tmp_path: Path, codec: str
) -> None:
    """
    title: >-
      Compression applies to real row groups and empty batches are harmless.
    parameters:
      tmp_path:
        type: Path
      codec:
        type: str
    """
    schema = RecordBatchSchema().add_field("id", rb.IrxColumnType.INT64)
    builder = rb.RecordBatchBuilder(schema)
    empty = builder.finish()
    builder.append_int64(0, 42)
    batch = builder.finish()
    path = tmp_path / "codec.parquet"
    with Parquet() as file:
        file.open_write(path, schema, compression=codec)
        file.write_batch(empty)
        file.write_batch(batch)
    metadata = pq.ParquetFile(path).metadata
    assert metadata.row_group(0).column(0).compression == codec.upper()
    assert pq.read_table(path).column(0).to_pylist() == [42]
    batch.release()
    empty.release()
    builder.release()
    schema.release()


@pytest.mark.parametrize(
    "case", ["empty", "duplicate", "reserved", "empty-name"]
)
def test_schema_validation_precedes_truncation(
    native: ctypes.CDLL, tmp_path: Path, case: str
) -> None:
    """
    title: >-
      Reject invalid schemas and metadata without modifying an existing file.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      case:
        type: str
    """
    field = pa.field("id", pa.int64())
    schemas = {
        "empty": pa.schema([]),
        "duplicate": pa.schema([field, field]),
        "reserved": pa.schema(
            [field], metadata={b"ARROW:schema": b"collision"}
        ),
        "empty-name": pa.schema([pa.field("", pa.int64())]),
    }
    schema = import_schema(native, schemas[case])
    path = tmp_path / "sentinel"
    path.write_bytes(b"original")
    writer = ctypes.c_void_p(123)
    try:
        assert (
            native.irx_rb_parquet_writer_open(
                schema, os.fsencode(path), b"snappy", 1, ctypes.byref(writer)
            )
            < 0
        )
        assert writer.value is None
        assert native.irx_record_batch_errmsg()
        assert path.read_bytes() == b"original"
    finally:
        native.irx_rb_schema_release(schema)


def test_snapshot_rebuild_preserves_timezone(
    native: ctypes.CDLL, tmp_path: Path
) -> None:
    """
    title: >-
      Reader schema snapshots are usable by builders without losing timezones.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    type_ = pa.timestamp("ns", tz="America/Sao_Paulo")
    schema = pa.schema(
        [pa.field("when", type_, metadata={b"field": b"kept"})],
        metadata={b"schema": b"kept"},
    )
    path = tmp_path / "time.parquet"
    pq.write_table(pa.table([pa.array([], type=type_)], schema=schema), path)
    with Parquet() as source:
        source.open_read(path)
        snapshot = source.schema()
    builder = rb.RecordBatchBuilder(snapshot)
    snapshot.release()
    builder.append_timestamp(0, 123456789)
    batch = builder.finish()
    actual = export_batch(native, batch)
    assert actual.schema.equals(schema, check_metadata=True)
    assert actual.column(0).cast(pa.int64()).to_pylist() == [123456789]
    batch.release()
    builder.release()


def test_late_corruption_is_not_eof(tmp_path: Path) -> None:
    """
    title: >-
      Corrupt later pages fail after valid batches instead of ending silently.
    parameters:
      tmp_path:
        type: Path
    """
    path = tmp_path / "corrupt.parquet"
    expected = pa.table({"id": range(40)})
    pq.write_table(
        expected,
        path,
        row_group_size=20,
        compression="snappy",
        use_dictionary=False,
    )
    with pq.ParquetFile(path) as file:
        column = file.metadata.row_group(1).column(0)
        offset = column.data_page_offset
        size = column.total_compressed_size
    with path.open("r+b") as file:
        file.seek(offset)
        file.write(b"\xff" * size)
    source = Parquet()
    source.open_read(path, batch_size=20)
    first = source.next_batch()
    assert first is not None and first.get_int64(0, 0) == 0
    first.release()
    with pytest.raises(RuntimeError):
        source.next_batch()
    assert source.mode == "failed" and source.reader is None


def test_plain_external_schema_and_float_specials(tmp_path: Path) -> None:
    """
    title: >-
      Read ordinary Parquet without embedded Arrow schema and preserve IEEE
      values.
    parameters:
      tmp_path:
        type: Path
    """
    import math  # noqa: PLC0415

    path = tmp_path / "external.parquet"
    pq.write_table(
        pa.table(
            {"value": [float("inf"), float("-inf"), float("nan"), -0.0, None]}
        ),
        path,
        store_schema=False,
    )
    with Parquet() as source, Parquet() as target:
        source.open_read(path)
        snapshot = source.schema()
        target.open_write(tmp_path / "copy.parquet", snapshot)
        snapshot.release()
        for batch in source:
            target.write_batch(batch)
    values = pq.read_table(tmp_path / "copy.parquet").column(0).to_pylist()
    assert values[0] == float("inf") and values[1] == float("-inf")
    assert math.isnan(values[2])
    assert math.copysign(1.0, values[3]) == -1.0
    assert values[4] is None
