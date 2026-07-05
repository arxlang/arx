"""
packages/irx/src/irx/record_batch.py

High-level Python API for RecordBatch streaming via the Arrow C++ bridge.

This module provides:

* ``RecordBatchSchema``   — build an Arrow schema incrementally.
* ``RecordBatchBuilder``  — append typed values and produce a batch.
* ``RecordBatchStreamWriter`` — write batches to a file or in-memory buffer.
* ``RecordBatchStreamReader`` — iterate batches from a file or buffer.

The classes are thin wrappers around the opaque C handles declared in
``irx_record_batch.h``.  They are also the canonical Python-side spelling of
the feature for IRx integration tests and for Arx programs that need to
round-trip Arrow IPC data via the Python host.

Example — round-trip through a buffer
--------------------------------------
::

    from irx.record_batch import (
        RecordBatchSchema, RecordBatchBuilder,
        RecordBatchStreamWriter, RecordBatchStreamReader,
        IrxColumnType,
    )

    schema = RecordBatchSchema()
    schema.add_field("id",    IrxColumnType.INT32,   nullable=False)
    schema.add_field("value", IrxColumnType.FLOAT64, nullable=True)

    writer = RecordBatchStreamWriter.open_buffer(schema)

    builder = RecordBatchBuilder(schema)
    for i in range(5):
        builder.append_int32(0, i)
        builder.append_float64(1, i * 1.5)
    batch = builder.finish()
    writer.write_batch(batch)
    batch.release()
    builder.release()

    writer.close()
    data = writer.buffer_data()
    writer.release()

    reader = RecordBatchStreamReader.open_buffer(data)
    while (rb := reader.next_batch()) is not None:
        print(rb.num_rows(), rb.num_columns())
        for row in range(rb.num_rows()):
            print(rb.get_int32(0, row), rb.get_float64(1, row))
        rb.release()
    reader.close()
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
    Locate and load the IRx Arrow native library.

    During development the library is compiled by the IRx build system and
    placed under the runtime/arrow/ directory.  In an installed package it will
    be in the platform lib/ directory next to the Python package.
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
    lib = _load_native_lib()
    _configure_lib(lib)
    return lib


@typechecked
def _configure_lib(lib: ctypes.CDLL) -> None:
    """Set argtypes / restype for every exported function."""
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
    if rc < 0:
        msg = lib.irx_record_batch_errmsg()
        raise RuntimeError(f"IRx RecordBatch error ({rc}): {msg.decode()}")


# ---------------------------------------------------------------------------
# Public enum
# ---------------------------------------------------------------------------


@typechecked
class IrxColumnType(IntEnum):
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
    """Incrementally build an Arrow schema for RecordBatch streaming."""

    def __init__(self) -> None:
        lib = _get_lib()
        handle = ctypes.c_void_p()
        _check(lib.irx_rb_schema_create(ctypes.byref(handle)), lib)
        self._handle = handle
        self._lib = lib
        self._released = False

    def add_field(
        self, name: str, col_type: IrxColumnType, nullable: bool = True
    ) -> "RecordBatchSchema":
        """Add a named field to the schema. Returns self for chaining."""
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
        return int(self._lib.irx_rb_schema_num_fields(self._handle))

    def release(self) -> None:
        if not self._released:
            self._lib.irx_rb_schema_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        self.release()

    def _raw(self) -> ctypes.c_void_p:
        return self._handle


# ---------------------------------------------------------------------------
# RecordBatchBuilder
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchBuilder:
    """Append typed values column-by-column and produce a RecordBatch."""

    def __init__(self, schema: RecordBatchSchema) -> None:
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
        _check(
            self._lib.irx_rb_builder_append_int8(
                self._handle, col, ctypes.c_int8(v)
            ),
            self._lib,
        )

    def append_int16(self, col: int, v: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_int16(
                self._handle, col, ctypes.c_int16(v)
            ),
            self._lib,
        )

    def append_int32(self, col: int, v: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_int32(
                self._handle, col, ctypes.c_int32(v)
            ),
            self._lib,
        )

    def append_int64(self, col: int, v: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_int64(
                self._handle, col, ctypes.c_int64(v)
            ),
            self._lib,
        )

    def append_uint8(self, col: int, v: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_uint8(
                self._handle, col, ctypes.c_uint8(v)
            ),
            self._lib,
        )

    def append_uint16(self, col: int, v: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_uint16(
                self._handle, col, ctypes.c_uint16(v)
            ),
            self._lib,
        )

    def append_uint32(self, col: int, v: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_uint32(
                self._handle, col, ctypes.c_uint32(v)
            ),
            self._lib,
        )

    def append_uint64(self, col: int, v: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_uint64(
                self._handle, col, ctypes.c_uint64(v)
            ),
            self._lib,
        )

    def append_float32(self, col: int, v: float) -> None:
        _check(
            self._lib.irx_rb_builder_append_float32(
                self._handle, col, ctypes.c_float(v)
            ),
            self._lib,
        )

    def append_float64(self, col: int, v: float) -> None:
        _check(
            self._lib.irx_rb_builder_append_float64(
                self._handle, col, ctypes.c_double(v)
            ),
            self._lib,
        )

    def append_bool(self, col: int, v: bool) -> None:
        _check(
            self._lib.irx_rb_builder_append_bool(
                self._handle, col, ctypes.c_int32(int(v))
            ),
            self._lib,
        )

    def append_null(self, col: int) -> None:
        _check(
            self._lib.irx_rb_builder_append_null(self._handle, col), self._lib
        )

    def finish(self) -> "RecordBatch":
        """Finalise and return a RecordBatch handle."""
        batch_handle = ctypes.c_void_p()
        _check(
            self._lib.irx_rb_builder_finish(
                self._handle, ctypes.byref(batch_handle)
            ),
            self._lib,
        )
        return RecordBatch(batch_handle, self._lib)

    def release(self) -> None:
        if not self._released:
            self._lib.irx_rb_builder_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        self.release()


# ---------------------------------------------------------------------------
# RecordBatch (inspection handle)
# ---------------------------------------------------------------------------


@typechecked
class RecordBatch:
    """Wraps an irx_rb_batch handle from builder.finish() or the reader."""

    def __init__(self, handle: ctypes.c_void_p, lib: ctypes.CDLL) -> None:
        self._handle = handle
        self._lib = lib
        self._released = False

    @property
    def num_rows(self) -> int:
        return int(self._lib.irx_rb_batch_num_rows(self._handle))

    @property
    def num_columns(self) -> int:
        return int(self._lib.irx_rb_batch_num_columns(self._handle))

    def _scalar_get(
        self, fn_name: str, ctype: type[Any], col: int, row: int
    ) -> Any:
        out = ctype()
        _check(
            getattr(self._lib, fn_name)(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return out.value

    def get_int8(self, col: int, row: int) -> int:
        return int(
            self._scalar_get("irx_rb_batch_get_int8", ctypes.c_int8, col, row)
        )

    def get_int16(self, col: int, row: int) -> int:
        return int(
            self._scalar_get(
                "irx_rb_batch_get_int16", ctypes.c_int16, col, row
            )
        )

    def get_int32(self, col: int, row: int) -> int:
        return int(
            self._scalar_get(
                "irx_rb_batch_get_int32", ctypes.c_int32, col, row
            )
        )

    def get_int64(self, col: int, row: int) -> int:
        return int(
            self._scalar_get(
                "irx_rb_batch_get_int64", ctypes.c_int64, col, row
            )
        )

    def get_uint8(self, col: int, row: int) -> int:
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint8", ctypes.c_uint8, col, row
            )
        )

    def get_uint16(self, col: int, row: int) -> int:
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint16", ctypes.c_uint16, col, row
            )
        )

    def get_uint32(self, col: int, row: int) -> int:
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint32", ctypes.c_uint32, col, row
            )
        )

    def get_uint64(self, col: int, row: int) -> int:
        return int(
            self._scalar_get(
                "irx_rb_batch_get_uint64", ctypes.c_uint64, col, row
            )
        )

    def get_float32(self, col: int, row: int) -> float:
        return float(
            self._scalar_get(
                "irx_rb_batch_get_float32", ctypes.c_float, col, row
            )
        )

    def get_float64(self, col: int, row: int) -> float:
        return float(
            self._scalar_get(
                "irx_rb_batch_get_float64", ctypes.c_double, col, row
            )
        )

    def get_bool(self, col: int, row: int) -> bool:
        out = ctypes.c_int32()
        _check(
            self._lib.irx_rb_batch_get_bool(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return bool(out.value)

    def is_null(self, col: int, row: int) -> bool:
        out = ctypes.c_int32()
        _check(
            self._lib.irx_rb_batch_is_null(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return bool(out.value)

    def release(self) -> None:
        if not self._released:
            self._lib.irx_rb_batch_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        self.release()


# ---------------------------------------------------------------------------
# RecordBatchStreamWriter
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchStreamWriter:
    """Write RecordBatches to an Arrow IPC stream (file or buffer)."""

    def __init__(
        self,
        handle: ctypes.c_void_p,
        lib: ctypes.CDLL,
        is_buffer: bool = False,
    ) -> None:
        self._handle = handle
        self._lib = lib
        self._is_buffer = is_buffer
        self._closed = False
        self._released = False

    @classmethod
    def open_file(
        cls, schema: RecordBatchSchema, path: str | os.PathLike[str]
    ) -> "RecordBatchStreamWriter":
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
        _check(
            self._lib.irx_rb_stream_writer_write_batch(
                self._handle, batch._handle
            ),
            self._lib,
        )

    def close(self) -> None:
        if not self._closed:
            _check(
                self._lib.irx_rb_stream_writer_close(self._handle), self._lib
            )
            self._closed = True

    def buffer_data(self) -> bytes:
        """
        Return the serialised IPC bytes (buffer writers only).
        Must be called after close().
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
        if not self._released:
            self._lib.irx_rb_stream_writer_release(self._handle)
            self._released = True

    def __del__(self) -> None:
        self.release()

    def __enter__(self) -> "RecordBatchStreamWriter":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
        self.release()


# ---------------------------------------------------------------------------
# RecordBatchStreamReader
# ---------------------------------------------------------------------------


@typechecked
class RecordBatchStreamReader:
    """Read RecordBatches from an Arrow IPC stream (file or buffer)."""

    def __init__(self, handle: ctypes.c_void_p, lib: ctypes.CDLL) -> None:
        self._handle = handle
        self._lib = lib
        self._closed = False

    @classmethod
    def open_file(
        cls, path: str | os.PathLike[str]
    ) -> "RecordBatchStreamReader":
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
        Return the next RecordBatch or None at end-of-stream.
        Caller is responsible for calling RecordBatch.release().
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
        batch = self.next_batch()
        while batch is not None:
            yield batch
            batch.release()
            batch = self.next_batch()

    def close(self) -> None:
        if not self._closed:
            self._lib.irx_rb_stream_reader_close(self._handle)
            self._closed = True

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> "RecordBatchStreamReader":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
