"""
title: Vector helpers for llvmliteir codegen.
"""

from __future__ import annotations

from llvmlite import ir
from llvmlite.ir import VectorType

from irx.builder.types import is_fp_type
from irx.typecheck import typechecked


@typechecked
def is_vector(value: ir.Value) -> bool:
    """
    title: Is vector.
    parameters:
      value: Value to process.
    returns: 'Result of this operation: is vector.'
    """
    return isinstance(getattr(value, "type", None), VectorType)


@typechecked
def emit_int_div(
    ir_builder: ir.IRBuilder,
    lhs: ir.Value,
    rhs: ir.Value,
    unsigned: bool,
) -> ir.Instruction:
    """
    title: Emit int div.
    parameters:
      ir_builder: IR builder.
      lhs: Left operand.
      rhs: Right operand.
      unsigned: Whether to use unsigned semantics.
    returns: 'Result of this operation: emit int div.'
    """
    return (
        ir_builder.udiv(lhs, rhs, name="vdivtmp")
        if unsigned
        else ir_builder.sdiv(lhs, rhs, name="vdivtmp")
    )


@typechecked
def emit_add(
    ir_builder: ir.IRBuilder,
    lhs: ir.Value,
    rhs: ir.Value,
    name: str = "addtmp",
) -> ir.Instruction:
    """
    title: Emit add.
    parameters:
      ir_builder: IR builder.
      lhs: Left operand.
      rhs: Right operand.
      name: Name identifying the declaration or operation.
    returns: 'Result of this operation: emit add.'
    """
    if is_fp_type(lhs.type):
        return ir_builder.fadd(lhs, rhs, name=name)
    return ir_builder.add(lhs, rhs, name=name)


@typechecked
def splat_scalar(
    ir_builder: ir.IRBuilder,
    scalar: ir.Value,
    vec_type: ir.VectorType,
) -> ir.Value:
    """
    title: Splat scalar.
    parameters:
      ir_builder: IR builder.
      scalar: Scalar.
      vec_type: Type of vec.
    returns: 'Result of this operation: splat scalar.'
    """
    zero_i32 = ir.Constant(ir.IntType(32), 0)
    undef_vec = ir.Constant(vec_type, ir.Undefined)
    vector_zero = ir_builder.insert_element(undef_vec, scalar, zero_i32)
    mask_ty = ir.VectorType(ir.IntType(32), vec_type.count)
    mask = ir.Constant(mask_ty, [0] * vec_type.count)
    return ir_builder.shuffle_vector(vector_zero, undef_vec, mask)


__all__ = ["emit_add", "emit_int_div", "is_vector", "splat_scalar"]
