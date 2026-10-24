"""
title: Checked numeric execution from resolved semantic plans.
summary: >-
  Guards precede unsafe conversions, mutation, and result publication. LLVM
  overflow intrinsics do not rely on undefined signed-overflow flags. Runtime
  failures use the registered reporter at every optimization level.
"""

from __future__ import annotations

import astx

from llvmlite import ir
from public import private

from irx.analysis.numeric_policy import (
    NumericConversion,
    NumericConversionKind,
    integer_bounds,
)
from irx.analysis.resolved_nodes import ResolvedOperator
from irx.analysis.types import is_unsigned_type
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import require_semantic_metadata
from irx.typecheck import typechecked


@private
@typechecked
def numeric_guard(
    visitor: VisitorCore, node: astx.AST, valid: ir.Value, *, conversion: bool
) -> None:
    """
    title: Deliver a deterministic arithmetic or conversion failure.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.AST
      valid:
        type: ir.Value
      conversion:
        type: bool
    """
    visitor._guard_runtime_condition(
        node,
        valid,
        code="ARX-RUNTIME-CONVERSION-001"
        if conversion
        else "ARX-RUNTIME-ARITHMETIC-001",
        message="numeric conversion is out of range"
        if conversion
        else "integer arithmetic result is out of range",
        block_name="numeric.conversion"
        if conversion
        else "numeric.arithmetic",
        exception_role="OverflowError",
    )


@private
@typechecked
def integer_operation(
    visitor: VisitorCore,
    node: astx.AST,
    lhs: ir.Value,
    rhs: ir.Value,
    plan: ResolvedOperator,
    operator: str,
) -> ir.Value:
    """
    title: >-
      Emit checked or explicitly wrapping integer arithmetic, including SIMD.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.AST
      lhs:
        type: ir.Value
      rhs:
        type: ir.Value
      plan:
        type: ResolvedOperator
      operator:
        type: str
    returns:
      type: ir.Value
    """
    builder = visitor._llvm.ir_builder
    name = {"+": "add", "-": "sub", "*": "mul"}[operator]
    if plan.mode is astx.NumericMode.WRAPPING:
        return getattr(builder, name)(lhs, rhs, name + "tmp")
    scalar = (
        lhs.type.element if isinstance(lhs.type, ir.VectorType) else lhs.type
    )
    if not isinstance(scalar, ir.IntType) or lhs.type != rhs.type:
        raise TypeError(
            "checked integer arithmetic requires matching integer storage"
        )
    suffix = f"i{scalar.width}"
    flag_type: ir.Type = ir.IntType(1)
    if isinstance(lhs.type, ir.VectorType):
        suffix = f"v{lhs.type.count}" + suffix
        flag_type = ir.VectorType(ir.IntType(1), lhs.type.count)
    sign = "u" if plan.flags.unsigned else "s"
    intrinsic_name = f"llvm.{sign}{name}.with.overflow.{suffix}"
    intrinsic = visitor._llvm.module.globals.get(intrinsic_name)
    if intrinsic is None:
        intrinsic = ir.Function(
            visitor._llvm.module,
            ir.FunctionType(
                ir.LiteralStructType([lhs.type, flag_type]),
                [lhs.type, rhs.type],
            ),
            intrinsic_name,
        )
    if not isinstance(intrinsic, ir.Function):
        raise TypeError("overflow intrinsic symbol is not a function")
    pair = builder.call(intrinsic, [lhs, rhs], name="checked." + name)
    result = builder.extract_value(pair, 0, name + "tmp")
    overflow = builder.extract_value(pair, 1, "overflow")
    if isinstance(flag_type, ir.VectorType):
        any_overflow: ir.Value = ir.Constant(ir.IntType(1), 0)
        for lane in range(flag_type.count):
            bit = builder.extract_element(
                overflow, ir.Constant(ir.IntType(32), lane)
            )
            any_overflow = builder.or_(any_overflow, bit)
        overflow = any_overflow
    numeric_guard(visitor, node, builder.not_(overflow), conversion=False)
    return result


@private
@typechecked
def resolved_integer_operation(
    visitor: VisitorCore,
    node: astx.AST,
    lhs: ir.Value,
    rhs: ir.Value,
    operator: str,
) -> ir.Value:
    """
    title: >-
      Require an analyzed arithmetic plan before emitting a checked operation.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.AST
      lhs:
        type: ir.Value
      rhs:
        type: ir.Value
      operator:
        type: str
    returns:
      type: ir.Value
    """
    semantic = require_semantic_metadata(
        getattr(node, "semantic", None),
        node=node,
        metadata="semantic",
        context="integer arithmetic",
    )
    plan = require_semantic_metadata(
        semantic.resolved_operator,
        node=node,
        metadata="resolved_operator",
        context="integer arithmetic",
    )
    return integer_operation(visitor, node, lhs, rhs, plan, operator)


@private
@typechecked
def finite_value(visitor: VisitorCore, value: ir.Value) -> ir.Value:
    """
    title: >-
      Test finiteness without rejecting preexisting floating NaN or infinity.
    parameters:
      visitor:
        type: VisitorCore
      value:
        type: ir.Value
    returns:
      type: ir.Value
    """
    builder = visitor._llvm.ir_builder
    above = builder.fcmp_ordered(
        ">", value, ir.Constant(value.type, float("-inf"))
    )
    below = builder.fcmp_ordered(
        "<", value, ir.Constant(value.type, float("inf"))
    )
    return builder.and_(above, below)


@private
@typechecked
def numeric_cast(
    visitor: VisitorCore,
    node: astx.Cast,
    value: ir.Value,
    plan: NumericConversion,
    mode: astx.NumericMode,
) -> ir.Value:
    """
    title: >-
      Convert a valid scalar payload using the analyzed conversion contract.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.Cast
      value:
        type: ir.Value
      plan:
        type: NumericConversion
      mode:
        type: astx.NumericMode
    returns:
      type: ir.Value
    """
    builder = visitor._llvm.ir_builder
    if mode is astx.NumericMode.CHECKED and plan.requires_range_check:
        if plan.kind is NumericConversionKind.INTEGER_RANGE:
            bounds = integer_bounds(plan.target_type)
            assert bounds is not None

            wide = ir.IntType(128)
            extended = (
                builder.zext
                if is_unsigned_type(plan.source_type)
                else builder.sext
            )(value, wide)
            valid = builder.and_(
                builder.icmp_signed(
                    ">=", extended, ir.Constant(wide, bounds[0])
                ),
                builder.icmp_signed(
                    "<=", extended, ir.Constant(wide, bounds[1])
                ),
            )
            numeric_guard(visitor, node, valid, conversion=True)
        elif plan.kind is NumericConversionKind.FLOAT_TO_INTEGER:
            bounds = integer_bounds(plan.target_type)
            assert bounds is not None
            double: ir.Value = value
            if not isinstance(value.type, ir.DoubleType):
                double = builder.fpext(value, ir.DoubleType())
            # NaN is an invalid value, unlike infinity or a finite value
            # outside the target range, both of which are overflow failures.
            visitor._guard_runtime_condition(
                node,
                builder.fcmp_ordered("==", double, double),
                code="ARX-RUNTIME-CONVERSION-001",
                message="cannot convert NaN to an integer",
                block_name="numeric.conversion.nan",
                exception_role="ValueError",
            )
            # LLVM may lower truncation to a libm call on baseline targets.
            visitor.runtime_features.activate("libm")
            trunc = visitor._llvm.module.declare_intrinsic(
                "llvm.trunc", [ir.DoubleType()]
            )
            truncated = builder.call(trunc, [double])
            valid = builder.and_(
                builder.fcmp_ordered(
                    ">=",
                    truncated,
                    ir.Constant(ir.DoubleType(), float(bounds[0])),
                ),
                builder.fcmp_ordered(
                    "<",
                    truncated,
                    ir.Constant(ir.DoubleType(), float(bounds[1] + 1)),
                ),
            )
            numeric_guard(visitor, node, valid, conversion=True)
            target = require_semantic_metadata(
                visitor._llvm_type_for_ast_type(plan.target_type),
                node=node,
                metadata="cast target",
                context="numeric cast",
            )
            return (builder.fptoui if bounds[0] == 0 else builder.fptosi)(
                truncated, target
            )
    result = visitor._cast_ast_value(
        value, source_type=plan.source_type, target_type=plan.target_type
    )
    if mode is astx.NumericMode.CHECKED and plan.requires_range_check:
        if plan.kind is NumericConversionKind.INTEGER_TO_FLOAT:
            numeric_guard(
                visitor, node, finite_value(visitor, result), conversion=True
            )
        elif plan.kind is NumericConversionKind.FLOAT_NARROW:
            valid = builder.or_(
                builder.not_(finite_value(visitor, value)),
                finite_value(visitor, result),
            )
            numeric_guard(visitor, node, valid, conversion=True)
    return result


@private
@typechecked
def lower_numeric_cast(
    visitor: VisitorCore,
    node: astx.Cast,
    value: ir.Value,
    plan: NumericConversion,
    mode: astx.NumericMode,
) -> ir.Value:
    """
    title: Guard nullable conversion payloads only when the input is valid.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.Cast
      value:
        type: ir.Value
      plan:
        type: NumericConversion
      mode:
        type: astx.NumericMode
    returns:
      type: ir.Value
    """
    source = visitor._resolved_ast_type(node.value)
    target = visitor._resolved_ast_type(node)
    if not isinstance(target, astx.NullableType):
        return numeric_cast(visitor, node, value, plan, mode)
    builder = visitor._llvm.ir_builder
    target_llvm = require_semantic_metadata(
        visitor._llvm_type_for_ast_type(target),
        node=node,
        metadata="nullable cast target",
        context="numeric cast",
    )
    null_block = builder.block
    valid: ir.Value = ir.Constant(ir.IntType(1), 1)
    merge = None
    if isinstance(source, astx.NullableType):
        valid = builder.extract_value(value, 0)
        payload = builder.extract_value(value, 1)
        live = builder.function.append_basic_block("cast.valid")
        merge = builder.function.append_basic_block("cast.merge")
        builder.cbranch(valid, live, merge)
        builder.position_at_start(live)
        value = payload
    result = numeric_cast(visitor, node, value, plan, mode)
    boxed = builder.insert_value(ir.Constant(target_llvm, None), valid, 0)
    boxed = builder.insert_value(boxed, result, 1)
    if merge is None:
        return boxed
    live_end = builder.block
    builder.branch(merge)
    builder.position_at_start(merge)
    output = builder.phi(target_llvm)
    output.add_incoming(ir.Constant(target_llvm, None), null_block)
    output.add_incoming(boxed, live_end)
    return output


@private
@typechecked
def guard_collection_length(
    visitor: VisitorCore, node: astx.AST, length: ir.Value
) -> None:
    """
    title: Keep i32 collection length, index, and count results representable.
    summary: The backing ABI uses i64 lengths; no narrowing may silently wrap.
    parameters:
      visitor:
        type: VisitorCore
      node:
        type: astx.AST
      length:
        type: ir.Value
    """
    builder = visitor._llvm.ir_builder
    valid = builder.icmp_unsigned(
        "<=", length, ir.Constant(length.type, (1 << 31) - 1)
    )
    numeric_guard(visitor, node, valid, conversion=True)
