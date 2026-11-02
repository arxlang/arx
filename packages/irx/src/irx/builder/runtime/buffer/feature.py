"""
title: Buffer runtime feature declarations.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from llvmlite import ir
from public import private

from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.builder.runtime.sequence import declare_sequence_reader
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@typechecked
def build_buffer_runtime_feature() -> RuntimeFeature:
    """
    title: Build the buffer runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    runtime_root = Path(__file__).resolve().parent
    native_root = runtime_root / "native"
    return RuntimeFeature(
        name="buffer",
        symbols={
            "irx_buffer_sequence_read": ExternalSymbolSpec(
                "irx_buffer_sequence_read",
                partial(
                    declare_sequence_reader, name="irx_buffer_sequence_read"
                ),
            ),
            "irx_buffer_checked_offset": ExternalSymbolSpec(
                "irx_buffer_checked_offset", declare_checked_offset
            ),
            "irx_buffer_owner_external_new": ExternalSymbolSpec(
                "irx_buffer_owner_external_new",
                _declare_owner_external_new,
            ),
            "irx_buffer_owner_retain": ExternalSymbolSpec(
                "irx_buffer_owner_retain",
                _declare_owner_retain,
            ),
            "irx_buffer_owner_release": ExternalSymbolSpec(
                "irx_buffer_owner_release",
                _declare_owner_release,
            ),
            "irx_buffer_view_retain": ExternalSymbolSpec(
                "irx_buffer_view_retain",
                _declare_view_retain,
            ),
            "irx_buffer_view_release": ExternalSymbolSpec(
                "irx_buffer_view_release",
                _declare_view_release,
            ),
            "irx_buffer_last_error": ExternalSymbolSpec(
                "irx_buffer_last_error",
                _declare_last_error,
            ),
        },
        artifacts=(
            NativeArtifact(
                kind="c_source",
                path=native_root / "irx_buffer_runtime.c",
                include_dirs=(native_root,),
                compile_flags=("-std=c99",),
            ),
        ),
        metadata={
            "opaque_handles": {"owner": "irx_buffer_owner_handle"},
            "view_type": "irx_buffer_view",
        },
    )


@private
@typechecked
def declare_checked_offset(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare rank, bounds and byte-offset validation.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    integer = visitor._llvm.INT64_TYPE
    return declare_external_function(
        visitor._llvm.module,
        "irx_buffer_checked_offset",
        ir.FunctionType(
            visitor._llvm.INT32_TYPE,
            [
                visitor._llvm.BUFFER_VIEW_TYPE.as_pointer(),
                integer.as_pointer(),
                visitor._llvm.INT32_TYPE,
                integer,
                integer.as_pointer(),
            ],
        ),
    )


@typechecked
def _declare_owner_external_new(
    visitor: VisitorProtocol,
) -> ir.Function:
    """
    title: Declare owner external new.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [
            visitor._llvm.OPAQUE_POINTER_TYPE,
            visitor._llvm.OPAQUE_POINTER_TYPE,
            visitor._llvm.BUFFER_OWNER_HANDLE_TYPE.as_pointer(),
        ],
    )
    return declare_external_function(
        visitor._llvm.module,
        "irx_buffer_owner_external_new",
        fn_type,
    )


@typechecked
def _declare_owner_retain(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare owner retain.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [visitor._llvm.BUFFER_OWNER_HANDLE_TYPE],
    )
    return declare_external_function(
        visitor._llvm.module,
        "irx_buffer_owner_retain",
        fn_type,
    )


@typechecked
def _declare_owner_release(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare owner release.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [visitor._llvm.BUFFER_OWNER_HANDLE_TYPE],
    )
    return declare_external_function(
        visitor._llvm.module,
        "irx_buffer_owner_release",
        fn_type,
    )


@typechecked
def _declare_view_retain(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare view retain.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [visitor._llvm.BUFFER_VIEW_TYPE.as_pointer()],
    )
    return declare_external_function(
        visitor._llvm.module,
        "irx_buffer_view_retain",
        fn_type,
    )


@typechecked
def _declare_view_release(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare view release.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [visitor._llvm.BUFFER_VIEW_TYPE.as_pointer()],
    )
    return declare_external_function(
        visitor._llvm.module,
        "irx_buffer_view_release",
        fn_type,
    )


@typechecked
def _declare_last_error(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare last error.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.OPAQUE_POINTER_TYPE,
        [],
    )
    return declare_external_function(
        visitor._llvm.module,
        "irx_buffer_last_error",
        fn_type,
    )
