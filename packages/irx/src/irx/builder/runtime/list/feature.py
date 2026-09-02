"""
title: Dynamic-list runtime feature declarations.
summary: >-
  Declare append, checked status, index, and idempotent storage destruction for
  IRX lists. Language-level cleanup insertion remains owned by semantic
  ownership metadata and lowering.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from llvmlite import ir

from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.builtins.collections.list import (
    LIST_APPEND_SYMBOL,
    LIST_AT_SYMBOL,
    LIST_DESTROY_SYMBOL,
    LIST_REQUIRE_OK_SYMBOL,
)
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@typechecked
def build_list_runtime_feature() -> RuntimeFeature:
    """
    title: Build the dynamic-list runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    native_root = Path(__file__).resolve().parent / "native"
    return RuntimeFeature(
        name="list",
        symbols={
            LIST_APPEND_SYMBOL: ExternalSymbolSpec(
                LIST_APPEND_SYMBOL,
                _declare_list_append,
            ),
            LIST_AT_SYMBOL: ExternalSymbolSpec(
                LIST_AT_SYMBOL,
                _declare_list_at,
            ),
            LIST_DESTROY_SYMBOL: ExternalSymbolSpec(
                LIST_DESTROY_SYMBOL,
                _declare_list_destroy,
            ),
            LIST_REQUIRE_OK_SYMBOL: ExternalSymbolSpec(
                LIST_REQUIRE_OK_SYMBOL,
                _declare_list_require_ok,
            ),
        },
        artifacts=(
            NativeArtifact(
                kind="c_source",
                path=native_root / "irx_list_runtime.c",
                include_dirs=(native_root,),
                compile_flags=("-std=c99",),
            ),
        ),
        metadata={
            "canonical_name": "list",
            "symbols": (
                LIST_APPEND_SYMBOL,
                LIST_AT_SYMBOL,
                LIST_DESTROY_SYMBOL,
                LIST_REQUIRE_OK_SYMBOL,
            ),
            "limitations": (
                "scalar element storage only",
                "borrowed and static list values cannot be moved into owned "
                "locals",
                "owned list locals in generators are not supported yet",
            ),
        },
    )


@typechecked
def _list_llvm_type(visitor: VisitorProtocol) -> ir.LiteralStructType:
    """
    title: Return the canonical lowered list ABI type.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.LiteralStructType
    """
    return ir.LiteralStructType(
        [
            visitor._llvm.INT8_TYPE.as_pointer(),
            visitor._llvm.INT64_TYPE,
            visitor._llvm.INT64_TYPE,
            visitor._llvm.INT64_TYPE,
        ]
    )


@typechecked
def _declare_list_append(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare the dynamic-list append helper.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [
            _list_llvm_type(visitor).as_pointer(),
            visitor._llvm.INT8_TYPE.as_pointer(),
        ],
    )
    return declare_external_function(
        visitor._llvm.module,
        LIST_APPEND_SYMBOL,
        fn_type,
    )


@typechecked
def _declare_list_at(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare the dynamic-list indexed-access helper.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT8_TYPE.as_pointer(),
        [
            _list_llvm_type(visitor).as_pointer(),
            visitor._llvm.INT64_TYPE,
        ],
    )
    return declare_external_function(
        visitor._llvm.module,
        LIST_AT_SYMBOL,
        fn_type,
    )


@typechecked
def _declare_list_destroy(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare the idempotent dynamic-list storage destructor.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.VOID_TYPE,
        [_list_llvm_type(visitor).as_pointer()],
    )
    return declare_external_function(
        visitor._llvm.module,
        LIST_DESTROY_SYMBOL,
        fn_type,
    )


@typechecked
def _declare_list_require_ok(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare the fail-closed dynamic-list status checker.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    fn_type = ir.FunctionType(
        visitor._llvm.VOID_TYPE,
        [visitor._llvm.INT32_TYPE],
    )
    return declare_external_function(
        visitor._llvm.module,
        LIST_REQUIRE_OK_SYMBOL,
        fn_type,
    )
