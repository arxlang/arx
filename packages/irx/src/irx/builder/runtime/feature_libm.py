"""
title: Bounded f64 C-libm declarations and native link requirements.
summary: >-
  sqrt, exp, and log take one f64; pow takes two. All return f64 using native C
  domain, NaN, infinity, and overflow behavior, not Python math exceptions.
  Only native Linux/Darwin targets are enabled; other targets fail explicitly.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import astx

from llvmlite import binding as llvm
from llvmlite import ir
from public import private

from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    RuntimeFeature,
    declare_external_function,
)
from irx.native import NativeFunctionABI
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@typechecked
def build_libm_runtime_feature() -> RuntimeFeature:
    """
    title: Build the libm runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    arities = {"sqrt": 1, "exp": 1, "log": 1, "pow": 2}
    triple = llvm.get_default_triple().lower()
    supported = "-linux" in triple or "-darwin" in triple
    return RuntimeFeature(
        name="libm",
        symbols={
            name: ExternalSymbolSpec(
                name,
                partial(declare_libm_symbol, name=name, argument_count=arity),
                ffi_abi=NativeFunctionABI(
                    tuple(astx.Float64() for _ in range(arity)),
                    astx.Float64(),
                ),
            )
            for name, arity in arities.items()
        },
        linker_flags=("-lm",) if supported else (),
        unavailable_reason=(
            None
            if supported
            else f"C libm requires a native Linux/Darwin target; got {triple}"
        ),
    )


@private
@typechecked
def declare_libm_symbol(
    visitor: VisitorProtocol, *, name: str, argument_count: int
) -> ir.Function:
    """
    title: Declare one unary or binary all-f64 function from the libm catalog.
    parameters:
      visitor:
        type: VisitorProtocol
      name:
        type: str
      argument_count:
        type: int
    returns:
      type: ir.Function
    """
    if argument_count not in (1, 2):
        raise ValueError("libm declarations require one or two f64 arguments")
    fn_type = ir.FunctionType(
        visitor._llvm.DOUBLE_TYPE,
        [visitor._llvm.DOUBLE_TYPE] * argument_count,
    )
    return declare_external_function(visitor._llvm.module, name, fn_type)
