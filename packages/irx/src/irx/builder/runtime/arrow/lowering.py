"""
title: LLVM call helpers for the generated Arrow runtime ABI.
"""

from __future__ import annotations

from typing import Sequence

from llvmlite import ir

from irx.builder.protocols import VisitorMixinBase
from irx.typecheck import typechecked


@typechecked
def call_arrow_runtime(
    visitor: VisitorMixinBase,
    function: ir.Function,
    arguments: Sequence[ir.Value],
    operation: str,
) -> tuple[ir.Value, ir.Value]:
    """
    title: Call a fallible Arrow function with an owned-error output slot.
    parameters:
      visitor:
        type: VisitorMixinBase
      function:
        type: ir.Function
      arguments:
        type: Sequence[ir.Value]
      operation:
        type: str
    returns:
      type: tuple[ir.Value, ir.Value]
    """
    error_slot = visitor._llvm.ir_builder.alloca(
        visitor._llvm.OPAQUE_POINTER_TYPE,
        name=f"{operation}_error_slot",
    )
    visitor._llvm.ir_builder.store(
        ir.Constant(visitor._llvm.OPAQUE_POINTER_TYPE, None),
        error_slot,
    )
    status = visitor._llvm.ir_builder.call(
        function,
        [*arguments, error_slot],
        name=f"{operation}_status",
    )
    return status, error_slot


__all__ = ["call_arrow_runtime"]
