"""
title: Builtin dataframe runtime feature declarations backed by Arrow.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from llvmlite import ir
from public import private

from irx.builder.runtime.arrowcpp import (
    arrowcpp_compile_flags,
    arrowcpp_include_dirs,
    arrowcpp_linker_flags,
    arrowcpp_runtime_metadata,
)
from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@typechecked
def build_dataframe_runtime_feature() -> RuntimeFeature:
    """
    title: Build the builtin dataframe runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    runtime_root = Path(__file__).resolve().parent
    native_root = (runtime_root.parent / "arrow" / "native").resolve()
    buffer_native_root = (runtime_root.parent / "buffer" / "native").resolve()
    include_dirs = (
        native_root,
        buffer_native_root,
        *arrowcpp_include_dirs(),
    )
    artifacts = [
        NativeArtifact(
            kind="cxx_source",
            path=native_root / "irx_arrow_runtime.cc",
            include_dirs=include_dirs,
            compile_flags=arrowcpp_compile_flags(),
        )
    ]

    return RuntimeFeature(
        name="dataframe",
        symbols={
            "irx_arrow_table_from_ipc": ExternalSymbolSpec(
                "irx_arrow_table_from_ipc", declare_table_from_ipc
            ),
            "irx_arrow_series_set": ExternalSymbolSpec(
                "irx_arrow_series_set", declare_series_set
            ),
            "irx_arrow_series_slice": ExternalSymbolSpec(
                "irx_arrow_series_slice", declare_series_slice
            ),
            "irx_arrow_series_index": ExternalSymbolSpec(
                "irx_arrow_series_index", declare_series_index
            ),
            "irx_arrow_column_compute_promoted": ExternalSymbolSpec(
                "irx_arrow_column_compute_promoted",
                declare_column_compute_promoted,
            ),
            "irx_arrow_column_compute": ExternalSymbolSpec(
                "irx_arrow_column_compute", declare_column_compute
            ),
            "irx_arrow_table_new_from_arrays": ExternalSymbolSpec(
                "irx_arrow_table_new_from_arrays",
                _declare_table_new_from_arrays,
            ),
            "irx_arrow_table_num_rows": ExternalSymbolSpec(
                "irx_arrow_table_num_rows",
                _declare_table_num_rows,
            ),
            "irx_arrow_table_num_columns": ExternalSymbolSpec(
                "irx_arrow_table_num_columns",
                _declare_table_num_columns,
            ),
            "irx_arrow_table_column_by_name": ExternalSymbolSpec(
                "irx_arrow_table_column_by_name",
                _declare_table_column_by_name,
            ),
            "irx_arrow_table_column_by_index": ExternalSymbolSpec(
                "irx_arrow_table_column_by_index",
                _declare_table_column_by_index,
            ),
            "irx_arrow_table_retain": ExternalSymbolSpec(
                "irx_arrow_table_retain",
                _declare_table_retain,
            ),
            "irx_arrow_table_release": ExternalSymbolSpec(
                "irx_arrow_table_release",
                _declare_table_release,
            ),
            "irx_arrow_chunked_array_retain": ExternalSymbolSpec(
                "irx_arrow_chunked_array_retain",
                _declare_chunked_array_retain,
            ),
            "irx_arrow_chunked_array_release": ExternalSymbolSpec(
                "irx_arrow_chunked_array_release",
                _declare_chunked_array_release,
            ),
            "irx_arrow_last_error": ExternalSymbolSpec(
                "irx_arrow_last_error",
                _declare_last_error,
            ),
        },
        artifacts=tuple(artifacts),
        metadata={
            "opaque_handles": {
                "table": "irx_arrow_table_handle",
                "chunked_array": "irx_arrow_chunked_array_handle",
            },
            "canonical_name": "dataframe",
            **arrowcpp_runtime_metadata(),
        },
        linker_flags=arrowcpp_linker_flags(),
    )


@typechecked
def _declare_function(
    visitor: VisitorProtocol,
    name: str,
    return_type: ir.Type,
    arg_types: list[ir.Type],
) -> ir.Function:
    """
    title: Declare one Arrow dataframe runtime symbol.
    parameters:
      visitor:
        type: VisitorProtocol
      name:
        type: str
      return_type:
        type: ir.Type
      arg_types:
        type: list[ir.Type]
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(return_type, arg_types)
    return declare_external_function(visitor._llvm.module, name, fn_type)


@typechecked
def _declare_table_new_from_arrays(
    visitor: VisitorProtocol,
) -> ir.Function:
    """
    title: Declare Arrow table construction from arrays.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_new_from_arrays",
        visitor._llvm.INT32_TYPE,
        [
            visitor._llvm.INT64_TYPE,
            visitor._llvm.ASCII_STRING_TYPE.as_pointer(),
            visitor._llvm.ARRAY_HANDLE_TYPE.as_pointer(),
            visitor._llvm.TABLE_HANDLE_TYPE.as_pointer(),
        ],
    )


@typechecked
def _declare_table_num_rows(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare Arrow table row-count query.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_num_rows",
        visitor._llvm.INT64_TYPE,
        [visitor._llvm.TABLE_HANDLE_TYPE],
    )


@typechecked
def _declare_table_num_columns(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare Arrow table column-count query.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_num_columns",
        visitor._llvm.INT64_TYPE,
        [visitor._llvm.TABLE_HANDLE_TYPE],
    )


@typechecked
def _declare_table_column_by_name(
    visitor: VisitorProtocol,
) -> ir.Function:
    """
    title: Declare Arrow table column lookup by name.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_column_by_name",
        visitor._llvm.INT32_TYPE,
        [
            visitor._llvm.TABLE_HANDLE_TYPE,
            visitor._llvm.ASCII_STRING_TYPE,
            visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE.as_pointer(),
        ],
    )


@typechecked
def _declare_table_column_by_index(
    visitor: VisitorProtocol,
) -> ir.Function:
    """
    title: Declare Arrow table column lookup by index.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_column_by_index",
        visitor._llvm.INT32_TYPE,
        [
            visitor._llvm.TABLE_HANDLE_TYPE,
            visitor._llvm.INT32_TYPE,
            visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE.as_pointer(),
        ],
    )


@typechecked
def _declare_table_retain(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare Arrow table retain.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_retain",
        visitor._llvm.INT32_TYPE,
        [visitor._llvm.TABLE_HANDLE_TYPE],
    )


@typechecked
def _declare_table_release(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare Arrow table release.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_release",
        visitor._llvm.VOID_TYPE,
        [visitor._llvm.TABLE_HANDLE_TYPE],
    )


@typechecked
def _declare_chunked_array_retain(
    visitor: VisitorProtocol,
) -> ir.Function:
    """
    title: Declare Arrow chunked-array retain.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_chunked_array_retain",
        visitor._llvm.INT32_TYPE,
        [visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE],
    )


@typechecked
def _declare_chunked_array_release(
    visitor: VisitorProtocol,
) -> ir.Function:
    """
    title: Declare Arrow chunked-array release.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_chunked_array_release",
        visitor._llvm.VOID_TYPE,
        [visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE],
    )


@typechecked
def _declare_last_error(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare Arrow runtime last-error query.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_last_error",
        visitor._llvm.ASCII_STRING_TYPE,
        [],
    )


__all__ = ["build_dataframe_runtime_feature"]


@private
@typechecked
def declare_series_index(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare status-returning scalar access through opaque storage.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    i32, i64 = ir.IntType(32), ir.IntType(64)
    return _declare_function(
        visitor,
        "irx_arrow_series_index",
        i32,
        [
            visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE,
            i64,
            i32,
            i64.as_pointer(),
            i32.as_pointer(),
        ],
    )


@private
@typechecked
def declare_column_compute(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare a focused, checked Arrow scalar/Series kernel primitive.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    i32, i64 = ir.IntType(32), ir.IntType(64)
    column = visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE
    return _declare_function(
        visitor,
        "irx_arrow_column_compute",
        i32,
        [
            visitor._llvm.ASCII_STRING_TYPE,
            i32,
            column,
            i64,
            i32,
            column,
            i64,
            i32,
            column.as_pointer(),
            i64.as_pointer(),
            i32.as_pointer(),
        ],
    )


@private
@typechecked
def declare_series_slice(visitor: VisitorProtocol) -> ir.Function:
    """
    title: >-
      Declare a checked slice returning independently owned column storage.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    column = visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE
    return _declare_function(
        visitor,
        "irx_arrow_series_slice",
        ir.IntType(32),
        [
            column,
            ir.IntType(64),
            ir.IntType(64),
            ir.IntType(64),
            ir.IntType(32),
            column.as_pointer(),
        ],
    )


@private
@typechecked
def declare_column_compute_promoted(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare checked conversion to the semantic common operand type.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    original = declare_column_compute(visitor)
    return declare_external_function(
        visitor._llvm.module,
        "irx_arrow_column_compute_promoted",
        original.function_type,
    )


@private
@typechecked
def declare_series_set(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare checked copy-on-write Series element updates.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    i32, i64 = ir.IntType(32), ir.IntType(64)
    return _declare_function(
        visitor,
        "irx_arrow_series_set",
        i32,
        [visitor._llvm.CHUNKED_ARRAY_HANDLE_TYPE, i64, i32, i64, i32, i32],
    )


@private
@typechecked
def declare_table_from_ipc(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare owned DataFrame construction from a checked IPC literal.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    return _declare_function(
        visitor,
        "irx_arrow_table_from_ipc",
        ir.IntType(32),
        [
            ir.IntType(8).as_pointer(),
            ir.IntType(64),
            visitor._llvm.TABLE_HANDLE_TYPE.as_pointer(),
        ],
    )
