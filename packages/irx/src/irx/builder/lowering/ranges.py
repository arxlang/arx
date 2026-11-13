"""
title: Allocation-free integer range values, length, and checked indexing.
"""

from typing import TYPE_CHECKING, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import CallResolution, SemanticInfo
from irx.analysis.types import is_unsigned_type
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.runtime import safe_pop
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.lowering.functions import FunctionVisitorMixin


@private
@typechecked
def lower_range_call(
    visitor: VisitorCore, node: astx.FunctionCall, plan: CallResolution
) -> None:
    """
    title: Construct a fixed-size range after checking a nonzero i32 stride.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.FunctionCall
      plan:
        type: CallResolution
    """
    calls: FunctionVisitorMixin = cast("FunctionVisitorMixin", visitor)
    stop, start, step = calls.lower_bound_call_arguments(plan)
    builder = visitor._llvm.ir_builder
    integer = ir.IntType(64)
    start, stop, step = (
        builder.sext(value, integer) for value in (start, stop, step)
    )
    zero = ir.Constant(integer, 0)
    one = ir.Constant(integer, 1)
    visitor._guard_runtime_condition(
        node,
        builder.icmp_signed("!=", step, zero),
        code="ARX-RUNTIME-ASSERT-001",
        message="range() step must not be 0",
        block_name="range.step",
        exception_role="AssertionError",
    )
    ascending = builder.icmp_signed(">", step, zero)
    distance = builder.select(
        ascending, builder.sub(stop, start), builder.sub(start, stop)
    )
    stride = builder.select(ascending, step, builder.neg(step))
    positive = builder.icmp_signed(">", distance, zero)
    # Clamp before unsigned division; a wrong-direction interval is empty.
    distance = builder.select(positive, distance, zero)
    length = builder.udiv(
        builder.add(distance, builder.sub(stride, one)), stride
    )
    value = ir.Constant(ir.LiteralStructType([integer] * 3), None)
    for index, field in enumerate((start, step, length)):
        value = builder.insert_value(value, field, index)
    visitor.result_stack.append(value)


@private
@typechecked
def range_item(
    visitor: VisitorCore, value: ir.Value, index: ir.Value
) -> ir.Value:
    """
    title: Compute an element after a caller has proved index below length.
    parameters:
      visitor:
        type: VisitorCore
      value:
        type: ir.Value
      index:
        type: ir.Value
    returns:
      type: ir.Value
    """
    builder = visitor._llvm.ir_builder
    wide = builder.add(
        builder.extract_value(value, 0),
        builder.mul(index, builder.extract_value(value, 1)),
    )
    return builder.trunc(wide, ir.IntType(32))


@private
@typechecked
def lower_range_query(
    visitor: VisitorCore, node: astx.CollectionLength | astx.SubscriptExpr
) -> bool:
    """
    title: Consume range access metadata without materializing any values.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.CollectionLength | astx.SubscriptExpr
    returns:
      type: bool
    """
    info = getattr(node, "semantic", None)
    base = node.base if isinstance(node, astx.CollectionLength) else node.value
    if not isinstance(info, SemanticInfo) or not info.range_access:
        if isinstance(visitor._resolved_ast_type(base), astx.RangeType):
            require_semantic_metadata(
                None, node=node, metadata="range_access", context="range query"
            )
        return False
    visitor.visit_child(base)
    value = require_lowered_value(
        safe_pop(visitor.result_stack), node=base, context="range value"
    )
    builder = visitor._llvm.ir_builder
    length = builder.extract_value(value, 2)
    if isinstance(node, astx.CollectionLength):
        visitor.result_stack.append(length)
        return True
    visitor.visit_child(node.index)
    index = require_lowered_value(
        safe_pop(visitor.result_stack), node=node.index, context="range index"
    )
    index = visitor._cast_value_to_type(
        index,
        ir.IntType(64),
        unsigned=is_unsigned_type(visitor._resolved_ast_type(node.index)),
    )
    visitor._guard_runtime_condition(
        node,
        builder.icmp_unsigned("<", index, length),
        code="ARX-RUNTIME-RANGE-001",
        message="range index out of bounds",
        block_name="range.index",
        exception_role="IndexError",
    )
    visitor.result_stack.append(range_item(visitor, value, index))
    return True
