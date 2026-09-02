"""
title: Generic fatal runtime diagnostic feature declarations.
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
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol

RUNTIME_FAILURE_FEATURE_NAME = "errors"
RUNTIME_FAILURE_SYMBOL_NAME = "__arx_runtime_fail"


@typechecked
def build_runtime_failure_feature() -> RuntimeFeature:
    """
    title: Build the generic fatal runtime diagnostic feature.
    returns:
      type: RuntimeFeature
    """
    native_root = Path(__file__).resolve().parent / "native"
    return RuntimeFeature(
        name=RUNTIME_FAILURE_FEATURE_NAME,
        symbols={
            RUNTIME_FAILURE_SYMBOL_NAME: ExternalSymbolSpec(
                RUNTIME_FAILURE_SYMBOL_NAME,
                _declare_runtime_failure,
            ),
        },
        artifacts=(
            NativeArtifact(
                kind="c_source",
                path=native_root / "irx_error_runtime.c",
                include_dirs=(native_root,),
                compile_flags=("-std=c99",),
            ),
        ),
        metadata={
            "protocol": "ARX_RUNTIME_FAIL|code|source|line|col|message",
            "exit_status": 1,
        },
    )


@typechecked
def _declare_runtime_failure(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare the fatal runtime diagnostic function.
    parameters:
      visitor:
        type: VisitorProtocol
    returns:
      type: ir.Function
    """
    string_pointer = visitor._llvm.INT8_TYPE.as_pointer()
    fn_type = ir.FunctionType(
        visitor._llvm.VOID_TYPE,
        [
            string_pointer,
            string_pointer,
            visitor._llvm.INT32_TYPE,
            visitor._llvm.INT32_TYPE,
            string_pointer,
        ],
    )
    return declare_external_function(
        visitor._llvm.module,
        RUNTIME_FAILURE_SYMBOL_NAME,
        fn_type,
    )
