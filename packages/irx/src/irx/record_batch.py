"""
title: Record batch streaming API.
"""

from __future__ import annotations

import ctypes
import os

from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime, time, timezone
from enum import IntEnum
from functools import lru_cache
from typing import Any, Optional

from irx.record_batch_abi import (
    IRX_RECORD_BATCH_LIBRARY_ENV,
    RECORD_BATCH_ABI_VERSION,
    record_batch_library_path,
)
from irx.typecheck import typechecked

# Load the native shared library


@typechecked
def _load_native_lib() -> ctypes.CDLL:
    """
    title: _load_native_lib.
    returns:
      type: ctypes.CDLL
    """
    configured = os.environ.get(IRX_RECORD_BATCH_LIBRARY_ENV)
    if configured:
        configured_path = record_batch_library_path()
        if not configured_path.is_file():
            raise RuntimeError(
                f"{IRX_RECORD_BATCH_LIBRARY_ENV} does not name an existing "
                f"native library: {configured_path}"
            )
        return ctypes.CDLL(str(configured_path))

    # Build or refresh the ABI-scoped cache from wheel/source contents. The
    # builder owns fingerprinting, locking, and atomic replacement.
    from irx.builder.runtime.record_batch import (  # noqa: PLC0415
        ensure_record_batch_shared_library,
    )

    library_path = ensure_record_batch_shared_library()
    try:
        return ctypes.CDLL(str(library_path))
    except OSError as error:
        raise RuntimeError(
            f"Unable to load RecordBatch native library: {library_path}"
        ) from error


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
    pcstr = c.POINTER(c.c_char_p)
    pui8 = c.POINTER(c.c_uint8)
    ppui8 = c.POINTER(pui8)
    ppi32 = c.POINTER(pi32)

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

    try:
        fn("irx_record_batch_abi_version", u32)
    except AttributeError as err:
        raise RuntimeError(
            "RecordBatch native ABI mismatch: the library does not expose "
            "irx_record_batch_abi_version; rebuild the IRx native runtime"
        ) from err
    actual_abi = int(lib.irx_record_batch_abi_version())
    if actual_abi != RECORD_BATCH_ABI_VERSION:
        raise RuntimeError(
            "RecordBatch native ABI mismatch: expected "
            f"{RECORD_BATCH_ABI_VERSION}, found {actual_abi}; rebuild the "
            "IRx native runtime"
        )

    fn("irx_record_batch_errmsg", cstr)

    fn("irx_type_primitive", vp, i32)
    fn("irx_type_list", vp, vp)
    fn("irx_type_struct", vp, ctypes.POINTER(cstr), ctypes.POINTER(vp), i32)
    fn("irx_type_release", None, vp)

    fn("irx_rb_schema_create", i32, pvp)
    fn("irx_rb_schema_add_field", i32, vp, cstr, i32, i32)
    fn("irx_rb_schema_add_field2", i32, vp, cstr, vp, i32)
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
    fn("irx_rb_builder_append_utf8", i32, vp, i32, cstr, i64)
    fn("irx_rb_builder_append_date", i32, vp, i32, i64)
    fn("irx_rb_builder_append_timestamp", i32, vp, i32, i64)
    fn("irx_rb_builder_append_time", i32, vp, i32, i64)
    fn("irx_rb_builder_append_null", i32, vp, i32)
    fn("irx_rb_builder_append_list", i32, vp, i32, vp, i64)
    fn("irx_rb_builder_struct_append", i32, vp, i32)
    fn("irx_rb_builder_struct_field_int", i32, vp, i32, i32, i64)
    fn("irx_rb_builder_struct_field_float", i32, vp, i32, i32, f64)
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
    fn("irx_rb_batch_get_utf8", i32, vp, i32, i64, pcstr, pi64)
    fn("irx_rb_batch_get_date", i32, vp, i32, i64, pi64)
    fn("irx_rb_batch_get_timestamp", i32, vp, i32, i64, pi64)
    fn("irx_rb_batch_get_time", i32, vp, i32, i64, pi64)
    fn("irx_rb_batch_is_null", i32, vp, i32, i64, pi32)
    fn("irx_rb_batch_value_buffer", i32, vp, i32, ppui8, pi64)
    fn("irx_rb_batch_list_elem_type", i32, vp, i32, pi32)
    fn("irx_rb_batch_list_offsets", i32, vp, i32, ppi32, pi64)
    fn("irx_rb_batch_list_child_buffer", i32, vp, i32, pvp, pi64)
    fn("irx_rb_batch_struct_num_fields", i32, vp, i32, pi32)
    fn("irx_rb_batch_struct_field_name", i32, vp, i32, i32, pcstr)
    fn("irx_rb_batch_struct_field_type", i32, vp, i32, i32, pi32)
    fn("irx_rb_batch_struct_field_buffer", i32, vp, i32, i32, pvp, pi64)
    fn("irx_rb_batch_release", None, vp)

    fn("irx_compute_aggregate", i32, vp, i32, i32, pi32, pi64, pf64)
    fn("irx_compute_binary", i32, vp, i32, i32, i32, pvp)
    fn("irx_compute_filter", i32, vp, i32, pvp)
    fn("irx_compute_sort_indices", i32, vp, i32, i32, pi64, i64)

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


# Error helpers

IRX_OK = 0
IRX_EOF = 1

_EPOCH_DATE = date(1970, 1, 1)
_EPOCH_DATETIME = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS_PER_DAY = 86_400_000
_US_PER_DAY = 86_400_000_000
_NS_PER_DAY = 86_400_000_000_000


@typechecked
def _date_to_int(v: date, col_type: IrxColumnType) -> int:
    """
    title: Convert a datetime.date to the raw storage int for a date column.
    parameters:
      v:
        type: date
      col_type:
        type: IrxColumnType
    returns:
      type: int
    """
    days = (v - _EPOCH_DATE).days
    if col_type == IrxColumnType.DATE32:
        return days
    if col_type == IrxColumnType.DATE64:
        return days * _MS_PER_DAY
    raise ValueError(f"column type {col_type.name} is not a date column")


@typechecked
def _datetime_to_int(v: datetime, col_type: IrxColumnType) -> int:
    """
    title: Convert a datetime to the raw storage int for a timestamp column.
    parameters:
      v:
        type: datetime
      col_type:
        type: IrxColumnType
    returns:
      type: int
    """
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    delta = v - _EPOCH_DATETIME
    total_us = (
        delta.days * _US_PER_DAY
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    if col_type == IrxColumnType.TIMESTAMP_S:
        return total_us // 1_000_000
    if col_type == IrxColumnType.TIMESTAMP_MS:
        return total_us // 1_000
    if col_type == IrxColumnType.TIMESTAMP_US:
        return total_us
    if col_type == IrxColumnType.TIMESTAMP_NS:
        return total_us * 1_000
    raise ValueError(f"column type {col_type.name} is not a timestamp column")


@typechecked
def _time_to_int(v: time, col_type: IrxColumnType) -> int:
    """
    title: Convert a datetime.time to the raw storage int for a time column.
    parameters:
      v:
        type: time
      col_type:
        type: IrxColumnType
    returns:
      type: int
    """
    total_us = (
        v.hour * 3600 + v.minute * 60 + v.second
    ) * 1_000_000 + v.microsecond
    if col_type == IrxColumnType.TIME32_S:
        return total_us // 1_000_000
    if col_type == IrxColumnType.TIME32_MS:
        return total_us // 1_000
    if col_type == IrxColumnType.TIME64_US:
        return total_us
    if col_type == IrxColumnType.TIME64_NS:
        return total_us * 1_000
    raise ValueError(f"column type {col_type.name} is not a time column")


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


# Public enum


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
    UTF8 = 11
    LARGE_UTF8 = 12
    DATE32 = 13
    DATE64 = 14
    TIMESTAMP_S = 15
    TIMESTAMP_MS = 16
    TIMESTAMP_US = 17
    TIMESTAMP_NS = 18
    TIME32_S = 19
    TIME32_MS = 20
    TIME64_US = 21
    TIME64_NS = 22
    LIST = 23
    STRUCT = 24


@typechecked
class ComputeAgg(IntEnum):
    """
    title: Column aggregation kinds for RecordBatch reductions.
    """

    SUM = 0
    MIN = 1
    MAX = 2
    MEAN = 3
    COUNT = 4


@typechecked
class ComputeBinOp(IntEnum):
    """
    title: Element-wise binary operators for RecordBatch columns.
    """

    ADD = 0
    SUB = 1
    MUL = 2
    DIV = 3


# Aggregation result column types the native layer reports through its
# floating-point out-param; every other reported type reads back from the
# integer out-param.
_COMPUTE_FLOAT_TYPES: frozenset[IrxColumnType] = frozenset(
    {IrxColumnType.FLOAT32, IrxColumnType.FLOAT64}
)


# Fixed-width element types supported inside a list column, mapped to the
# ctypes scalar used to read/write their flattened value buffer. bool, utf8,
# and nested element types are intentionally excluded from this first cut.
_LIST_ELEM_CTYPE: dict[IrxColumnType, type[Any]] = {
    IrxColumnType.INT8: ctypes.c_int8,
    IrxColumnType.INT16: ctypes.c_int16,
    IrxColumnType.INT32: ctypes.c_int32,
    IrxColumnType.INT64: ctypes.c_int64,
    IrxColumnType.UINT8: ctypes.c_uint8,
    IrxColumnType.UINT16: ctypes.c_uint16,
    IrxColumnType.UINT32: ctypes.c_uint32,
    IrxColumnType.UINT64: ctypes.c_uint64,
    IrxColumnType.FLOAT32: ctypes.c_float,
    IrxColumnType.FLOAT64: ctypes.c_double,
    IrxColumnType.DATE32: ctypes.c_int32,
    IrxColumnType.DATE64: ctypes.c_int64,
    IrxColumnType.TIMESTAMP_S: ctypes.c_int64,
    IrxColumnType.TIMESTAMP_MS: ctypes.c_int64,
    IrxColumnType.TIMESTAMP_US: ctypes.c_int64,
    IrxColumnType.TIMESTAMP_NS: ctypes.c_int64,
    IrxColumnType.TIME32_S: ctypes.c_int32,
    IrxColumnType.TIME32_MS: ctypes.c_int32,
    IrxColumnType.TIME64_US: ctypes.c_int64,
    IrxColumnType.TIME64_NS: ctypes.c_int64,
}

# Struct fields share the list element's fixed-width, byte-addressable set:
# the same buffer-based reader backs both, so bool (bitmap), utf8 and nested
# field types are likewise excluded from this first cut.
_STRUCT_FIELD_CTYPE = _LIST_ELEM_CTYPE

# Field types read/written through the floating-point struct-field entry point;
# every other supported field type goes through the integer entry point.
_FLOAT_TYPES = frozenset({IrxColumnType.FLOAT32, IrxColumnType.FLOAT64})


@typechecked
def _encode_list_elem(v: Any, elem_type: IrxColumnType) -> int | float:
    """
    title: Encode one list element to its raw storage value.
    summary: |-
      datetime/date/time elements are converted through the same scale rules
      as the scalar temporal appenders; numeric elements pass through
      unchanged.
    parameters:
      v:
        type: Any
      elem_type:
        type: IrxColumnType
    returns:
      type: int | float
    """
    if isinstance(v, datetime):
        return _datetime_to_int(v, elem_type)
    if isinstance(v, date):
        return _date_to_int(v, elem_type)
    if isinstance(v, time):
        return _time_to_int(v, elem_type)
    if isinstance(v, (int, float)):
        return v
    raise TypeError(
        f"unsupported list element value of type {type(v).__name__}"
    )


# RecordBatchSchema


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
      _col_types:
        type: list[IrxColumnType]
      _elem_types:
        type: list[Optional[IrxColumnType]]
      _struct_fields:
        type: list[Optional[list[tuple[str, IrxColumnType]]]]
    """

    _handle: ctypes.c_void_p
    _lib: ctypes.CDLL
    _released: bool
    _col_types: list[IrxColumnType]
    _elem_types: list[Optional[IrxColumnType]]
    _struct_fields: list[Optional[list[tuple[str, IrxColumnType]]]]

    def __init__(self) -> None:
        """
        title: Create a new Arrow schema handle.
        """
        self._handle = ctypes.c_void_p()
        self._released = True
        self._col_types = []
        self._elem_types = []
        self._struct_fields = []

        lib = _get_lib()
        self._lib = lib
        _check(
            lib.irx_rb_schema_create(ctypes.byref(self._handle)),
            lib,
        )
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
        self._col_types.append(col_type)
        self._elem_types.append(None)
        self._struct_fields.append(None)
        return self

    def add_list_field(
        self,
        name: str,
        elem_type: IrxColumnType,
        nullable: bool = True,
    ) -> "RecordBatchSchema":
        """
        title: Add a list column with the given fixed-width element type.
        summary: |-
          elem_type must be one of the fixed-width primitive or temporal types
          (see _LIST_ELEM_CTYPE); bool, utf8, and nested element types are not
          supported yet.
        parameters:
          name:
            type: str
          elem_type:
            type: IrxColumnType
          nullable:
            type: bool
        returns:
          type: RecordBatchSchema
        """
        if elem_type not in _LIST_ELEM_CTYPE:
            raise ValueError(
                f"list element type {elem_type.name} is not supported"
            )
        t_elem = self._lib.irx_type_primitive(int(elem_type))
        if not t_elem:
            raise RuntimeError("failed to create list element type descriptor")
        t_list = self._lib.irx_type_list(t_elem)
        try:
            if not t_list:
                raise RuntimeError("failed to create list type descriptor")
            _check(
                self._lib.irx_rb_schema_add_field2(
                    self._handle,
                    name.encode(),
                    t_list,
                    int(nullable),
                ),
                self._lib,
            )
        finally:
            # irx_type_list copies its element, so both descriptors are owned
            # here and must be released regardless of the outcome.
            if t_list:
                self._lib.irx_type_release(t_list)
            self._lib.irx_type_release(t_elem)
        self._col_types.append(IrxColumnType.LIST)
        self._elem_types.append(elem_type)
        self._struct_fields.append(None)
        return self

    def add_struct_field(
        self,
        name: str,
        fields: Sequence[tuple[str, IrxColumnType]],
        nullable: bool = True,
    ) -> "RecordBatchSchema":
        """
        title: Add a struct column with the given named fixed-width fields.
        summary: |-
          Each field is a (name, type) pair whose type must be one of the
          fixed-width primitive or temporal types (see _STRUCT_FIELD_CTYPE);
          bool, utf8, and nested field types are not supported yet.
        parameters:
          name:
            type: str
          fields:
            type: Sequence[tuple[str, IrxColumnType]]
          nullable:
            type: bool
        returns:
          type: RecordBatchSchema
        """
        field_list = list(fields)
        if not field_list:
            raise ValueError("struct column must have at least one field")
        for fname, ftype in field_list:
            if ftype not in _STRUCT_FIELD_CTYPE:
                raise ValueError(
                    f"struct field type {ftype.name} is not supported"
                )
        # Build a child descriptor per field, then wrap them in a struct
        # descriptor. irx_type_struct copies each field descriptor, so every
        # descriptor allocated here is owned locally and released below.
        names_arr = (ctypes.c_char_p * len(field_list))(
            *(fname.encode() for fname, _ in field_list)
        )
        field_ptrs = (ctypes.c_void_p * len(field_list))()
        try:
            for i, (_, ftype) in enumerate(field_list):
                t_field = self._lib.irx_type_primitive(int(ftype))
                if not t_field:
                    raise RuntimeError(
                        "failed to create struct field type descriptor"
                    )
                field_ptrs[i] = t_field
            t_struct = self._lib.irx_type_struct(
                names_arr, field_ptrs, len(field_list)
            )
            if not t_struct:
                raise RuntimeError("failed to create struct type descriptor")
            try:
                _check(
                    self._lib.irx_rb_schema_add_field2(
                        self._handle,
                        name.encode(),
                        t_struct,
                        int(nullable),
                    ),
                    self._lib,
                )
            finally:
                self._lib.irx_type_release(t_struct)
        finally:
            for i in range(len(field_list)):
                if field_ptrs[i]:
                    self._lib.irx_type_release(ctypes.c_void_p(field_ptrs[i]))
        self._col_types.append(IrxColumnType.STRUCT)
        self._elem_types.append(None)
        self._struct_fields.append(field_list)
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


# RecordBatchBuilder


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
      _col_types:
        type: list[IrxColumnType]
      _elem_types:
        type: list[Optional[IrxColumnType]]
      _struct_fields:
        type: list[Optional[list[tuple[str, IrxColumnType]]]]
    """

    _handle: ctypes.c_void_p
    _lib: ctypes.CDLL
    _released: bool
    _col_types: list[IrxColumnType]
    _elem_types: list[Optional[IrxColumnType]]
    _struct_fields: list[Optional[list[tuple[str, IrxColumnType]]]]

    def __init__(self, schema: RecordBatchSchema) -> None:
        """
        title: Create a builder for the supplied schema.
        parameters:
          schema:
            type: RecordBatchSchema
        """
        self._handle = ctypes.c_void_p()
        self._released = True
        self._col_types = list(schema._col_types)
        self._elem_types = list(schema._elem_types)
        self._struct_fields = list(schema._struct_fields)

        lib = _get_lib()
        self._lib = lib
        _check(
            lib.irx_rb_builder_create(
                schema._raw(),
                ctypes.byref(self._handle),
            ),
            lib,
        )
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

    def append_string(self, col: int, v: str) -> None:
        """
        title: Append a UTF-8 string to a utf8 or large_utf8 column.
        parameters:
          col:
            type: int
          v:
            type: str
        """
        data = v.encode("utf-8")
        _check(
            self._lib.irx_rb_builder_append_utf8(
                self._handle, col, data, ctypes.c_int64(len(data))
            ),
            self._lib,
        )

    def append_date(self, col: int, v: date | int) -> None:
        """
        title: Append a value to a date32 or date64 column.
        summary: |-
          Accepts a datetime.date or a raw storage int (days since epoch for
          DATE32, milliseconds since epoch for DATE64).
        parameters:
          col:
            type: int
          v:
            type: date | int
        """
        if isinstance(v, date):
            v = _date_to_int(v, self._col_types[col])
        _check(
            self._lib.irx_rb_builder_append_date(
                self._handle, col, ctypes.c_int64(v)
            ),
            self._lib,
        )

    def append_timestamp(self, col: int, v: datetime | int) -> None:
        """
        title: Append a value to a timestamp column.
        summary: |-
          Accepts a datetime.datetime (naive treated as UTC) or a raw storage
          int already scaled to the column's unit (seconds, milliseconds,
          microseconds, or nanoseconds since epoch).
        parameters:
          col:
            type: int
          v:
            type: datetime | int
        """
        if isinstance(v, datetime):
            v = _datetime_to_int(v, self._col_types[col])
        _check(
            self._lib.irx_rb_builder_append_timestamp(
                self._handle, col, ctypes.c_int64(v)
            ),
            self._lib,
        )

    def append_time(self, col: int, v: time | int) -> None:
        """
        title: Append a value to a time32 or time64 column.
        summary: |-
          Accepts a datetime.time or a raw storage int scaled to the column's
          unit (seconds, milliseconds, microseconds, or nanoseconds since
          midnight).
        parameters:
          col:
            type: int
          v:
            type: time | int
        """
        if isinstance(v, time):
            v = _time_to_int(v, self._col_types[col])
        _check(
            self._lib.irx_rb_builder_append_time(
                self._handle, col, ctypes.c_int64(v)
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

    def append_list(self, col: int, values: Sequence[Any]) -> None:
        """
        title: Append one list slot to a list column.
        summary: |-
          values is a sequence of the column's element type. Temporal elements
          accept datetime.date/datetime/time objects or raw storage ints;
          numeric elements accept plain numbers. Use append_null(col) for a
          null list slot.
        parameters:
          col:
            type: int
          values:
            type: Sequence[Any]
        """
        elem_type = self._elem_types[col]
        if elem_type is None:
            raise ValueError(f"column {col} is not a list column")
        ctype = _LIST_ELEM_CTYPE[elem_type]
        encoded = [_encode_list_elem(v, elem_type) for v in values]
        n = len(encoded)
        arr = (ctype * n)(*encoded)
        _check(
            self._lib.irx_rb_builder_append_list(
                self._handle,
                col,
                ctypes.cast(arr, ctypes.c_void_p),
                ctypes.c_int64(n),
            ),
            self._lib,
        )

    def append_struct(
        self, col: int, values: Mapping[str, Any] | Sequence[Any]
    ) -> None:
        """
        title: Append one struct slot to a struct column.
        summary: |-
          values gives one value per field, either as a mapping keyed by field
          name or as a positional sequence in field order. Temporal fields
          accept datetime.date/datetime/time objects or raw storage ints;
          numeric fields accept plain numbers. Use append_null(col) for a null
          struct slot.
        parameters:
          col:
            type: int
          values:
            type: Mapping[str, Any] | Sequence[Any]
        """
        fields = self._struct_fields[col]
        if fields is None:
            raise ValueError(f"column {col} is not a struct column")
        if isinstance(values, Mapping):
            ordered = [values[fname] for fname, _ in fields]
        else:
            ordered = list(values)
            if len(ordered) != len(fields):
                raise ValueError(
                    f"struct column {col} expects {len(fields)} field values, "
                    f"got {len(ordered)}"
                )
        _check(
            self._lib.irx_rb_builder_struct_append(self._handle, col),
            self._lib,
        )
        for i, ((_, ftype), v) in enumerate(zip(fields, ordered)):
            if ftype in _FLOAT_TYPES:
                _check(
                    self._lib.irx_rb_builder_struct_field_float(
                        self._handle, col, i, ctypes.c_double(v)
                    ),
                    self._lib,
                )
            else:
                encoded = int(_encode_list_elem(v, ftype))
                _check(
                    self._lib.irx_rb_builder_struct_field_int(
                        self._handle, col, i, ctypes.c_int64(encoded)
                    ),
                    self._lib,
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


# RecordBatch (inspection handle)
@typechecked
class RecordBatch:
    """
    title: RecordBatch.
    summary: |-
      Null-slot behaviour is uniform across every getter: a null value reads
      back as the zero value of its type (0 for numerics, empty string for
      utf8/large_utf8, epoch-relative 0 for date/timestamp/time). Callers
      that need to distinguish a real zero/empty value from a null must
      check ``is_null(col, row)`` first.
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

    def get_string(self, col: int, row: int) -> str:
        """
        title: Return a UTF-8 string from a utf8 or large_utf8 column.
        summary: |-
          Null slots return an empty string rather than an error, matching
          the behavior of the numeric getters. Callers that need to
          distinguish a real empty string from a null must check
          ``is_null(col, row)`` first.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: str
        """
        data_ptr = ctypes.c_char_p()
        length = ctypes.c_int64()
        _check(
            self._lib.irx_rb_batch_get_utf8(
                self._handle,
                col,
                row,
                ctypes.byref(data_ptr),
                ctypes.byref(length),
            ),
            self._lib,
        )
        raw = ctypes.string_at(data_ptr, length.value)
        return raw.decode("utf-8")

    def get_date(self, col: int, row: int) -> int:
        """
        title: Return the raw storage int for a date32 or date64 column.
        summary: |-
          Value is days since epoch for DATE32 and milliseconds since epoch
          for DATE64.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        out = ctypes.c_int64()
        _check(
            self._lib.irx_rb_batch_get_date(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return int(out.value)

    def get_timestamp(self, col: int, row: int) -> int:
        """
        title: Return the raw storage int for a timestamp column.
        summary: |-
          Value is scaled to the column's unit (seconds, milliseconds,
          microseconds, or nanoseconds since epoch).
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        out = ctypes.c_int64()
        _check(
            self._lib.irx_rb_batch_get_timestamp(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return int(out.value)

    def get_time(self, col: int, row: int) -> int:
        """
        title: Return the raw storage int for a time32 or time64 column.
        summary: |-
          Value is scaled to the column's unit (seconds, milliseconds,
          microseconds, or nanoseconds since midnight).
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: int
        """
        out = ctypes.c_int64()
        _check(
            self._lib.irx_rb_batch_get_time(
                self._handle, col, row, ctypes.byref(out)
            ),
            self._lib,
        )
        return int(out.value)

    def get_list(self, col: int, row: int) -> Optional[list[Any]]:
        """
        title: Return the list at a list-column row, or None if it is null.
        summary: |-
          Elements come back as raw storage values: numbers for numeric
          element types and raw storage ints for temporal element types
          (matching the scalar getters). An empty list slot returns an empty
          list; a null list slot returns None.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: Optional[list[Any]]
        """
        if self.is_null(col, row):
            return None
        elem = ctypes.c_int32()
        _check(
            self._lib.irx_rb_batch_list_elem_type(
                self._handle, col, ctypes.byref(elem)
            ),
            self._lib,
        )
        ctype = _LIST_ELEM_CTYPE[IrxColumnType(elem.value)]

        offs = ctypes.POINTER(ctypes.c_int32)()
        n = ctypes.c_int64()
        _check(
            self._lib.irx_rb_batch_list_offsets(
                self._handle, col, ctypes.byref(offs), ctypes.byref(n)
            ),
            self._lib,
        )
        buf = ctypes.c_void_p()
        blen = ctypes.c_int64()
        _check(
            self._lib.irx_rb_batch_list_child_buffer(
                self._handle, col, ctypes.byref(buf), ctypes.byref(blen)
            ),
            self._lib,
        )
        start = offs[row]
        end = offs[row + 1]
        if end == start:
            return []
        child = ctypes.cast(buf, ctypes.POINTER(ctype))
        return [child[i] for i in range(start, end)]

    def get_struct(self, col: int, row: int) -> Optional[dict[str, Any]]:
        """
        title: Return the struct at a struct-column row, or None if it is null.
        summary: |-
          Fields come back keyed by name; values are raw storage values
          (numbers for numeric fields, raw storage ints for temporal fields,
          matching the scalar getters). A null struct slot returns None.
        parameters:
          col:
            type: int
          row:
            type: int
        returns:
          type: Optional[dict[str, Any]]
        """
        if self.is_null(col, row):
            return None
        nfields = ctypes.c_int32()
        _check(
            self._lib.irx_rb_batch_struct_num_fields(
                self._handle, col, ctypes.byref(nfields)
            ),
            self._lib,
        )
        result: dict[str, Any] = {}
        for field in range(nfields.value):
            name = ctypes.c_char_p()
            _check(
                self._lib.irx_rb_batch_struct_field_name(
                    self._handle, col, field, ctypes.byref(name)
                ),
                self._lib,
            )
            ftype = ctypes.c_int32()
            _check(
                self._lib.irx_rb_batch_struct_field_type(
                    self._handle, col, field, ctypes.byref(ftype)
                ),
                self._lib,
            )
            ctype = _STRUCT_FIELD_CTYPE[IrxColumnType(ftype.value)]
            buf = ctypes.c_void_p()
            blen = ctypes.c_int64()
            _check(
                self._lib.irx_rb_batch_struct_field_buffer(
                    self._handle,
                    col,
                    field,
                    ctypes.byref(buf),
                    ctypes.byref(blen),
                ),
                self._lib,
            )
            child = ctypes.cast(buf, ctypes.POINTER(ctype))
            field_name = name.value.decode() if name.value is not None else ""
            result[field_name] = child[row]
        return result

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

    # Compute layer (arrow::compute wrappers)

    def aggregate(self, col: int, op: ComputeAgg) -> int | float:
        """
        title: Reduce a column to a scalar with the given aggregation.
        summary: >-
          MEAN returns a float; COUNT returns an int; SUM/MIN/MAX return an int
          for integer columns and a float for floating-point columns.
        parameters:
          col:
            type: int
          op:
            type: ComputeAgg
        returns:
          type: int | float
        """
        out_type = ctypes.c_int32()
        i_out = ctypes.c_int64()
        f_out = ctypes.c_double()
        _check(
            self._lib.irx_compute_aggregate(
                self._handle,
                col,
                int(op),
                ctypes.byref(out_type),
                ctypes.byref(i_out),
                ctypes.byref(f_out),
            ),
            self._lib,
        )
        if IrxColumnType(out_type.value) in _COMPUTE_FLOAT_TYPES:
            return float(f_out.value)
        return int(i_out.value)

    def sum(self, col: int) -> int | float:
        """
        title: Return the sum of a numeric column.
        parameters:
          col:
            type: int
        returns:
          type: int | float
        """
        return self.aggregate(col, ComputeAgg.SUM)

    def mean(self, col: int) -> float:
        """
        title: Return the mean of a numeric column.
        parameters:
          col:
            type: int
        returns:
          type: float
        """
        return float(self.aggregate(col, ComputeAgg.MEAN))

    def min(self, col: int) -> int | float:
        """
        title: Return the minimum value of a numeric column.
        parameters:
          col:
            type: int
        returns:
          type: int | float
        """
        return self.aggregate(col, ComputeAgg.MIN)

    def max(self, col: int) -> int | float:
        """
        title: Return the maximum value of a numeric column.
        parameters:
          col:
            type: int
        returns:
          type: int | float
        """
        return self.aggregate(col, ComputeAgg.MAX)

    def count(self, col: int) -> int:
        """
        title: Return the number of non-null values in a column.
        parameters:
          col:
            type: int
        returns:
          type: int
        """
        return int(self.aggregate(col, ComputeAgg.COUNT))

    def _binary(
        self, col_a: int, col_b: int, op: ComputeBinOp
    ) -> "RecordBatch":
        """
        title: Apply an element-wise binary op to two columns.
        parameters:
          col_a:
            type: int
          col_b:
            type: int
          op:
            type: ComputeBinOp
        returns:
          type: RecordBatch
        """
        out = ctypes.c_void_p()
        _check(
            self._lib.irx_compute_binary(
                self._handle, col_a, col_b, int(op), ctypes.byref(out)
            ),
            self._lib,
        )
        return RecordBatch(out, self._lib)

    def add(self, col_a: int, col_b: int) -> "RecordBatch":
        """
        title: Add two columns element-wise into a new single-column batch.
        parameters:
          col_a:
            type: int
          col_b:
            type: int
        returns:
          type: RecordBatch
        """
        return self._binary(col_a, col_b, ComputeBinOp.ADD)

    def subtract(self, col_a: int, col_b: int) -> "RecordBatch":
        """
        title: Subtract column b from column a element-wise.
        parameters:
          col_a:
            type: int
          col_b:
            type: int
        returns:
          type: RecordBatch
        """
        return self._binary(col_a, col_b, ComputeBinOp.SUB)

    def multiply(self, col_a: int, col_b: int) -> "RecordBatch":
        """
        title: Multiply two columns element-wise.
        parameters:
          col_a:
            type: int
          col_b:
            type: int
        returns:
          type: RecordBatch
        """
        return self._binary(col_a, col_b, ComputeBinOp.MUL)

    def divide(self, col_a: int, col_b: int) -> "RecordBatch":
        """
        title: Divide column a by column b element-wise.
        parameters:
          col_a:
            type: int
          col_b:
            type: int
        returns:
          type: RecordBatch
        """
        return self._binary(col_a, col_b, ComputeBinOp.DIV)

    def filter(self, mask_col: int) -> "RecordBatch":
        """
        title: Select the rows where the boolean mask column is true.
        parameters:
          mask_col:
            type: int
        returns:
          type: RecordBatch
        """
        out = ctypes.c_void_p()
        _check(
            self._lib.irx_compute_filter(
                self._handle, mask_col, ctypes.byref(out)
            ),
            self._lib,
        )
        return RecordBatch(out, self._lib)

    def sort_indices(self, col: int, ascending: bool = True) -> list[int]:
        """
        title: Return the row indices that sort a column.
        parameters:
          col:
            type: int
          ascending:
            type: bool
        returns:
          type: list[int]
        """
        n = self.num_rows
        out = (ctypes.c_int64 * n)()
        _check(
            self._lib.irx_compute_sort_indices(
                self._handle, col, 1 if ascending else 0, out, n
            ),
            self._lib,
        )
        return [int(out[i]) for i in range(n)]

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
