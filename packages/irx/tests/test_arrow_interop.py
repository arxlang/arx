"""
title: Native IPC and Arrow C interface interoperability contracts.
"""

import ctypes
import errno
import gc
import os

from pathlib import Path

import pyarrow as pa
import pytest

from irx.builder.runtime.record_batch import (
    _SIGNATURES,
    ensure_record_batch_shared_library,
)
from pyarrow.cffi import ffi

IRX_ERR_TYPE = -4


@pytest.fixture(scope="module")
def native() -> ctypes.CDLL:
    """
    title: Load current native code and bind its registered ABI signatures.
    returns:
      type: ctypes.CDLL
    """
    library = ctypes.CDLL(str(ensure_record_batch_shared_library()))
    types = {
        "p": ctypes.c_void_p,
        "v": None,
        "i8": ctypes.c_int8,
        "i16": ctypes.c_int16,
        "i32": ctypes.c_int32,
        "i64": ctypes.c_int64,
        "f32": ctypes.c_float,
        "f64": ctypes.c_double,
    }
    for name, (result, args) in _SIGNATURES.items():
        function = getattr(library, name)
        function.restype = types[result]
        function.argtypes = [types[arg] for arg in args]
    library.irx_record_batch_errmsg.restype = ctypes.c_char_p
    return library


def address(value: object) -> int:
    """
    title: Return a CFFI-owned struct address for ctypes and PyArrow.
    parameters:
      value:
        type: object
    returns:
      type: int
    """
    return int(ffi.cast("uintptr_t", value))


def import_batch(
    native: ctypes.CDLL, batch: pa.RecordBatch
) -> ctypes.c_void_p:
    """
    title: Move one PyArrow batch into the native ABI.
    parameters:
      native:
        type: ctypes.CDLL
      batch:
        type: pa.RecordBatch
    returns:
      type: ctypes.c_void_p
    """
    array = ffi.new("struct ArrowArray *")
    schema = ffi.new("struct ArrowSchema *")
    batch._export_to_c(address(array), address(schema))
    out = ctypes.c_void_p()
    assert (
        native.irx_rb_batch_import(
            address(array), address(schema), ctypes.byref(out)
        )
        == 0
    )
    assert array.release == ffi.NULL
    assert schema.release == ffi.NULL
    return out


def sample_batch() -> pa.RecordBatch:
    """
    title: Exercise slicing, nulls, UTF-8, timezone and binary metadata.
    returns:
      type: pa.RecordBatch
    """
    schema = pa.schema(
        [
            pa.field("id", pa.int64(), metadata={b"field": b"\x00\xff"}),
            pa.field("text", pa.string()),
            pa.field("when", pa.timestamp("us", tz="UTC")),
        ],
        metadata={b"schema": b"preserved"},
    )
    return pa.RecordBatch.from_arrays(
        [
            pa.array([0, 42, None]),
            pa.array(["prefix", "λ", None]),
            pa.array([0, 123, None], type=pa.timestamp("us", tz="UTC")),
        ],
        schema=schema,
    ).slice(1)


def test_c_data_lifetime_and_repeated_release(native: ctypes.CDLL) -> None:
    """
    title: Exported buffers survive original handles and guarded releases.
    parameters:
      native:
        type: ctypes.CDLL
    """
    expected = sample_batch()
    handle = import_batch(native, expected)
    array = ffi.new("struct ArrowArray *")
    schema = ffi.new("struct ArrowSchema *")
    assert (
        native.irx_rb_batch_export(handle, address(array), address(schema))
        == 0
    )
    native.irx_rb_batch_release(handle)
    gc.collect()
    result = pa.RecordBatch._import_from_c(address(array), address(schema))
    assert result.equals(expected, check_metadata=True)
    for _ in range(2):
        native.irx_rb_c_array_release(address(array))
        native.irx_rb_c_schema_release(address(schema))
    assert result.column(0).to_pylist() == [42, None]


def test_c_stream_callbacks_and_eos(native: ctypes.CDLL) -> None:
    """
    title: Schema and batch outputs outlive the stream and EOS is released.
    parameters:
      native:
        type: ctypes.CDLL
    """
    handle = import_batch(native, sample_batch())
    stream = ffi.new("struct ArrowArrayStream *")
    assert native.irx_rb_batch_export_stream(handle, address(stream)) == 0
    native.irx_rb_batch_release(handle)
    schema = ffi.new("struct ArrowSchema *")
    array = ffi.new("struct ArrowArray *")
    end = ffi.new("struct ArrowArray *")
    assert stream.get_schema(stream, schema) == 0
    assert stream.get_next(stream, array) == 0
    assert array.release != ffi.NULL
    for _ in range(2):
        assert stream.get_next(stream, end) == 0
        assert end.release == ffi.NULL
    for _ in range(2):
        native.irx_rb_c_stream_release(address(stream))
    assert stream.release == ffi.NULL
    result = pa.RecordBatch._import_from_c(address(array), address(schema))
    assert result.equals(sample_batch(), check_metadata=True)


def test_c_stream_import_move(native: ctypes.CDLL) -> None:
    """
    title: Imported streams own their producer and yield independent batches.
    parameters:
      native:
        type: ctypes.CDLL
    """
    expected = sample_batch()
    producer = pa.RecordBatchReader.from_batches(
        expected.schema, [expected.slice(0, 0), expected]
    )
    stream = ffi.new("struct ArrowArrayStream *")
    producer._export_to_c(address(stream))
    reader = ctypes.c_void_p()
    assert (
        native.irx_rb_stream_reader_import(
            address(stream), ctypes.byref(reader)
        )
        == 0
    )
    assert stream.release == ffi.NULL
    del producer
    gc.collect()
    for rows in (0, 2):
        batch = ctypes.c_void_p()
        assert (
            native.irx_rb_stream_reader_next_batch(reader, ctypes.byref(batch))
            == 0
        )
        assert native.irx_rb_batch_num_rows(batch) == rows
        native.irx_rb_batch_release(batch)
    end = ctypes.c_void_p()
    assert (
        native.irx_rb_stream_reader_next_batch(reader, ctypes.byref(end)) == 1
    )
    native.irx_rb_stream_reader_close(reader)


@pytest.mark.parametrize("file_format", [False, True])
def test_ipc_reader_export_preserves_metadata(
    native: ctypes.CDLL, tmp_path: Path, file_format: bool
) -> None:
    """
    title: Transfer IPC iteration to PyArrow without losing schema or buffers.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      file_format:
        type: bool
    """
    path = tmp_path / "input.arrow"
    expected = sample_batch()
    make_writer = pa.ipc.new_file if file_format else pa.ipc.new_stream
    with make_writer(str(path), expected.schema) as writer:
        writer.write_batch(expected)
        writer.write_batch(expected.slice(0, 0))
    reader = ctypes.c_void_p()
    open_reader = (
        native.irx_rb_file_reader_open
        if file_format
        else native.irx_rb_stream_reader_open_file
    )
    assert open_reader(str(path).encode(), ctypes.byref(reader)) == 0
    stream = ffi.new("struct ArrowArrayStream *")
    assert native.irx_rb_stream_reader_export(reader, address(stream)) == 0
    native.irx_rb_stream_reader_close(reader)
    result = pa.RecordBatchReader._import_from_c(address(stream))
    assert result.schema.equals(expected.schema, check_metadata=True)
    batches = list(result)
    assert [batch.num_rows for batch in batches] == [2, 0]
    assert batches[0].equals(expected, check_metadata=True)
    result.close()


@pytest.mark.parametrize("cut", [1, 8, 15])
def test_truncated_stream_is_not_eof(
    native: ctypes.CDLL, tmp_path: Path, cut: int
) -> None:
    """
    title: Missing EOS and interrupted payloads cannot appear successful.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      cut:
        type: int
    """
    expected = sample_batch()
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, expected.schema) as writer:
        writer.write_batch(expected)
    path = tmp_path / "cut.arrow"
    path.write_bytes(sink.getvalue().to_pybytes()[:-cut])
    reader = ctypes.c_void_p()
    assert (
        native.irx_rb_stream_reader_open_file(
            str(path).encode(), ctypes.byref(reader)
        )
        == 0
    )
    try:
        while True:
            batch = ctypes.c_void_p()
            status = native.irx_rb_stream_reader_next_batch(
                reader, ctypes.byref(batch)
            )
            if status != 0:
                assert status < 0
                assert not batch.value
                break
            native.irx_rb_batch_release(batch)
    finally:
        native.irx_rb_stream_reader_close(reader)


def test_unsupported_import_releases_adopted_buffers(
    native: ctypes.CDLL,
) -> None:
    """
    title: Unsupported C Data types fail with no live output or leaked buffer.
    parameters:
      native:
        type: ctypes.CDLL
    """
    batch = pa.record_batch([pa.array([b"bytes"])], names=["binary"])
    array = ffi.new("struct ArrowArray *")
    schema = ffi.new("struct ArrowSchema *")
    batch._export_to_c(address(array), address(schema))
    out = ctypes.c_void_p()
    assert (
        native.irx_rb_batch_import(
            address(array), address(schema), ctypes.byref(out)
        )
        == IRX_ERR_TYPE
    )
    assert not out.value
    assert array.release == ffi.NULL
    assert schema.release == ffi.NULL
    assert b"unsupported" in native.irx_record_batch_errmsg()


def test_builder_snapshot_preserves_timezone(native: ctypes.CDLL) -> None:
    """
    title: Builders own immutable schemas, including timestamp timezone types.
    parameters:
      native:
        type: ctypes.CDLL
    """
    expected_schema = pa.schema(
        [pa.field("when", pa.timestamp("us", tz="UTC"), nullable=False)],
        metadata={b"schema": b"owned"},
    )
    exported = ffi.new("struct ArrowSchema *")
    expected_schema._export_to_c(address(exported))
    schema = ctypes.c_void_p()
    assert (
        native.irx_rb_schema_import(address(exported), ctypes.byref(schema))
        == 0
    )
    builder = ctypes.c_void_p()
    assert native.irx_rb_builder_create(schema, ctypes.byref(builder)) == 0
    native.irx_rb_schema_release(schema)
    try:
        assert native.irx_rb_builder_append_null(builder, 0) == IRX_ERR_TYPE
        assert native.irx_rb_builder_append_timestamp(builder, 0, 123) == 0
        batch = ctypes.c_void_p()
        assert native.irx_rb_builder_finish(builder, ctypes.byref(batch)) == 0
    finally:
        native.irx_rb_builder_release(builder)
    array = ffi.new("struct ArrowArray *")
    assert (
        native.irx_rb_batch_export(batch, address(array), address(exported))
        == 0
    )
    native.irx_rb_batch_release(batch)
    result = pa.RecordBatch._import_from_c(address(array), address(exported))
    assert result.schema.equals(expected_schema, check_metadata=True)
    assert result.column(0).cast(pa.int64()).to_pylist() == [123]


def test_stream_error_callbacks_and_single_release(
    native: ctypes.CDLL,
) -> None:
    """
    title: Callback errors stay errors and imported producers release once.
    parameters:
      native:
        type: ctypes.CDLL
    """
    releases: list[bool] = []
    error = ffi.new("char[]", b"injected stream failure")
    schema = pa.schema([pa.field("id", pa.int64())])

    @ffi.callback("int(struct ArrowArrayStream *, struct ArrowSchema *)")
    def get_schema(stream: object, out: object) -> int:
        """
        title: Supply an owned schema from a test producer.
        parameters:
          stream:
            type: object
          out:
            type: object
        returns:
          type: int
        """
        schema._export_to_c(address(out))
        return 0

    @ffi.callback("int(struct ArrowArrayStream *, struct ArrowArray *)")
    def get_next(stream: object, out: object) -> int:
        """
        title: Inject a recoverable C Stream error.
        parameters:
          stream:
            type: object
          out:
            type: object
        returns:
          type: int
        """
        return errno.EIO

    @ffi.callback("const char *(struct ArrowArrayStream *)")
    def get_error(stream: object) -> object:
        """
        title: Keep callback error storage alive for the producer lifetime.
        parameters:
          stream:
            type: object
        returns:
          type: object
        """
        return error

    @ffi.callback("void(struct ArrowArrayStream *)")
    def release(stream: object) -> None:
        """
        title: Count ownership release and mark the C struct released.
        parameters:
          stream:
            type: object
        """
        releases.append(True)
        ffi.cast("struct ArrowArrayStream *", stream).release = ffi.NULL

    source = ffi.new("struct ArrowArrayStream *")
    source.get_schema, source.get_next = get_schema, get_next
    source.get_last_error, source.release = get_error, release
    reader = ctypes.c_void_p()
    assert (
        native.irx_rb_stream_reader_import(
            address(source), ctypes.byref(reader)
        )
        == 0
    )
    exported = ffi.new("struct ArrowArrayStream *")
    assert native.irx_rb_stream_reader_export(reader, address(exported)) == 0
    native.irx_rb_stream_reader_close(reader)
    out = ffi.new("struct ArrowArray *")
    assert exported.get_next(exported, out) != 0
    assert b"injected stream failure" in ffi.string(
        exported.get_last_error(exported)
    )
    assert out.release == ffi.NULL
    for _ in range(2):
        native.irx_rb_c_stream_release(address(exported))
    assert releases == [True]


def test_writer_rejects_metadata_mismatch(
    native: ctypes.CDLL, tmp_path: Path
) -> None:
    """
    title: Native writers do not silently rewrite batch schema metadata.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
    """
    expected = sample_batch()
    handle = import_batch(native, expected)
    schema = ctypes.c_void_p()
    assert native.irx_rb_batch_schema(handle, ctypes.byref(schema)) == 0
    writer = ctypes.c_void_p()
    assert (
        native.irx_rb_file_writer_open(
            schema,
            str(tmp_path / "mismatch.arrow").encode(),
            ctypes.byref(writer),
        )
        == 0
    )
    mismatched = import_batch(
        native, expected.replace_schema_metadata({b"new": b"value"})
    )
    try:
        assert (
            native.irx_rb_stream_writer_write_batch(writer, mismatched)
            == IRX_ERR_TYPE
        )
        assert native.irx_rb_stream_writer_write_batch(writer, handle) == 0
        assert native.irx_rb_stream_writer_close(writer) == 0
        assert native.irx_rb_stream_writer_close(writer) == 0
    finally:
        native.irx_rb_stream_writer_release(writer)
        native.irx_rb_schema_release(schema)
        native.irx_rb_batch_release(handle)
        native.irx_rb_batch_release(mismatched)


def test_pipe_reader_borrows_descriptor(native: ctypes.CDLL) -> None:
    """
    title: Byte transport reads pipes and closes only its duplicate descriptor.
    parameters:
      native:
        type: ctypes.CDLL
    """
    if os.name != "posix":
        pytest.skip("POSIX descriptors required")
    expected = pa.record_batch([pa.array([42])], names=["id"])
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, expected.schema) as writer:
        writer.write_batch(expected)
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, sink.getvalue().to_pybytes())
        os.close(write_fd)
        write_fd = -1
        reader = ctypes.c_void_p()
        assert native.irx_rb_fd_reader_open(read_fd, ctypes.byref(reader)) == 0
        batch = ctypes.c_void_p()
        assert (
            native.irx_rb_stream_reader_next_batch(reader, ctypes.byref(batch))
            == 0
        )
        native.irx_rb_stream_reader_close(reader)
        assert native.irx_rb_batch_num_rows(batch) == 1
        native.irx_rb_batch_release(batch)
        os.fstat(read_fd)
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)


@pytest.mark.parametrize("nested", [False, True])
def test_c_export_rejects_unrepresentable_field_names(
    native: ctypes.CDLL, tmp_path: Path, nested: bool
) -> None:
    """
    title: C export must not truncate names that IPC can preserve intact.
    parameters:
      native:
        type: ctypes.CDLL
      tmp_path:
        type: Path
      nested:
        type: bool
    """
    if nested:
        values = pa.array([{"bad\x00name": 42}])
        batch = pa.record_batch([values], names=["record"])
    else:
        batch = pa.record_batch([pa.array([42])], names=["bad\x00name"])
    path = tmp_path / "names.arrow"
    with pa.ipc.new_file(str(path), batch.schema) as writer:
        writer.write_batch(batch)
    reader = ctypes.c_void_p()
    assert (
        native.irx_rb_file_reader_open(
            str(path).encode(), ctypes.byref(reader)
        )
        == 0
    )
    stream = ffi.new("struct ArrowArrayStream *")
    try:
        assert (
            native.irx_rb_stream_reader_export(reader, address(stream))
            == IRX_ERR_TYPE
        )
        assert stream.release == ffi.NULL
        assert b"embedded NUL" in native.irx_record_batch_errmsg()
    finally:
        native.irx_rb_stream_reader_close(reader)
