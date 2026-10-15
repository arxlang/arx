"""
title: LLVM call helpers for the generated Arrow runtime ABI.
"""

from __future__ import annotations

from typing import Any, Sequence, cast

import astx

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


@typechecked
def require_arrow_runtime_success(
    visitor: VisitorMixinBase,
    node: astx.AST,
    status: ir.Value,
    operation: str,
) -> None:
    """
    title: Fail through the structured runtime path unless Arrow succeeded.
    parameters:
      visitor:
        type: VisitorMixinBase
      node:
        type: astx.AST
      status:
        type: ir.Value
      operation:
        type: str
    """
    ok = visitor._llvm.ir_builder.icmp_signed(
        "==",
        status,
        ir.Constant(visitor._llvm.INT32_TYPE, 0),
        name=f"{operation}_ok",
    )
    cast(Any, visitor)._guard_runtime_condition(
        node,
        ok,
        code="ARX-RUNTIME-ARROW-001",
        message=f"Arrow runtime operation failed: {operation}",
        block_name=f"arrow.{operation}",
    )


__all__ = ["call_arrow_runtime", "require_arrow_runtime_success"]
