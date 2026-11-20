"""
title: Typed configuration for native Parquet sessions.
"""

from __future__ import annotations

import ctypes

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Literal

from public import private, public

from irx.typecheck import skip_unused, typechecked


@public
@typechecked
@dataclass(frozen=True)
class ParquetPredicate:
    """
    title: One typed comparison; multiple predicates are combined with AND.
    attributes:
      column: Column to process.
      operation: Operation to resolve or execute.
      value: Stored value.
    """

    column: str
    operation: Literal[
        "eq", "ne", "lt", "le", "gt", "ge", "is_null", "is_valid"
    ]
    value: str | int | float | bool = ""

    def __post_init__(self) -> None:
        """
        title: Reject invalid comparisons rather than stringifying arbitrary
          values.
        """
        validate_predicate(self.column, self.operation, self.value)


@private
@typechecked
def option_text(value: str) -> bytes:
    """
    title: Reject NUL before passing option text across a C-string boundary.
    parameters:
      value: Value to process.
    returns: 'Result of this operation: reject NUL before passing option
      text across a C-string boundary.'
    """
    if "\0" in value:
        raise ValueError("Parquet option text must not contain NUL")
    return value.encode("utf-8")


@public
@typechecked
@dataclass(frozen=True)
class ParquetOptions:
    """
    title: Options copied into a native Parquet session at open time.
    summary: Empty columns/row_groups select all. Dataset evolution unions
      same-typed fields only. Atomic replacement and rewrite append are
      POSIX-local operations with advisory writer exclusion and optional
      fsync durability. Reconstruct preserves supported logical types over
      explicit physical storage for single files. Raw AES keys are excluded
      from repr; callers own key distribution and lifetime.
    attributes:
      batch_size: Size of batch.
      row_group_size: Size of row group.
      data_page_size: Size of data page.
      compression: Compression.
      compression_level: Compression level.
      columns: Column declarations or values.
      partition_columns: Partition columns.
      row_groups: Row groups.
      predicates: Predicates.
      use_threads: Whether to use use threads.
      pre_buffer: Whether to use pre buffer.
      dataset: Whether to use dataset.
      hive: Whether to use hive.
      unify: Whether to use unify.
      normalize: Whether to use normalize.
      atomic: Whether to use atomic.
      durable: Whether to use durable.
      reconstruct: Whether to use reconstruct.
      append: Whether to use append.
      encryption_key: Encryption key.
    """

    batch_size: int = 65536
    row_group_size: int = 1048576
    data_page_size: int = 1048576
    compression: str = "snappy"
    compression_level: int | None = None
    columns: tuple[str, ...] = ()
    partition_columns: tuple[str, ...] = ()
    row_groups: tuple[int, ...] = ()
    predicates: tuple[ParquetPredicate, ...] = ()
    use_threads: bool = False
    pre_buffer: bool = False
    dataset: bool = False
    hive: bool = False
    unify: bool = False
    normalize: bool = False
    atomic: bool = False
    durable: bool = False
    reconstruct: bool = False
    append: bool = False
    encryption_key: bytes | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """
        title: Validate collection items and secrets before any native side
          effect.
        """
        validate_option_items(
            self.columns,
            self.partition_columns,
            self.row_groups,
            self.predicates,
            self.encryption_key,
        )

    @contextmanager
    def native(self, lib: ctypes.CDLL) -> Iterator[ctypes.c_void_p]:
        """
        title: Create and release a temporary checked native options owner.
        parameters:
          lib: Lib.
        returns: Created and release a temporary checked native options owner.
        """
        from irx.record_batch import _check  # noqa: PLC0415

        pointer = ctypes.c_void_p
        signatures = {
            "new": (pointer, []),
            "release": (None, [pointer]),
            "int": (ctypes.c_int, [pointer, ctypes.c_char_p, ctypes.c_int64]),
            "text": (
                ctypes.c_int,
                [pointer, ctypes.c_char_p, ctypes.c_char_p],
            ),
            "key": (ctypes.c_int, [pointer, pointer, ctypes.c_int64]),
            "filter": (
                ctypes.c_int,
                [
                    pointer,
                    ctypes.c_char_p,
                    ctypes.c_char_p,
                    ctypes.c_char_p,
                    ctypes.c_char_p,
                ],
            ),
        }
        try:
            for name, (result, arguments) in signatures.items():
                function = getattr(lib, "irx_parquet_options_" + name)
                function.restype = result
                function.argtypes = arguments
        except AttributeError as error:
            raise RuntimeError(
                "Native library lacks Parquet options; rebuild the runtime"
            ) from error
        handle = pointer(lib.irx_parquet_options_new())
        if not handle:
            raise RuntimeError("Cannot allocate Parquet options")
        try:
            integers = {
                "batch_size": self.batch_size,
                "row_group_size": self.row_group_size,
                "data_page_size": self.data_page_size,
            }
            if self.compression_level is not None:
                integers["compression_level"] = self.compression_level
            for name, value in integers.items():
                option_integer(value)
                _check(
                    lib.irx_parquet_options_int(handle, name.encode(), value),
                    lib,
                )
            for name in (
                "use_threads",
                "pre_buffer",
                "dataset",
                "hive",
                "unify",
                "normalize",
                "atomic",
                "durable",
                "reconstruct",
                "append",
            ):
                value = getattr(self, name)
                if type(value) is not bool:
                    raise TypeError(f"{name} must be bool")
                # Older explicit ABI overrides need not know unused new flags.
                if name in ("durable", "reconstruct") and not value:
                    continue
                _check(
                    lib.irx_parquet_options_int(
                        handle, name.encode(), int(value)
                    ),
                    lib,
                )
            _check(
                lib.irx_parquet_options_text(
                    handle, b"compression", option_text(self.compression)
                ),
                lib,
            )
            for column in self.columns:
                _check(
                    lib.irx_parquet_options_text(
                        handle, b"column", option_text(column)
                    ),
                    lib,
                )
            for column in self.partition_columns:
                _check(
                    lib.irx_parquet_options_text(
                        handle, b"partition_column", option_text(column)
                    ),
                    lib,
                )
            for group in self.row_groups:
                option_integer(group)
                _check(
                    lib.irx_parquet_options_int(handle, b"row_group", group),
                    lib,
                )
            for predicate in self.predicates:
                literal = predicate.value
                if type(literal) is bool:
                    kind = b"bool"
                    text = "true" if literal else "false"
                elif isinstance(literal, int):
                    option_integer(literal)
                    kind, text = b"int64", str(literal)
                elif isinstance(literal, float):
                    kind, text = b"double", repr(literal)
                else:
                    kind, text = b"string", str(literal)
                _check(
                    lib.irx_parquet_options_filter(
                        handle,
                        option_text(predicate.column),
                        option_text(predicate.operation),
                        option_text(text),
                        kind,
                    ),
                    lib,
                )
            if self.encryption_key is not None:
                key = self.encryption_key
                _check(lib.irx_parquet_options_key(handle, key, len(key)), lib)
            yield handle
        finally:
            lib.irx_parquet_options_release(handle)


@private
@typechecked
def option_integer(value: int) -> None:
    """
    title: Reject bool and integer truncation at the native ABI boundary.
    parameters:
      value: Value to process.
    """
    if isinstance(value, bool) or not -(1 << 63) <= value < (1 << 63):
        raise ValueError(
            "Parquet integer options require signed 64-bit integers"
        )


@private
@typechecked
def validate_option_items(
    columns: tuple[str, ...],
    partition_columns: tuple[str, ...],
    row_groups: tuple[int, ...],
    predicates: tuple[ParquetPredicate, ...],
    encryption_key: bytes | None,
) -> None:
    """
    title: Runtime-check every item of options collections via the IRx wrapper.
    parameters:
      columns: Column declarations or values.
      partition_columns: Partition columns.
      row_groups: Row groups.
      predicates: Predicates.
      encryption_key: Encryption key.
    """
    skip_unused(
        columns, partition_columns, row_groups, predicates, encryption_key
    )


@private
@typechecked
def validate_predicate(
    column: str,
    operation: Literal[
        "eq", "ne", "lt", "le", "gt", "ge", "is_null", "is_valid"
    ],
    value: str | int | float | bool,
) -> None:
    """
    title: Runtime-check all predicate fields with the owning package wrapper.
    parameters:
      column: Column to process.
      operation: Operation to resolve or execute.
      value: Value to process.
    """
    skip_unused(column, operation, value)
