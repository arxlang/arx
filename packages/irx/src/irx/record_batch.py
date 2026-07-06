"""
title: Record batch streaming API.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys

from collections.abc import Iterator
from enum import IntEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from irx.typecheck import typechecked

# ---------------------------------------------------------------------------
# Load the native shared library
# ---------------------------------------------------------------------------


@typechecked
def _load_native_lib() -> ctypes.CDLL:
    """
    title: _load_native_lib.
    returns:
      type: ctypes.CDLL
    """
    candidates = [
        # Development build (in-tree)
        Path(__file__).parent
        / "builder"
        / "runtime"
        / "arrow"
        / "libirx_record_batch.so",
        Path(__file__).parent
        / "builder"
        / "runtime"
        / "arrow"
        / "libirx_record_batch.dylib",
        Path(__file__).parent
        / "builder"
        / "runtime"
        / "arrow"
        / "irx_record_batch.dll",
        # Installed package
        Path(sys.prefix) / "lib" / "libirx_record_batch.so",
        Path(sys.prefix) / "lib" / "libirx_record_batch.dylib",
    ]
    for p in candidates:
        if p.exists():
            return ctypes.CDLL(str(p))

    # Fall back to ldconfig / PATH search
    name = ctypes.util.find_library("irx_record_batch")
    if name:
        return ctypes.CDLL(name)

    raise RuntimeError(
        "Could not locate libirx_record_batch.  "
        "Build the IRx native runtime first: `makim irx.build-native`"
    )


# Lazy-load (cached) so importing this module does not fail where the native
# library has not been compiled yet (e.g. documentation builds).
@lru_cache(maxsize=1)
@typechecked
def _get_lib() -> ctypes.CDLL:
    """
    title: Return the lazily-loaded record-batch native library.
    returns:
      type: ctypes.CDLL
    """
    lib = _load_native_lib()
    _configure_lib(lib)
    return lib


@typechecked
def _configure_lib(lib: ctypes.CDLL) -> None:
    """
    title: _configure_lib.
    parameters:
      lib:
        type: ctypes.CDLL
    """
    c = ctypes
    vp = c.c_void_p
    pvp = c.POINTER(c.c_void_p)
    i8 = c.c_int8
    pi8 = c.POINTER(c.c_int8)
    i16 = c.c_int16
    pi16 = c.POINTER(c.c_int16)
    i32 = c.c_int32
    pi32 = c.POINTER(c.c_int32)
    i64 = c.c_int64
    pi64 = c.POINTER(c.c_int64)
    u8 = c.c_uint8
    pu8 = c.POINTER(c.c_uint8)
    u16 = c.c_uint16
    pu16 = c.POINTER(c.c_uint16)
    u32 = c.c_uint32
    pu32 = c.POINTER(c.c_uint32)
    u64 = c.c_uint64
    pu64 = c.POINTER(c.c_uint64)
    f32 = c.c_float
    pf32 = c.POINTER(c.c_float)
    f64 = c.c_double
    pf64 = c.POINTER(c.c_double)
    cstr = c.c_char_p
    pui8 = c.POINTER(c.c_uint8)
    ppui8 = c.POINTER(pui8)

    def fn(name: str, restype: Any, *argtypes: Any) -> None:
        """
        title: Configure ctypes metadata for one exported native function.
        parameters:
          name:
            type: str
          restype:
            type: Any
          argtypes:
            type: Any
            variadic: positional
        """
        f = getattr(lib, name)
        f.restype = restype
        f.argtypes = list(argtypes)

    fn("irx_record_batch_errmsg", cstr)

    fn("irx_rb_schema_create", i32, pvp)
    fn("irx_rb_schema_add_field", i32, vp, cstr, i32, i32)
    fn("irx_rb_schema_num_fields", i32, vp)
    fn("irx_rb_schema_release", None, vp)

    fn("irx_rb_builder_create", i32, vp, pvp)
    fn("irx_rb_builder_append_int8", i32, vp, i32, i8)
    fn("irx_rb_builder_append_int16", i32, vp, i32, i16)
    fn("irx_rb_builder_append_int32", i32, vp, i32, i32)
    fn("irx_rb_builder_append_int64", i32, vp, i32, i64)
    fn("irx_rb_builder_append_uint8", i32, vp, i32, u8)
    fn("irx_rb_builder_append_uint16", i32, vp, i32, u16)
    fn("irx_rb_builder_append_uint32", i32, vp, i32, u32)
    fn("irx_rb_builder_append_uint64", i32, vp, i32, u64)
    fn("irx_rb_builder_append_float32", i32, vp, i32, f32)
    fn("irx_rb_builder_append_float64", i32, vp, i32, f64)
    fn("irx_rb_builder_append_bool", i32, vp, i32, i32)
    fn("irx_rb_builder_append_null", i32, vp, i32)
    fn("irx_rb_builder_finish", i32, vp, pvp)
    fn("irx_rb_builder_release", None, vp)

    fn("irx_rb_batch_num_rows", i64, vp)
    fn("irx_rb_batch_num_columns", i32, vp)
    fn("irx_rb_batch_get_int8", i32, vp, i32, i64, pi8)
    fn("irx_rb_batch_get_int16", i32, vp, i32, i64, pi16)
    fn("irx_rb_batch_get_int32", i32, vp, i32, i64, pi32)
    fn("irx_rb_batch_get_int64", i32, vp, i32, i64, pi64)
    fn("irx_rb_batch_get_uint8", i32, vp, i32, i64, pu8)
    fn("irx_rb_batch_get_uint16", i32, vp, i32, i64, pu16)
    fn("irx_rb_batch_get_uint32", i32, vp, i32, i64, pu32)
    fn("irx_rb_batch_get_uint64", i32, vp, i32, i64, pu64)
    fn("irx_rb_batch_get_float32", i32, vp, i32, i64, pf32)
    fn("irx_rb_batch_get_float64", i32, vp, i32, i64, pf64)
    fn("irx_rb_batch_get_bool", i32, vp, i32, i64, pi32)
    fn("irx_rb_batch_is_null", i32, vp, i32, i64, pi32)
    fn("irx_rb_batch_value_buffer", i32, vp, i32, ppui8, pi64)
    fn("irx_rb_batch_release", None, vp)

    fn("irx_rb_stream_writer_open_file", i32, vp, cstr, pvp)
    fn("irx_rb_stream_writer_open_buffer", i32, vp, pvp)
    fn("irx_rb_stream_writer_write_batch", i32, vp, vp)
    fn("irx_rb_stream_writer_close", i32, vp)
    fn("irx_rb_stream_writer_buffer_data", i32, vp, ppui8, pi64)
    fn("irx_rb_stream_writer_release", None, vp)

    fn("irx_rb_stream_reader_open_file", i32, cstr, pvp)
    fn("irx_rb_stream_reader_open_buffer", i32, pui8, i64, pvp)
    fn("irx_rb_stream_reader_next_batch", i32, vp, pvp)
    fn("irx_rb_stream_reader_schema", vp, vp)
    fn("irx_rb_stream_reader_close", None, vp)


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

IRX_OK = 0
IRX_EOF = 1


@typechecked
def _check(rc: int, lib: ctypes.CDLL) -> None:
    """
    title: Validate a native record-batch call result code.
    parameters:
      rc:
        type: int
      lib:
        type: ctypes.CDLL
    """
    if rc < 0:
        msg = lib.irx_record_batch_errmsg()
        raise RuntimeError(f"IRx RecordBatch error ({rc}): {msg.decode()}")


# ---------------------------------------------------------------------------
# Public enum
# ---------------------------------------------------------------------------


@typechecked
class IrxColumnType(IntEnum):
    """
    title: IrxColumnType.
    """

    INT8 = 0
    INT16 = 1
    INT32 = 2
    INT64 = 3
    UINT8 = 4
    UINT16 = 5
    UINT32 = 6
    UINT64 = 7
    FLOAT32 = 8
    FLOAT64 = 9
    BOOL = 10


# ---------------------------------------------------------------------------
# RecordBatchSchema
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchSchema:
    """
    title: RecordBatchSchema.
    attributes:
      _handle:
        type: ctypes.c_void_p
      _lib:
        type: ctypes.CDLL
      _released:
        type: bool
    """

    _handle: ctypes.c_void_p
    _lib: ctypes.CDLL
    _released: bool

    def __init__(self) -> None:
        """
        title: Create a new Arrow schema handle.
        """
        lib = _get_lib()
        handle = ctypes.c_void_p()
        _check(lib.irx_rb_schema_create(ctypes.byref(handle)), lib)
        self._handle = handle
        self._lib = lib
        self._released = False

    def add_field(
        self, name: str, col_type: IrxColumnType, nullable: bool = True
    ) -> "RecordBatchSchema":
        """
        title: add_field.
        parameters:
          name:
            type: str
          col_type:
            type: IrxColumnType
          nullable:
            type: bool
        returns:
          type: RecordBatchSchema
        """
        _check(
            self._lib.irx_rb_schema_add_field(
                self._handle,
                name.encode(),
                int(col_type),
                int(nullable),
            ),
            self._lib,
        )
        return self

    @property
    def num_fields(self) -> int:
        """
        title: Return the number of schema fields.
        returns:
          type: int
        """
        return int(self._lib.irx_rb_schema_num_fields(self._handle))

    def release(self) -> None:
        """
        title: Release the underlying schema handle.
        """
        if not self._released:
            self._lib.irx_rb_schema_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        """
        title: Release the schema when the object is garbage collected.
        """
        self.release()

    def _raw(self) -> ctypes.c_void_p:
        """
        title: Return the underlying native handle.
        returns:
          type: ctypes.c_void_p
        """
        return self._handle


# ---------------------------------------------------------------------------
# RecordBatchBuilder
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchBuilder:
    """
    title: RecordBatchBuilder.
    attributes:
      _handle:
        type: ctypes.c_void_p
      _lib:
        type: ctypes.CDLL
      _released:
        type: bool
    """

    _handle: ctypes.c_void_p
    _lib: ctypes.CDLL
    _released: bool

    def __init__(self, schema: RecordBatchSchema) -> None:
        """
        title: Create a builder for the supplied schema.
        parameters:
          schema:
            type: RecordBatchSchema
        """
        lib = _get_lib()
        handle = ctypes.c_void_p()
        _check(
            lib.irx_rb_builder_create(schema._raw(), ctypes.byref(handle)), lib
        )
        self._handle = handle
        self._lib = lib
        self._released = False

    # --- typed appends ---

    def append_int8(self, col: int, v: int) -> None:
        """
        title: Append an 8-bit signed integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_int8(
                self._handle, col, ctypes.c_int8(v)
            ),
            self._lib,
        )

    def append_int16(self, col: int, v: int) -> None:
        """
        title: Append a 16-bit signed integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_int16(
                self._handle, col, ctypes.c_int16(v)
            ),
            self._lib,
        )

    def append_int32(self, col: int, v: int) -> None:
        """
        title: Append a 32-bit signed integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_int32(
                self._handle, col, ctypes.c_int32(v)
            ),
            self._lib,
        )

    def append_int64(self, col: int, v: int) -> None:
        """
        title: Append a 64-bit signed integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_int64(
                self._handle, col, ctypes.c_int64(v)
            ),
            self._lib,
        )

    def append_uint8(self, col: int, v: int) -> None:
        """
        title: Append an 8-bit unsigned integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_uint8(
                self._handle, col, ctypes.c_uint8(v)
            ),
            self._lib,
        )

    def append_uint16(self, col: int, v: int) -> None:
        """
        title: Append a 16-bit unsigned integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_uint16(
                self._handle, col, ctypes.c_uint16(v)
            ),
            self._lib,
        )

    def append_uint32(self, col: int, v: int) -> None:
        """
        title: Append a 32-bit unsigned integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_uint32(
                self._handle, col, ctypes.c_uint32(v)
            ),
            self._lib,
        )

    def append_uint64(self, col: int, v: int) -> None:
        """
        title: Append a 64-bit unsigned integer to a column.
        parameters:
          col:
            type: int
          v:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_uint64(
                self._handle, col, ctypes.c_uint64(v)
            ),
            self._lib,
        )

    def append_float32(self, col: int, v: float) -> None:
        """
        title: Append a 32-bit floating-point value to a column.
        parameters:
          col:
            type: int
          v:
            type: float
        """
        _check(
            self._lib.irx_rb_builder_append_float32(
                self._handle, col, ctypes.c_float(v)
            ),
            self._lib,
        )

    def append_float64(self, col: int, v: float) -> None:
        """
        title: Append a 64-bit floating-point value to a column.
        parameters:
          col:
            type: int
          v:
            type: float
        """
        _check(
            self._lib.irx_rb_builder_append_float64(
                self._handle, col, ctypes.c_double(v)
            ),
            self._lib,
        )

    def append_bool(self, col: int, v: bool) -> None:
        """
        title: Append a boolean value to a column.
        parameters:
          col:
            type: int
          v:
            type: bool
        """
        _check(
            self._lib.irx_rb_builder_append_bool(
                self._handle, col, ctypes.c_int32(int(v))
            ),
            self._lib,
        )

    def append_null(self, col: int) -> None:
        """
        title: Append a null value to a column.
        parameters:
          col:
            type: int
        """
        _check(
            self._lib.irx_rb_builder_append_null(self._handle, col), self._lib
        )

    def finish(self) -> "RecordBatch":
        """
        title: finish.
        returns:
          type: RecordBatch
        """
        batch_handle = ctypes.c_void_p()
        _check(
            self._lib.irx_rb_builder_finish(
                self._handle, ctypes.byref(batch_handle)
            ),
            self._lib,
        )
        return RecordBatch(batch_handle, self._lib)

    def release(self) -> None:
        """
        title: Release the underlying builder handle.
        """
        if not self._released:
            self._lib.irx_rb_builder_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        """
        title: Release the builder when the object is garbage collected.
        """
        self.release()


# ---------------------------------------------------------------------------
# RecordBatch (inspection handle)
# ---------------------------------------------------------------------------


@typechecked
class RecordBatch:
    """
    title: RecordBatch.
    attributes:
      _handle:
        type: ctypes.c_void_p
      _lib:
        type: ctypes.CDLL
      _released:
        type: bool
    """

    _handle: ctypes.c_void_p
    _lib: ctypes.CDLL
    _released: bool

    def __init__(self, handle: ctypes.c_void_p, lib: ctypes.CDLL) -> None:
        """
        title: Create a wrapper around an existing native batch handle.
        parameters:
          handle:
            type: ctypes.c_void_p
          lib:
            type: ctypes.CDLL
        """
        self._handle = handle
        self._lib = lib
        self._released = False

    @property
    def num_rows(self) -> int:
        """
        title: Return the number of rows in the batch.
        returns:
          type: int
        """
        return int(self._lib.irx_rb_batch_num_rows(self._handle))

    @property
    def num_columns(self) -> int:
        """
        title: Return the number of columns in the batch.
        returns:
          type: int
        """
        return int(self._lib.irx_rb_batch_num_columns(self._handle))

    def _scalar_get(
        self, fn_name: str, ctype: type[Any], col: int, row: int
    ) -> Any:
        """
        title: Read a scalar value from the batch through a native getter.
        parameters:
          fn_name:
            type: str
          ctype:
            type: type[Any]
          col:
            type: int
          row:
            type: int
        returns:
          type: Any
        """
        out = ctype()
        _check(
            getattr(self._lib, fn_name)(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return out.value

    def get_int8(self, col: int, row: int) -> int:
        """
        title: Return an 8-bit signed integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get("irx_rb_batch_get_int8", ctypes.c_int8, col, row)
        )

    def get_int16(self, col: int, row: int) -> int:
        """
        title: Return a 16-bit signed integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get(
                "irx_rb_batch_get_int16", ctypes.c_int16, col, row
            )
        )

    def get_int32(self, col: int, row: int) -> int:
        """
        title: Return a 32-bit signed integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get(
                "irx_rb_batch_get_int32", ctypes.c_int32, col, row
            )
        )

    def get_int64(self, col: int, row: int) -> int:
        """
        title: Return a 64-bit signed integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get(
                "irx_rb_batch_get_int64", ctypes.c_int64, col, row
            )
        )

    def get_uint8(self, col: int, row: int) -> int:
        """
        title: Return an 8-bit unsigned integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint8", ctypes.c_uint8, col, row
            )
        )

    def get_uint16(self, col: int, row: int) -> int:
        """
        title: Return a 16-bit unsigned integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint16", ctypes.c_uint16, col, row
            )
        )

    def get_uint32(self, col: int, row: int) -> int:
        """
        title: Return a 32-bit unsigned integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint32", ctypes.c_uint32, col, row
            )
        )

    def get_uint64(self, col: int, row: int) -> int:
        """
        title: Return a 64-bit unsigned integer value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint64", ctypes.c_uint64, col, row
            )
        )

    def get_float32(self, col: int, row: int) -> float:
        """
        title: Return a 32-bit floating-point value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: float
        """
        return float(
            self._scalar_get(
                "irx_rb_batch_get_float32", ctypes.c_float, col, row
            )
        )

    def get_float64(self, col: int, row: int) -> float:
        """
        title: Return a 64-bit floating-point value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: float
        """
        return float(
            self._scalar_get(
                "irx_rb_batch_get_float64", ctypes.c_double, col, row
            )
        )

    def get_bool(self, col: int, row: int) -> bool:
        """
        title: Return a boolean value from the batch.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: bool
        """
        out = ctypes.c_int32()
        _check(
            self._lib.irx_rb_batch_get_bool(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return bool(out.value)

    def is_null(self, col: int, row: int) -> bool:
        """
        title: Return whether the value at the supplied location is null.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: bool
        """
        out = ctypes.c_int32()
        _check(
            self._lib.irx_rb_batch_is_null(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return bool(out.value)

    def release(self) -> None:
        """
        title: Release the underlying batch handle.
        """
        if not self._released:
            self._lib.irx_rb_batch_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        """
        title: Release the batch when the object is garbage collected.
        """
        self.release()


# ---------------------------------------------------------------------------
# RecordBatchStreamWriter
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchStreamWriter:
    """
    title: RecordBatchStreamWriter.
    attributes:
      _handle:
        type: ctypes.c_void_p
      _lib:
        type: ctypes.CDLL
      _is_buffer:
        type: bool
      _closed:
        type: bool
      _released:
        type: bool
    """

    _handle: ctypes.c_void_p
    _lib: ctypes.CDLL
    _is_buffer: bool
    _closed: bool
    _released: bool

    def __init__(
        self,
        handle: ctypes.c_void_p,
        lib: ctypes.CDLL,
        is_buffer: bool = False,
    ) -> None:
        """
        title: Wrap an existing native stream writer handle.
        parameters:
          handle:
            type: ctypes.c_void_p
          lib:
            type: ctypes.CDLL
          is_buffer:
            type: bool
        """
        self._handle = handle
        self._lib = lib
        self._is_buffer = is_buffer
        self._closed = False
        self._released = False

    @classmethod
    def open_file(
        cls, schema: RecordBatchSchema, path: str | os.PathLike[str]
    ) -> "RecordBatchStreamWriter":
        """
        title: Open a stream writer backed by a file path.
        parameters:
          schema:
            type: RecordBatchSchema
          path:
            type: str | os.PathLike[str]
        returns:
          type: RecordBatchStreamWriter
        """
        lib = _get_lib()
        handle = ctypes.c_void_p()
        _check(
            lib.irx_rb_stream_writer_open_file(
                schema._raw(), str(path).encode(), ctypes.byref(handle)
            ),
            lib,
        )
        return cls(handle, lib, is_buffer=False)

    @classmethod
    def open_buffer(
        cls, schema: RecordBatchSchema
    ) -> "RecordBatchStreamWriter":
        """
        title: Open a stream writer backed by an in-memory buffer.
        parameters:
          schema:
            type: RecordBatchSchema
        returns:
          type: RecordBatchStreamWriter
        """
        lib = _get_lib()
        handle = ctypes.c_void_p()
        _check(
            lib.irx_rb_stream_writer_open_buffer(
                schema._raw(), ctypes.byref(handle)
            ),
            lib,
        )
        return cls(handle, lib, is_buffer=True)

    def write_batch(self, batch: RecordBatch) -> None:
        """
        title: Write a completed batch to the stream.
        parameters:
          batch:
            type: RecordBatch
        """
        _check(
            self._lib.irx_rb_stream_writer_write_batch(
                self._handle, batch._handle
            ),
            self._lib,
        )

    def close(self) -> None:
        """
        title: Close the underlying stream writer.
        """
        if not self._closed:
            _check(
                self._lib.irx_rb_stream_writer_close(self._handle), self._lib
            )
            self._closed = True

    def buffer_data(self) -> bytes:
        """
        title: buffer_data.
        returns:
          type: bytes
        """
        if not self._is_buffer:
            raise RuntimeError(
                "This writer is file-based; buffer_data() is not available."
            )
        data_ptr = ctypes.POINTER(ctypes.c_uint8)()
        size = ctypes.c_int64()
        _check(
            self._lib.irx_rb_stream_writer_buffer_data(
                self._handle,
                ctypes.byref(data_ptr),
                ctypes.byref(size),
            ),
            self._lib,
        )
        return bytes(ctypes.string_at(data_ptr, size.value))

    def release(self) -> None:
        """
        title: Release the underlying stream writer handle.
        """
        if not self._released:
            self._lib.irx_rb_stream_writer_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        """
        title: Release the writer when the object is garbage collected.
        """
        self.release()

    def __enter__(self) -> "RecordBatchStreamWriter":
        """
        title: Support using the writer as a context manager.
        returns:
          type: RecordBatchStreamWriter
        """
        return self

    def __exit__(self, *_exc: object) -> None:
        """
        title: Close and release the writer from a context manager.
        parameters:
          _exc:
            type: object
            variadic: positional
        """
        self.close()
        self.release()


# ---------------------------------------------------------------------------
# RecordBatchStreamReader
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchStreamReader:
    """
    title: RecordBatchStreamReader.
    attributes:
      _handle:
        type: ctypes.c_void_p
      _lib:
        type: ctypes.CDLL
      _closed:
        type: bool
    """

    _handle: ctypes.c_void_p
    _lib: ctypes.CDLL
    _closed: bool

    def __init__(self, handle: ctypes.c_void_p, lib: ctypes.CDLL) -> None:
        """
        title: Wrap an existing native stream reader handle.
        parameters:
          handle:
            type: ctypes.c_void_p
          lib:
            type: ctypes.CDLL
        """
        self._handle = handle
        self._lib = lib
        self._closed = False

    @classmethod
    def open_file(
        cls, path: str | os.PathLike[str]
    ) -> "RecordBatchStreamReader":
        """
        title: Open a stream reader backed by a file path.
        parameters:
          path:
            type: str | os.PathLike[str]
        returns:
          type: RecordBatchStreamReader
        """
        lib = _get_lib()
        handle = ctypes.c_void_p()
        _check(
            lib.irx_rb_stream_reader_open_file(
                str(path).encode(), ctypes.byref(handle)
            ),
            lib,
        )
        return cls(handle, lib)

    @classmethod
    def open_buffer(cls, data: bytes) -> "RecordBatchStreamReader":
        """
        title: Open a stream reader backed by an in-memory buffer.
        parameters:
          data:
            type: bytes
        returns:
          type: RecordBatchStreamReader
        """
        lib = _get_lib()
        handle = ctypes.c_void_p()
        buf = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        _check(
            lib.irx_rb_stream_reader_open_buffer(
                buf, ctypes.c_int64(len(data)), ctypes.byref(handle)
            ),
            lib,
        )
        return cls(handle, lib)

    def next_batch(self) -> Optional[RecordBatch]:
        """
        title: Return the next RecordBatch or None at end-of-stream.
        returns:
          type: Optional[RecordBatch]
        """
        batch_handle = ctypes.c_void_p()
        rc = self._lib.irx_rb_stream_reader_next_batch(
            self._handle, ctypes.byref(batch_handle)
        )
        if rc == IRX_EOF:
            return None
        _check(rc, self._lib)
        return RecordBatch(batch_handle, self._lib)

    def __iter__(self) -> Iterator[RecordBatch]:
        """
        title: Iterate batches from the stream until exhaustion.
        returns:
          type: Iterator[RecordBatch]
        """
        batch = self.next_batch()
        while batch is not None:
            yield batch
            batch.release()
            batch = self.next_batch()

    def close(self) -> None:
        """
        title: Close the underlying stream reader.
        """
        if not self._closed:
            self._lib.irx_rb_stream_reader_close(self._handle)
            self._closed = True

    def __del__(self) -> None:
        """
        title: Release the reader when the object is garbage collected.
        """
        self.close()

    def __enter__(self) -> "RecordBatchStreamReader":
        """
        title: Support using the reader as a context manager.
        returns:
          type: RecordBatchStreamReader
        """
        return self

    def __exit__(self, *_exc: object) -> None:
        """
        title: Close and release the reader from a context manager.
        parameters:
          _exc:
            type: object
            variadic: positional
        """
        self.close()
