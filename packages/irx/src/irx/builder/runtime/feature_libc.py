"""
title: Libc runtime feature declarations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llvmlite import ir

from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    RuntimeFeature,
    declare_external_function,
)
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@typechecked
def build_libc_runtime_feature() -> RuntimeFeature:
    """
    title: Build the libc runtime feature specification.
    returns: Constructed the libc runtime feature specification.
    """
    return RuntimeFeature(
        name="libc",
        symbols={
            "exit": ExternalSymbolSpec("exit", _declare_exit),
            "free": ExternalSymbolSpec("free", _declare_free),
            "malloc": ExternalSymbolSpec("malloc", _declare_malloc),
            "puts": ExternalSymbolSpec("puts", _declare_puts),
            "snprintf": ExternalSymbolSpec("snprintf", _declare_snprintf),
        },
    )


@typechecked
def _declare_exit(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare exit.
    parameters:
      visitor: Visitor performing the traversal or lowering.
    returns: 'Result of this operation: declare exit.'
    """
    fn_type = ir.FunctionType(
        visitor._llvm.VOID_TYPE,
        [visitor._llvm.INT32_TYPE],
    )
    return declare_external_function(visitor._llvm.module, "exit", fn_type)


@typechecked
def _declare_malloc(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare malloc.
    parameters:
      visitor: Visitor performing the traversal or lowering.
    returns: 'Result of this operation: declare malloc.'
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT8_TYPE.as_pointer(),
        [visitor._llvm.SIZE_T_TYPE],
    )
    return declare_external_function(visitor._llvm.module, "malloc", fn_type)


@typechecked
def _declare_free(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare the C heap-release function.
    parameters:
      visitor: Visitor performing the traversal or lowering.
    returns: 'Result of this operation: declare the C heap-release function.'
    """
    fn_type = ir.FunctionType(
        visitor._llvm.VOID_TYPE,
        [visitor._llvm.INT8_TYPE.as_pointer()],
    )
    return declare_external_function(visitor._llvm.module, "free", fn_type)


@typechecked
def _declare_puts(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare puts.
    parameters:
      visitor: Visitor performing the traversal or lowering.
    returns: 'Result of this operation: declare puts.'
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [visitor._llvm.INT8_TYPE.as_pointer()],
    )
    return declare_external_function(visitor._llvm.module, "puts", fn_type)


@typechecked
def _declare_snprintf(visitor: VisitorProtocol) -> ir.Function:
    """
    title: Declare snprintf.
    parameters:
      visitor: Visitor performing the traversal or lowering.
    returns: 'Result of this operation: declare snprintf.'
    """
    fn_type = ir.FunctionType(
        visitor._llvm.INT32_TYPE,
        [
            visitor._llvm.INT8_TYPE.as_pointer(),
            visitor._llvm.SIZE_T_TYPE,
            visitor._llvm.INT8_TYPE.as_pointer(),
        ],
        var_arg=True,
    )
    return declare_external_function(visitor._llvm.module, "snprintf", fn_type)
