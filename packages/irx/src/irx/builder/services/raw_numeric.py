"""
title: Raw LLVM storage adaptation without source conversion policy.
"""

from collections.abc import Callable

import astx

from llvmlite import ir
from llvmlite.ir import DoubleType, FloatType, HalfType
from public import private

from irx.analysis.types import (
    is_boolean_type,
    is_float_type,
    is_integer_type,
)
from irx.builder.types import is_fp_type
from irx.builder.vector import is_vector
from irx.typecheck import typechecked

try:
    from llvmlite.ir import FP128Type
except ImportError:  # pragma: no cover - optional LLVM representation
    FP128Type = None

FLOAT16_BITS = 16
FLOAT32_BITS = 32
FLOAT64_BITS = 64
FLOAT128_BITS = 128


@private
@typechecked
class RawNumericEmission:
    """
    title: Explicit raw LLVM representation adaptation, not semantic analysis.
    summary: >-
      These helpers adapt already selected LLVM storage representations. Source
      operations consume resolved plans; this service never selects a common
      source type or conversion policy.
    attributes:
      builder:
        type: Callable[[], ir.IRBuilder]
    """

    builder: Callable[[], ir.IRBuilder]

    def __init__(self, builder: Callable[[], ir.IRBuilder]) -> None:
        """
        title: Use the current function builder without owning compiler state.
        parameters:
          builder:
            type: Callable[[], ir.IRBuilder]
        """
        self.builder = builder

    def is_numeric_value(self, value: ir.Value) -> bool:
        """
        title: Is numeric value.
        parameters:
          value:
            type: ir.Value
        returns:
          type: bool
        """
        if is_vector(value):
            elem_ty = value.type.element
            return isinstance(elem_ty, ir.IntType) or is_fp_type(elem_ty)
        return isinstance(value.type, ir.IntType) or is_fp_type(value.type)

    def bool_value_from_numeric(
        self,
        value: ir.Value,
        source_type: astx.DataType | None,
        *,
        name: str,
    ) -> ir.Value:
        """
        title: Convert one numeric value to boolean truthiness.
        parameters:
          value:
            type: ir.Value
          source_type:
            type: astx.DataType | None
          name:
            type: str
        returns:
          type: ir.Value
        """
        if is_boolean_type(source_type):
            return value
        if is_float_type(source_type):
            zero = ir.Constant(value.type, 0.0)
            return self.emit_numeric_compare(
                "!=",
                value,
                zero,
                unsigned=False,
                name=name,
            )
        if is_integer_type(source_type):
            zero = ir.Constant(value.type, 0)
            return self.emit_numeric_compare(
                "!=",
                value,
                zero,
                unsigned=True,
                name=name,
            )
        raise TypeError(f"Unsupported boolean conversion from {source_type!r}")

    def emit_numeric_compare(
        self,
        op_code: str,
        lhs: ir.Value,
        rhs: ir.Value,
        *,
        unsigned: bool,
        name: str,
    ) -> ir.Value:
        """
        title: Emit one numeric compare using shared signedness policy.
        parameters:
          op_code:
            type: str
          lhs:
            type: ir.Value
          rhs:
            type: ir.Value
          unsigned:
            type: bool
          name:
            type: str
        returns:
          type: ir.Value
        """
        if is_fp_type(lhs.type):
            return self.builder().fcmp_ordered(op_code, lhs, rhs, name)
        if unsigned:
            return self.builder().icmp_unsigned(
                op_code,
                lhs,
                rhs,
                name,
            )
        return self.builder().icmp_signed(op_code, lhs, rhs, name)

    def float_bit_width(self, type_: ir.Type) -> int:
        """
        title: Float bit width.
        parameters:
          type_:
            type: ir.Type
        returns:
          type: int
        """
        if isinstance(type_, DoubleType):
            return FLOAT64_BITS
        if isinstance(type_, FloatType):
            return FLOAT32_BITS
        if isinstance(type_, HalfType):
            return FLOAT16_BITS
        if FP128Type is not None and isinstance(type_, FP128Type):
            return FLOAT128_BITS
        raise TypeError(f"Unknown floating-point type: {type_}")

    def cast_value_to_type(
        self,
        value: ir.Value,
        target_scalar_ty: ir.Type,
        unsigned: bool = False,
    ) -> ir.Value:
        """
        title: Cast value to type.
        parameters:
          value:
            type: ir.Value
          target_scalar_ty:
            type: ir.Type
          unsigned:
            type: bool
        returns:
          type: ir.Value
        """
        builder = self.builder()
        value_is_vec = is_vector(value)
        if value_is_vec:
            lanes = value.type.count
            current_scalar_ty = value.type.element
            target_ty = ir.VectorType(target_scalar_ty, lanes)
        else:
            lanes = None
            current_scalar_ty = value.type
            target_ty = target_scalar_ty

        if current_scalar_ty == target_scalar_ty and value.type == target_ty:
            return value

        current_is_float = is_fp_type(current_scalar_ty)
        target_is_float = is_fp_type(target_scalar_ty)

        if target_is_float:
            if current_is_float:
                current_bits = self.float_bit_width(current_scalar_ty)
                target_bits = self.float_bit_width(target_scalar_ty)
                if current_bits == target_bits:
                    if value.type != target_ty:
                        return builder.bitcast(value, target_ty)
                    return value
                if current_bits < target_bits:
                    return builder.fpext(value, target_ty, "fpext")
                return builder.fptrunc(value, target_ty, "fptrunc")
            if unsigned:
                return builder.uitofp(value, target_ty, "uitofp")
            return builder.sitofp(value, target_ty, "sitofp")

        if current_is_float:
            raise TypeError(
                "Cannot implicitly convert floating-point to integer"
            )

        current_width = getattr(current_scalar_ty, "width", 0)
        target_width = getattr(target_scalar_ty, "width", 0)
        if current_width == target_width:
            if value.type != target_ty:
                return builder.bitcast(value, target_ty)
            return value

        if current_width < target_width:
            if unsigned:
                return builder.zext(value, target_ty, "zext")
            return builder.sext(value, target_ty, "sext")

        return builder.trunc(value, target_ty, "trunc")
