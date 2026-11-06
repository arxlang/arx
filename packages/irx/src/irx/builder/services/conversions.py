"""
title: Checked numeric emission consuming analysis-owned conversion records.
summary: >-
  Guards precede unsafe conversions, mutation, and result publication. LLVM
  overflow intrinsics do not rely on undefined signed-overflow flags. Runtime
  failures use registered activation and the injected checked-control boundary.
"""

from collections.abc import Callable
from math import isfinite, isnan
from typing import Protocol, runtime_checkable

import astx

from llvmlite import ir
from public import private

from irx.analysis.float_literals import rounded_float
from irx.analysis.numeric_policy import (
    NumericConversion,
    NumericConversionKind,
    integer_bounds,
)
from irx.analysis.resolved_nodes import ResolvedOperator
from irx.analysis.types import (
    bit_width,
    is_boolean_type,
    is_float_type,
    is_integer_type,
    is_unsigned_type,
)
from irx.builder.diagnostics import require_semantic_metadata
from irx.builder.services.raw_numeric import RawNumericEmission
from irx.builder.services.representations import (
    TypeLowering,
    resolved_type,
    semantic_info,
)
from irx.typecheck import typechecked


@private
@runtime_checkable
class RuntimeCondition(Protocol):
    """
    title: The single control-transfer dependency of checked numeric emission.
    """

    def __call__(
        self,
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: Continue on success or emit the compiler's checked failure path.
        parameters:
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        del node, condition, code, message, block_name, exception_role
        raise NotImplementedError


@private
@typechecked
class NumericEmission(RawNumericEmission):
    """
    title: >-
      Numeric emission consuming analysis-selected types and conversion plans.
    summary: >-
      The active builder belongs to its function; module references belong to
      this compilation. Runtime guard and activation callbacks are the only
      control-transfer/runtime dependencies. No symbol lookup or promotion is
      performed here.
    attributes:
      module:
        type: ir.Module
      types:
        type: TypeLowering
      guard:
        type: RuntimeCondition
      activate:
        type: Callable[[str], None]
    """

    module: ir.Module
    types: TypeLowering
    guard: RuntimeCondition
    activate: Callable[[str], None]

    def __init__(
        self,
        module: ir.Module,
        builder: Callable[[], ir.IRBuilder],
        types: TypeLowering,
        guard: RuntimeCondition,
        activate: Callable[[str], None],
    ) -> None:
        """
        title: Bind explicit representation and checked-control dependencies.
        parameters:
          module:
            type: ir.Module
          builder:
            type: Callable[[], ir.IRBuilder]
          types:
            type: TypeLowering
          guard:
            type: RuntimeCondition
          activate:
            type: Callable[[str], None]
        """
        super().__init__(builder)
        self.module = module
        self.types = types
        self.guard = guard
        self.activate = activate

    def cast_scalar(
        self,
        value: ir.Value,
        *,
        source_type: astx.DataType | None,
        target_type: astx.DataType | None,
    ) -> ir.Value:
        """
        title: Cast one lowered value using semantic scalar types.
        parameters:
          value:
            type: ir.Value
          source_type:
            type: astx.DataType | None
          target_type:
            type: astx.DataType | None
        returns:
          type: ir.Value
        """
        if source_type is None or target_type is None:
            return value

        if isinstance(target_type, astx.NullableType):
            valid: ir.Value = ir.Constant(ir.IntType(1), 1)
            if isinstance(source_type, astx.NullableType):
                valid = self.builder().extract_value(value, 0)
                value = self.builder().extract_value(value, 1)
                source_type = source_type.value_type
            value = self.cast_scalar(
                value,
                source_type=source_type,
                target_type=target_type.value_type,
            )
            llvm_type = self.types.llvm_type(target_type)
            if llvm_type is None:
                raise TypeError("missing nullable storage type")
            result = self.builder().insert_value(
                ir.Constant(llvm_type, None), valid, 0
            )
            return self.builder().insert_value(result, value, 1)
        if isinstance(source_type, astx.UnionType):
            source_type = self.types.union_storage_ast_type(source_type)
        if isinstance(target_type, astx.UnionType):
            target_type = self.types.union_storage_ast_type(target_type)
        if source_type is None or target_type is None:
            return value

        target_llvm_type = self.types.llvm_type(target_type)
        if target_llvm_type is None:
            return value
        if value.type == target_llvm_type:
            return value

        builder = self.builder()

        if is_boolean_type(target_type):
            return self.bool_value_from_numeric(
                value,
                source_type,
                name="boolcast",
            )

        if is_boolean_type(source_type):
            if is_integer_type(target_type):
                return builder.zext(value, target_llvm_type, "bool_zext")
            if is_float_type(target_type):
                return builder.uitofp(value, target_llvm_type, "bool_to_fp")

        if is_integer_type(source_type) and is_integer_type(target_type):
            source_width = bit_width(source_type)
            target_width = bit_width(target_type)

            if source_width == target_width:
                return value
            if source_width < target_width:
                if is_unsigned_type(source_type):
                    return builder.zext(value, target_llvm_type, "zext")
                return builder.sext(value, target_llvm_type, "sext")
            return builder.trunc(value, target_llvm_type, "trunc")

        if is_integer_type(source_type) and is_float_type(target_type):
            if is_unsigned_type(source_type):
                return builder.uitofp(value, target_llvm_type, "uitofp")
            return builder.sitofp(value, target_llvm_type, "sitofp")

        if is_float_type(source_type) and is_integer_type(target_type):
            if is_unsigned_type(target_type):
                return builder.fptoui(value, target_llvm_type, "fptoui")
            return builder.fptosi(value, target_llvm_type, "fptosi")

        if is_float_type(source_type) and is_float_type(target_type):
            if bit_width(source_type) < bit_width(target_type):
                return builder.fpext(value, target_llvm_type, "fpext")
            return builder.fptrunc(value, target_llvm_type, "fptrunc")

        if isinstance(source_type, astx.ClassType) and isinstance(
            target_type,
            astx.ClassType,
        ):
            return builder.bitcast(value, target_llvm_type, "classcast")

        raise TypeError(
            f"Unsupported scalar cast from {source_type!r} to {target_type!r}"
        )

    def aggregate_scalar(
        self,
        value: ir.Value,
        *,
        source_type: astx.DataType | None,
        target_type: astx.DataType | None,
    ) -> ir.Value:
        """
        title: Preserve constant aggregate storage under resolved conversions.
        summary: >-
          Aggregate literals and dictionary keys need constant representations
          when possible. Ordinary scalar lowering retains explicit SSA casts;
          this path never selects a promotion or changes conversion validity.
          Nonconstant values use the same resolved scalar emission.
        parameters:
          value:
            type: ir.Value
          source_type:
            type: astx.DataType | None
          target_type:
            type: astx.DataType | None
        returns:
          type: ir.Value
        """
        if (
            isinstance(value, ir.Constant)
            and source_type is not None
            and target_type is not None
        ):
            target = self.types.llvm_type(target_type)
            if target is not None:
                constant = self.cast_constant_scalar(
                    value, source_type, target_type, target
                )
                if constant is not None:
                    return constant
        return self.cast_scalar(
            value, source_type=source_type, target_type=target_type
        )

    def cast_constant_scalar(
        self,
        value: ir.Constant,
        source_type: astx.DataType,
        target_type: astx.DataType,
        target_llvm_type: ir.Type,
    ) -> ir.Constant | None:
        """
        title: Preserve scalar constants under explicitly selected conversions.
        summary: >-
          Signedness comes from the semantic source type, not the LLVM integer
          representation. This emits no promotion or conversion-policy
          decision; checked range guards remain the responsibility of
          numeric_cast.
        parameters:
          value:
            type: ir.Constant
          source_type:
            type: astx.DataType
          target_type:
            type: astx.DataType
          target_llvm_type:
            type: ir.Type
        returns:
          type: ir.Constant | None
        """
        raw = value.constant
        if not isinstance(raw, (int, float)):
            return None
        number: int | float
        if is_boolean_type(source_type):
            number = int(bool(raw))
        elif is_integer_type(source_type) and isinstance(raw, int):
            width = bit_width(source_type)
            number = raw & ((1 << width) - 1)
            if not is_unsigned_type(source_type) and number >= 1 << (
                width - 1
            ):
                number -= 1 << width
        elif is_float_type(source_type):
            number = rounded_float(raw, source_type)
        else:
            return None

        if is_boolean_type(target_type):
            # Match the ordered comparison used by bool_value_from_numeric.
            return ir.Constant(
                target_llvm_type, int(not isnan(number) and number != 0)
            )
        if is_float_type(target_type):
            return ir.Constant(
                target_llvm_type, rounded_float(number, target_type)
            )
        if not is_integer_type(target_type):
            return None
        if isinstance(number, float):
            if not isfinite(number):
                return None
            number = int(number)
            bounds = integer_bounds(target_type)
            if bounds is None or not bounds[0] <= number <= bounds[1]:
                return None
        width = bit_width(target_type)
        number &= (1 << width) - 1
        if not is_unsigned_type(target_type) and number >= 1 << (width - 1):
            number -= 1 << width
        return ir.Constant(target_llvm_type, number)

    def guard_numeric(
        self, node: astx.AST, valid: ir.Value, *, conversion: bool
    ) -> None:
        """
        title: Deliver a deterministic arithmetic or conversion failure.
        parameters:
          node:
            type: astx.AST
          valid:
            type: ir.Value
          conversion:
            type: bool
        """
        self.guard(
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

    def integer_operation(
        self,
        node: astx.AST,
        lhs: ir.Value,
        rhs: ir.Value,
        plan: ResolvedOperator,
        operator: str,
    ) -> ir.Value:
        """
        title: >-
          Emit checked or explicitly wrapping integer arithmetic, including
          SIMD.
        parameters:
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
        builder = self.builder()
        name = {"+": "add", "-": "sub", "*": "mul"}[operator]
        if plan.mode is astx.NumericMode.WRAPPING:
            return getattr(builder, name)(lhs, rhs, name + "tmp")
        scalar = (
            lhs.type.element
            if isinstance(lhs.type, ir.VectorType)
            else lhs.type
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
        intrinsic = self.module.globals.get(intrinsic_name)
        if intrinsic is None:
            intrinsic = ir.Function(
                self.module,
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
        self.guard_numeric(node, builder.not_(overflow), conversion=False)
        return result

    def resolved_integer_operation(
        self,
        node: astx.AST,
        lhs: ir.Value,
        rhs: ir.Value,
        operator: str,
    ) -> ir.Value:
        """
        title: >-
          Require an analyzed arithmetic plan before emitting a checked
          operation.
        parameters:
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
        semantic = semantic_info(node)
        plan = require_semantic_metadata(
            semantic.resolved_operator,
            node=node,
            metadata="resolved_operator",
            context="integer arithmetic",
        )
        return self.integer_operation(node, lhs, rhs, plan, operator)

    def finite_value(self, value: ir.Value) -> ir.Value:
        """
        title: >-
          Test finiteness without rejecting preexisting floating NaN or
          infinity.
        parameters:
          value:
            type: ir.Value
        returns:
          type: ir.Value
        """
        builder = self.builder()
        above = builder.fcmp_ordered(
            ">", value, ir.Constant(value.type, float("-inf"))
        )
        below = builder.fcmp_ordered(
            "<", value, ir.Constant(value.type, float("inf"))
        )
        return builder.and_(above, below)

    def numeric_cast(
        self,
        node: astx.Cast,
        value: ir.Value,
        plan: NumericConversion,
        mode: astx.NumericMode,
    ) -> ir.Value:
        """
        title: >-
          Convert a valid scalar payload using the analyzed conversion
          contract.
        parameters:
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
        builder = self.builder()
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
                self.guard_numeric(node, valid, conversion=True)
            elif plan.kind is NumericConversionKind.FLOAT_TO_INTEGER:
                bounds = integer_bounds(plan.target_type)
                assert bounds is not None
                double: ir.Value = value
                if not isinstance(value.type, ir.DoubleType):
                    double = builder.fpext(value, ir.DoubleType())
                # NaN is an invalid value, unlike infinity or a finite value
                # outside the target range: both are overflow failures.
                self.guard(
                    node,
                    builder.fcmp_ordered("==", double, double),
                    code="ARX-RUNTIME-CONVERSION-001",
                    message="cannot convert NaN to an integer",
                    block_name="numeric.conversion.nan",
                    exception_role="ValueError",
                )
                # LLVM may lower truncation to a libm call on baseline targets.
                self.activate("libm")
                trunc = self.module.declare_intrinsic(
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
                self.guard_numeric(node, valid, conversion=True)
                target = require_semantic_metadata(
                    self.types.llvm_type(plan.target_type),
                    node=node,
                    metadata="cast target",
                    context="numeric cast",
                )
                return (builder.fptoui if bounds[0] == 0 else builder.fptosi)(
                    truncated, target
                )
        result = self.cast_scalar(
            value, source_type=plan.source_type, target_type=plan.target_type
        )
        if mode is astx.NumericMode.CHECKED and plan.requires_range_check:
            if plan.kind is NumericConversionKind.INTEGER_TO_FLOAT:
                self.guard_numeric(
                    node, self.finite_value(result), conversion=True
                )
            elif plan.kind is NumericConversionKind.FLOAT_NARROW:
                valid = builder.or_(
                    builder.not_(self.finite_value(value)),
                    self.finite_value(result),
                )
                self.guard_numeric(node, valid, conversion=True)
        return result

    def lower_numeric_cast(
        self,
        node: astx.Cast,
        value: ir.Value,
        plan: NumericConversion,
        mode: astx.NumericMode,
    ) -> ir.Value:
        """
        title: Guard nullable conversion payloads only when the input is valid.
        parameters:
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
        source = resolved_type(node.value)
        target = resolved_type(node)
        if not isinstance(target, astx.NullableType):
            return self.numeric_cast(node, value, plan, mode)
        builder = self.builder()
        target_llvm = require_semantic_metadata(
            self.types.llvm_type(target),
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
        result = self.numeric_cast(node, value, plan, mode)
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

    def guard_collection_length(
        self, node: astx.AST, length: ir.Value
    ) -> None:
        """
        title: >-
          Keep i32 collection length, index, and count results representable.
        summary: >-
          The backing ABI uses i64 lengths; no narrowing may silently wrap.
        parameters:
          node:
            type: astx.AST
          length:
            type: ir.Value
        """
        builder = self.builder()
        valid = builder.icmp_unsigned(
            "<=", length, ir.Constant(length.type, (1 << 31) - 1)
        )
        self.guard_numeric(node, valid, conversion=True)
