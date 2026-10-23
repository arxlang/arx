"""
title: Simple native CSV and Parquet table I/O.
summary: >-
  Eager reads return independently owned PyArrow tables; writes borrow their
  input and check finalization. Importing this module performs no native build
  or optional Parquet loading. Format engines remain in the IRx native runtime.
"""

from __future__ import annotations

import ctypes
import math
import os

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Literal, cast

import pyarrow as pa

from public import private, public

from irx.parquet_options import (
    ParquetOptions,
    ParquetPredicate,
    option_integer,
    option_text,
)
from irx.record_batch import (
    RecordBatchSchema,
    _check,
    c_data_library,
    parquet_library,
    parquet_path,
    validate_c_data_field,
)
from irx.record_batch_abi import ArrowArrayStream
from irx.typecheck import typechecked


@public
@typechecked
@dataclass(frozen=True, init=False)
class ParquetFilter:
    """
    title: Immutable AND predicate group with independent composition.
    attributes:
      predicates:
        type: tuple[ParquetPredicate, Ellipsis]
    """

    predicates: tuple[ParquetPredicate, ...]

    def __init__(self, predicates: tuple[ParquetPredicate, ...]) -> None:
        """
        title: Check all predicate items even for directly constructed groups.
        parameters:
          predicates:
            type: tuple[ParquetPredicate, Ellipsis]
        """
        object.__setattr__(self, "predicates", predicates)

    def and_where(
        self,
        column: str,
        operation: str,
        value: str | int | float | bool | None = None,
    ) -> ParquetFilter:
        """
        title: Return a new group, preserving the original and its aliases.
        parameters:
          column:
            type: str
          operation:
            type: str
          value:
            type: str | int | float | bool | None
        returns:
          type: ParquetFilter
        """
        return ParquetFilter(
            (*self.predicates, *where(column, operation, value).predicates)
        )


@public
@typechecked
def where(
    column: str,
    operation: str,
    value: str | int | float | bool | None = None,
) -> ParquetFilter:
    """
    title: Create a checked predicate without serialized values or type tags.
    parameters:
      column:
        type: str
      operation:
        type: str
      value:
        type: str | int | float | bool | None
    returns:
      type: ParquetFilter
    """
    operators = {
        "==": "eq",
        "!=": "ne",
        "<": "lt",
        "<=": "le",
        ">": "gt",
        ">=": "ge",
        "is_null": "is_null",
        "is_valid": "is_valid",
    }
    if operation not in operators:
        raise ValueError(
            "operator must be ==, !=, <, <=, >, >=, is_null or is_valid"
        )
    null_check = operation in {"is_null", "is_valid"}
    if null_check != (value is None):
        raise ValueError(
            "null checks omit the value; comparisons require a value"
        )
    if not column:
        raise ValueError("filter column must be nonempty")
    option_text(column)
    if isinstance(value, int) and not isinstance(value, bool):
        option_integer(value)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("filter floating value must be finite")
    elif isinstance(value, str):
        option_text(value)
    op = cast(
        Literal["eq", "ne", "lt", "le", "gt", "ge", "is_null", "is_valid"],
        operators[operation],
    )
    return ParquetFilter(
        (ParquetPredicate(column, op, "" if value is None else value),)
    )


@private
@typechecked
def table_library(parquet: bool = False) -> ctypes.CDLL:
    """
    title: Bind table symbols lazily and reject stale native overrides.
    parameters:
      parquet:
        type: bool
    returns:
      type: ctypes.CDLL
    """
    lib = parquet_library() if parquet else c_data_library()
    p = ctypes.c_void_p
    c = ctypes.c_char_p
    signatures = {
        "irx_rb_c_stream_release": (None, [p]),
        "irx_arrow_table_import_stream": (ctypes.c_int, [p, p]),
        "irx_arrow_table_export_stream": (ctypes.c_int, [p, p]),
        "irx_arrow_table_release": (None, [p]),
        "irx_arrow_last_error": (c, []),
        "irx_csv_options_new": (p, []),
        "irx_csv_options_release": (None, [p]),
        "irx_csv_options_int": (ctypes.c_int, [p, c, ctypes.c_int64]),
        "irx_csv_options_text": (ctypes.c_int, [p, c, c]),
        "irx_csv_options_clear": (ctypes.c_int, [p, c]),
        "irx_rb_csv_read_table": (ctypes.c_int, [c, p, p, p]),
        "irx_rb_csv_write_table": (ctypes.c_int, [p, c, p]),
    }
    if parquet:
        signatures.update(
            {
                "irx_rb_parquet_read_table": (
                    ctypes.c_int,
                    [c, p, p, ctypes.c_int, p],
                ),
                "irx_rb_parquet_write_table": (
                    ctypes.c_int,
                    [p, c, p, ctypes.c_int],
                ),
            }
        )
    try:
        for name, (result, args) in signatures.items():
            function = getattr(lib, name)
            function.restype = result
            function.argtypes = args
    except AttributeError as error:
        raise RuntimeError(
            "Native library lacks table I/O; rebuild it or unset "
            "IRX_RECORD_BATCH_LIBRARY"
        ) from error
    return lib


@private
@typechecked
def check_arrow(status: int, lib: ctypes.CDLL) -> None:
    """
    title: Check the Arrow runtime status before reading any output slots.
    parameters:
      status:
        type: int
      lib:
        type: ctypes.CDLL
    """
    if status != 0:
        raise RuntimeError(lib.irx_arrow_last_error().decode("utf-8"))


@private
@typechecked
def export_table(handle: ctypes.c_void_p, lib: ctypes.CDLL) -> pa.Table:
    """
    title: Transfer independent table references through the C Stream ABI.
    parameters:
      handle:
        type: ctypes.c_void_p
      lib:
        type: ctypes.CDLL
    returns:
      type: pa.Table
    """
    stream = ArrowArrayStream()
    address = ctypes.addressof(stream)
    try:
        check_arrow(lib.irx_arrow_table_export_stream(handle, address), lib)
        with pa.RecordBatchReader._import_from_c(address) as reader:
            return reader.read_all()
    finally:
        lib.irx_rb_c_stream_release(address)
        lib.irx_arrow_table_release(handle)


@private
@contextmanager
@typechecked
def import_table(
    table: pa.Table, lib: ctypes.CDLL
) -> Iterator[ctypes.c_void_p]:
    """
    title: Borrow a PyArrow table through chunk-preserving C Stream references.
    parameters:
      table:
        type: pa.Table
      lib:
        type: ctypes.CDLL
    returns:
      type: Iterator[ctypes.c_void_p]
    """
    table.validate(full=True)
    for field in table.schema:
        validate_c_data_field(field)
    stream = ArrowArrayStream()
    address = ctypes.addressof(stream)
    handle = ctypes.c_void_p()
    try:
        table.to_reader()._export_to_c(address)
        check_arrow(
            lib.irx_arrow_table_import_stream(address, ctypes.byref(handle)),
            lib,
        )
        yield handle
    finally:
        lib.irx_rb_c_stream_release(address)
        lib.irx_arrow_table_release(handle)


@private
@contextmanager
@typechecked
def schema_handle(
    schema: pa.Schema | None,
) -> Iterator[ctypes.c_void_p | None]:
    """
    title: Keep an optional imported schema alive through a native read.
    parameters:
      schema:
        type: pa.Schema | None
    returns:
      type: Iterator[ctypes.c_void_p | None]
    """
    if schema is None:
        yield None
        return
    owner = RecordBatchSchema.from_arrow(schema)
    try:
        yield owner._raw()
    finally:
        owner.release()


@private
@typechecked
def selection(
    values: Sequence[str] | None, name: str, allow_empty: bool = False
) -> tuple[str, ...] | None:
    """
    title: Validate and snapshot string selectors before native side effects.
    parameters:
      values:
        type: Sequence[str] | None
      name:
        type: str
      allow_empty:
        type: bool
    returns:
      type: tuple[str, Ellipsis] | None
    """
    if values is None:
        return None
    if isinstance(values, str):
        raise TypeError(f"{name} must be a sequence of strings, not a string")
    result = tuple(values)
    if not result and not allow_empty:
        raise ValueError(f"{name} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    for value in result:
        option_text(value)
        if not value and not allow_empty:
            raise ValueError(f"{name} must contain nonempty names")
    return result


@private
@contextmanager
@typechecked
def csv_options(
    lib: ctypes.CDLL,
    integers: dict[str, int],
    texts: dict[str, str],
    lists: dict[str, tuple[str, ...] | None],
) -> Iterator[ctypes.c_void_p]:
    """
    title: Own checked native CSV options for one operation.
    parameters:
      lib:
        type: ctypes.CDLL
      integers:
        type: dict[str, int]
      texts:
        type: dict[str, str]
      lists:
        type: dict[str, tuple[str, Ellipsis] | None]
    returns:
      type: Iterator[ctypes.c_void_p]
    """
    handle = ctypes.c_void_p(lib.irx_csv_options_new())
    if not handle:
        raise RuntimeError("Cannot allocate CSV options")
    try:
        for name, number in integers.items():
            option_integer(number)
            _check(lib.irx_csv_options_int(handle, name.encode(), number), lib)
        for name, text in texts.items():
            _check(
                lib.irx_csv_options_text(
                    handle, name.encode(), option_text(text)
                ),
                lib,
            )
        for name, values in lists.items():
            if values is None:
                continue
            _check(lib.irx_csv_options_clear(handle, name.encode()), lib)
            for value in values:
                _check(
                    lib.irx_csv_options_text(
                        handle, name.encode(), option_text(value)
                    ),
                    lib,
                )
        yield handle
    finally:
        lib.irx_csv_options_release(handle)


@public
@typechecked
def read_csv(
    path: str | os.PathLike[str],
    *,
    schema: pa.Schema | None = None,
    columns: Sequence[str] | None = None,
    names: Sequence[str] | None = None,
    delimiter: str = ",",
    header: bool = True,
    quotechar: str = '"',
    doublequote: bool = True,
    escapechar: str = "",
    skiprows: int = 0,
    skip_blank_lines: bool = False,
    null_values: Sequence[str] = ("",),
    block_size: int = 1048576,
) -> pa.Table:
    """
    title: Read all CSV rows with strict parsing before optional projection.
    summary: >-
      The eager result must fit in memory. Inference freezes after the first
      block; schema controls parsing. Names require header=False and no schema.
      Quoted empty strings remain strings, unlike default unquoted empty nulls.
    parameters:
      path:
        type: str | os.PathLike[str]
      schema:
        type: pa.Schema | None
      columns:
        type: Sequence[str] | None
      names:
        type: Sequence[str] | None
      delimiter:
        type: str
      header:
        type: bool
      quotechar:
        type: str
      doublequote:
        type: bool
      escapechar:
        type: str
      skiprows:
        type: int
      skip_blank_lines:
        type: bool
      null_values:
        type: Sequence[str]
      block_size:
        type: int
    returns:
      type: pa.Table
    """
    path_bytes = parquet_path(path)
    selected = selection(columns, "columns")
    named = selection(names, "names")
    nulls = selection(null_values, "null_values", allow_empty=True)
    lib = table_library()
    with (
        schema_handle(schema) as expected,
        csv_options(
            lib,
            {
                "header": int(header),
                "doublequote": int(doublequote),
                "skip_blank_lines": int(skip_blank_lines),
                "skiprows": skiprows,
                "block_size": block_size,
            },
            {
                "delimiter": delimiter,
                "quotechar": quotechar,
                "escapechar": escapechar,
            },
            {"columns": selected, "names": named, "null_values": nulls},
        ) as options,
    ):
        result = ctypes.c_void_p()
        _check(
            lib.irx_rb_csv_read_table(
                path_bytes, expected, options, ctypes.byref(result)
            ),
            lib,
        )
        return export_table(result, lib)


@public
@typechecked
def write_csv(
    frame: pa.Table,
    path: str | os.PathLike[str],
    *,
    delimiter: str = ",",
    header: bool = True,
    lineterminator: str = "\n",
    na_rep: str = "",
    quoting: Literal["needed", "all_valid", "none"] = "needed",
) -> None:
    """
    title: Write all chunks and check finalization without consuming the table.
    summary: >-
      CSV is nontransactional. Custom null tokens can collide with non-null
      data; use matching read null_values. Do not assume lossless roundtrips.
    parameters:
      frame:
        type: pa.Table
      path:
        type: str | os.PathLike[str]
      delimiter:
        type: str
      header:
        type: bool
      lineterminator:
        type: str
      na_rep:
        type: str
      quoting:
        type: Literal[needed, all_valid, none]
    """
    path_bytes = parquet_path(path)
    lib = table_library()
    with (
        csv_options(
            lib,
            {"header": int(header)},
            {
                "delimiter": delimiter,
                "lineterminator": lineterminator,
                "na_rep": na_rep,
                "quoting": quoting,
            },
            {},
        ) as options,
        import_table(frame, lib) as table,
    ):
        _check(lib.irx_rb_csv_write_table(table, path_bytes, options), lib)


@public
@typechecked
def read_parquet(
    path: str | os.PathLike[str],
    *,
    schema: pa.Schema | None = None,
    columns: Sequence[str] | None = None,
    filters: ParquetFilter | None = None,
    row_groups: Sequence[int] | None = None,
    options: ParquetOptions | None = None,
    batch_size: int | None = None,
) -> pa.Table:
    """
    title: Read exact rows, discovering files or Hive datasets by default.
    summary: >-
      Explicit keywords replace options snapshots without mutating the input.
      None means an omitted override. Schema asserts the final projected types.
    parameters:
      path:
        type: str | os.PathLike[str]
      schema:
        type: pa.Schema | None
      columns:
        type: Sequence[str] | None
      filters:
        type: ParquetFilter | None
      row_groups:
        type: Sequence[int] | None
      options:
        type: ParquetOptions | None
      batch_size:
        type: int | None
    returns:
      type: pa.Table
    """
    selected = selection(columns, "columns")
    effective = options or ParquetOptions()
    if selected is not None:
        effective = replace(effective, columns=selected)
    if filters is not None:
        effective = replace(effective, predicates=filters.predicates)
    if batch_size is not None:
        effective = replace(effective, batch_size=batch_size)
    if row_groups is not None:
        groups = tuple(row_groups)
        if not groups or len(groups) != len(set(groups)):
            raise ValueError("row_groups must be nonempty and unique")
        for group in groups:
            option_integer(group)
        effective = replace(effective, row_groups=groups)
    path_bytes = parquet_path(path)
    lib = table_library(parquet=True)
    with effective.native(lib) as native, schema_handle(schema) as expected:
        result = ctypes.c_void_p()
        _check(
            lib.irx_rb_parquet_read_table(
                path_bytes,
                expected,
                native,
                int(options is None),
                ctypes.byref(result),
            ),
            lib,
        )
        return export_table(result, lib)


@public
@typechecked
def write_parquet(
    frame: pa.Table,
    path: str | os.PathLike[str],
    *,
    compression: str | None = None,
    row_group_size: int | None = None,
    atomic: bool | None = None,
    durable: bool | None = None,
    append: bool | None = None,
    partition_columns: Sequence[str] | None = None,
    options: ParquetOptions | None = None,
) -> None:
    """
    title: Write exact table types using explicit overrides and checked close.
    summary: >-
      Default compression is snappy; row-group size is 1048576. Atomic writes
      are opt-in and POSIX-local; None means no keyword override. Partitioned
      output selects Hive dataset mode unless explicit options say otherwise.
    parameters:
      frame:
        type: pa.Table
      path:
        type: str | os.PathLike[str]
      compression:
        type: str | None
      row_group_size:
        type: int | None
      atomic:
        type: bool | None
      durable:
        type: bool | None
      append:
        type: bool | None
      partition_columns:
        type: Sequence[str] | None
      options:
        type: ParquetOptions | None
    """
    effective = options or ParquetOptions()
    if compression is not None:
        effective = replace(effective, compression=compression)
    if row_group_size is not None:
        effective = replace(effective, row_group_size=row_group_size)
    if atomic is not None:
        effective = replace(effective, atomic=atomic)
    if durable is not None:
        effective = replace(effective, durable=durable)
    if append is not None:
        effective = replace(effective, append=append)
    partitions = selection(partition_columns, "partition_columns")
    if partitions is not None:
        effective = replace(effective, partition_columns=partitions)
    path_bytes = parquet_path(path)
    lib = table_library(parquet=True)
    with effective.native(lib) as native, import_table(frame, lib) as table:
        _check(
            lib.irx_rb_parquet_write_table(
                table, path_bytes, native, int(options is None)
            ),
            lib,
        )
