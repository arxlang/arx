# mypy: disable-error-code=no-redef

"""
title: Binary-operator visitor mixins for llvmliteir.
"""

from __future__ import annotations

from typing import Any, cast

import astx

from astx.binary_op import (
    SPECIALIZED_BINARY_OP_EXTRA,
    AddBinOp,
    AssignmentBinOp,
    BitAndBinOp,
    BitOrBinOp,
    BitXorBinOp,
    DivBinOp,
    EqBinOp,
    GeBinOp,
    GtBinOp,
    LeBinOp,
    LogicalAndBinOp,
    LogicalOrBinOp,
    LtBinOp,
    ModBinOp,
    MulBinOp,
    NeBinOp,
    SubBinOp,
    specialize_binary_op,
)
from llvmlite import ir

from irx.analysis.types import common_numeric_type, is_string_type
from irx.builder.core import (
    VisitorCore,
    semantic_assignment_key,
    semantic_flag,
    semantic_fma_rhs,
    uses_unsigned_semantics,
)
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.errors import (
    RUNTIME_FAILURE_FEATURE_NAME,
    RUNTIME_FAILURE_SYMBOL_NAME,
)
from irx.builder.types import is_fp_type, is_int_type
from irx.builder.vector import emit_add, emit_int_div, is_vector
from irx.typecheck import typechecked


@typechecked
class BinaryOpVisitorMixin(VisitorMixinBase):
    def _resolved_binary_variant(self, node: astx.BinaryOp) -> astx.BinaryOp:
        """
        title: Resolved binary variant.
        parameters:
          node:
            type: astx.BinaryOp
        returns:
          type: astx.BinaryOp
        """
        semantic = getattr(node, "semantic", None)
        extras = getattr(semantic, "extras", None)
        if isinstance(extras, dict):
            specialized = extras.get(SPECIALIZED_BINARY_OP_EXTRA)
            if isinstance(specialized, astx.BinaryOp):
                return specialized
        return specialize_binary_op(node)

    def _load_binary_operands(
        self,
        node: astx.BinaryOp,
        *,
        unify_numeric: bool = True,
    ) -> tuple[ir.Value, ir.Value, bool]:
        """
        title: Load binary operands.
        parameters:
          node:
            type: astx.BinaryOp
          unify_numeric:
            type: bool
        returns:
          type: tuple[ir.Value, ir.Value, bool]
        """
        self.visit_child(node.lhs)
        llvm_lhs = safe_pop(self.result_stack)
        self.visit_child(node.rhs)
        llvm_rhs = safe_pop(self.result_stack)

        if llvm_lhs is None or llvm_rhs is None:
            raise Exception("codegen: Invalid lhs/rhs")

        unsigned = uses_unsigned_semantics(node)
        lhs_type = self._resolved_ast_type(node.lhs)
        rhs_type = self._resolved_ast_type(node.rhs)
        semantic_numeric_type = common_numeric_type(lhs_type, rhs_type)
        if (
            unify_numeric
            and self._is_numeric_value(llvm_lhs)
            and self._is_numeric_value(llvm_rhs)
        ):
            if semantic_numeric_type is not None:
                llvm_lhs, llvm_rhs = self._coerce_numeric_operands_for_types(
                    llvm_lhs,
                    llvm_rhs,
                    lhs_type=lhs_type,
                    rhs_type=rhs_type,
                )
            else:
                # This is a low-level fallback for raw LLVM helper use only.
                llvm_lhs, llvm_rhs = self._unify_numeric_operands(
                    llvm_lhs,
                    llvm_rhs,
                    unsigned=unsigned,
                )

        return llvm_lhs, llvm_rhs, unsigned

    def _emit_vector_add(
        self,
        node: AddBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
    ) -> ir.Value | None:
        """
        title: Emit vector add.
        parameters:
          node:
            type: AddBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        prev_fast_math = self._fast_math_enabled
        if is_float_vec and semantic_flag(node, "fast_math"):
            self.set_fast_math(True)
        try:
            if is_float_vec:
                result = self._llvm.ir_builder.fadd(
                    llvm_lhs, llvm_rhs, name="vfaddtmp"
                )
                self._apply_fast_math(result)
            else:
                result = self._llvm.ir_builder.add(
                    llvm_lhs, llvm_rhs, name="vaddtmp"
                )
        finally:
            self.set_fast_math(prev_fast_math)
        return result

    def _load_boolean_operands(
        self,
        node: astx.BinaryOp,
    ) -> tuple[ir.Value, ir.Value]:
        """
        title: Load Boolean operands for logical operators.
        parameters:
          node:
            type: astx.BinaryOp
        returns:
          type: tuple[ir.Value, ir.Value]
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if (
            not is_int_type(llvm_lhs.type)
            or llvm_lhs.type.width != 1
            or not is_int_type(llvm_rhs.type)
            or llvm_rhs.type.width != 1
        ):
            raise Exception(
                "codegen: logical operator "
                f"'{node.op_code}' must lower Boolean operands."
            )
        return llvm_lhs, llvm_rhs

    def _lower_short_circuit_boolean(
        self,
        node: astx.BinaryOp,
        *,
        short_circuit_value: bool,
        name: str,
    ) -> None:
        """
        title: Lower one left-to-right short-circuit Boolean expression.
        parameters:
          node:
            type: astx.BinaryOp
          short_circuit_value:
            type: bool
          name:
            type: str
        """
        self.visit_child(node.lhs)
        llvm_lhs = safe_pop(self.result_stack)
        if (
            llvm_lhs is None
            or not is_int_type(llvm_lhs.type)
            or llvm_lhs.type.width != 1
        ):
            raise_lowering_internal_error(
                "logical operator lhs must lower to Boolean i1",
                node=node.lhs,
            )

        lhs_block = self._llvm.ir_builder.block
        function = self._llvm.ir_builder.function
        rhs_block = function.append_basic_block(f"logical.{name}.rhs")
        merge_block = function.append_basic_block(f"logical.{name}.merge")
        if short_circuit_value:
            self._llvm.ir_builder.cbranch(
                llvm_lhs,
                merge_block,
                rhs_block,
            )
        else:
            self._llvm.ir_builder.cbranch(
                llvm_lhs,
                rhs_block,
                merge_block,
            )

        self._llvm.ir_builder.position_at_start(rhs_block)
        self.visit_child(node.rhs)
        llvm_rhs = safe_pop(self.result_stack)
        if (
            llvm_rhs is None
            or not is_int_type(llvm_rhs.type)
            or llvm_rhs.type.width != 1
        ):
            raise_lowering_internal_error(
                "logical operator rhs must lower to Boolean i1",
                node=node.rhs,
            )
        rhs_end_block = self._llvm.ir_builder.block
        if rhs_end_block.is_terminated:
            raise_lowering_internal_error(
                "logical operator rhs terminated its expression block",
                node=node.rhs,
            )
        self._llvm.ir_builder.branch(merge_block)

        self._llvm.ir_builder.position_at_start(merge_block)
        result = self._llvm.ir_builder.phi(
            self._llvm.BOOLEAN_TYPE,
            name=name,
        )
        result.add_incoming(
            ir.Constant(self._llvm.BOOLEAN_TYPE, short_circuit_value),
            lhs_block,
        )
        result.add_incoming(llvm_rhs, rhs_end_block)
        self.result_stack.append(result)

    def _guard_scalar_integer_divisor(
        self,
        node: astx.BinaryOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
        *,
        unsigned: bool,
    ) -> None:
        """
        title: Reject zero and unrepresentable signed integer division.
        parameters:
          node:
            type: astx.BinaryOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
          unsigned:
            type: bool
        """
        if not is_int_type(llvm_lhs.type) or not is_int_type(llvm_rhs.type):
            raise_lowering_internal_error(
                "integer division guard requires integer operands",
                node=node,
            )
        if llvm_lhs.type != llvm_rhs.type:
            raise_lowering_internal_error(
                "integer division guard requires unified operand types",
                node=node,
            )

        zero = ir.Constant(llvm_rhs.type, 0)
        invalid = self._llvm.ir_builder.icmp_unsigned(
            "==",
            llvm_rhs,
            zero,
            name="integer_divisor_is_zero",
        )
        if not unsigned:
            width = llvm_lhs.type.width
            minimum = ir.Constant(llvm_lhs.type, -(1 << (width - 1)))
            negative_one = ir.Constant(llvm_rhs.type, -1)
            minimum_lhs = self._llvm.ir_builder.icmp_signed(
                "==",
                llvm_lhs,
                minimum,
                name="integer_dividend_is_minimum",
            )
            negative_one_rhs = self._llvm.ir_builder.icmp_signed(
                "==",
                llvm_rhs,
                negative_one,
                name="integer_divisor_is_negative_one",
            )
            overflow = self._llvm.ir_builder.and_(
                minimum_lhs,
                negative_one_rhs,
                name="integer_division_overflows",
            )
            invalid = self._llvm.ir_builder.or_(
                invalid,
                overflow,
                name="integer_division_is_invalid",
            )

        function = self._llvm.ir_builder.function
        fail_block = function.append_basic_block("integer.division.fail")
        pass_block = function.append_basic_block("integer.division.pass")
        self._llvm.ir_builder.cbranch(invalid, fail_block, pass_block)

        self._llvm.ir_builder.position_at_start(fail_block)
        string_pointer = cast(Any, self)._constant_c_string_pointer
        code_ptr = string_pointer(
            "ARX-RUNTIME-ARITHMETIC-001",
            name_hint="arithmetic_failure_code",
        )
        source_ptr = string_pointer(
            cast(Any, self)._assert_source_name(node),
            name_hint="arithmetic_failure_source",
        )
        message_ptr = string_pointer(
            "integer division or remainder has a zero divisor or an "
            "unrepresentable signed result",
            name_hint="arithmetic_failure_message",
        )
        failure = self.require_runtime_symbol(
            RUNTIME_FAILURE_FEATURE_NAME,
            RUNTIME_FAILURE_SYMBOL_NAME,
        )
        self._llvm.ir_builder.call(
            failure,
            [
                code_ptr,
                source_ptr,
                ir.Constant(self._llvm.INT32_TYPE, node.loc.line),
                ir.Constant(self._llvm.INT32_TYPE, node.loc.col),
                message_ptr,
            ],
        )
        self._llvm.ir_builder.unreachable()
        self._llvm.ir_builder.position_at_start(pass_block)

    def _emit_vector_sub(
        self,
        node: SubBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
    ) -> ir.Value | None:
        """
        title: Emit vector sub.
        parameters:
          node:
            type: SubBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        prev_fast_math = self._fast_math_enabled
        if is_float_vec and semantic_flag(node, "fast_math"):
            self.set_fast_math(True)
        try:
            if is_float_vec:
                result = self._llvm.ir_builder.fsub(
                    llvm_lhs, llvm_rhs, name="vfsubtmp"
                )
                self._apply_fast_math(result)
            else:
                result = self._llvm.ir_builder.sub(
                    llvm_lhs, llvm_rhs, name="vsubtmp"
                )
        finally:
            self.set_fast_math(prev_fast_math)
        return result

    def _emit_vector_mul(
        self,
        node: MulBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
    ) -> ir.Value | None:
        """
        title: Emit vector mul.
        parameters:
          node:
            type: MulBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        set_fast = is_float_vec and semantic_flag(node, "fast_math")
        if semantic_flag(node, "fma") and is_float_vec:
            fma_rhs_node = semantic_fma_rhs(node)
            if fma_rhs_node is None:
                raise Exception("FMA requires a third operand (fma_rhs)")
            self.visit_child(fma_rhs_node)
            llvm_fma_rhs = safe_pop(self.result_stack)
            if llvm_fma_rhs is None:
                raise Exception("FMA requires a valid third operand")
            if llvm_fma_rhs.type != llvm_lhs.type:
                raise Exception(
                    f"FMA operand type mismatch: "
                    f"{llvm_lhs.type} vs {llvm_fma_rhs.type}"
                )
            prev_fast_math = self._fast_math_enabled
            if set_fast:
                self.set_fast_math(True)
            try:
                return self._emit_fma(llvm_lhs, llvm_rhs, llvm_fma_rhs)
            finally:
                self.set_fast_math(prev_fast_math)

        prev_fast_math = self._fast_math_enabled
        if set_fast:
            self.set_fast_math(True)
        try:
            if is_float_vec:
                result = self._llvm.ir_builder.fmul(
                    llvm_lhs, llvm_rhs, name="vfmultmp"
                )
                self._apply_fast_math(result)
            else:
                result = self._llvm.ir_builder.mul(
                    llvm_lhs, llvm_rhs, name="vmultmp"
                )
        finally:
            self.set_fast_math(prev_fast_math)
        return result

    def _emit_vector_div(
        self,
        node: DivBinOp,
        llvm_lhs: ir.Value,
        llvm_rhs: ir.Value,
        *,
        unsigned: bool,
    ) -> ir.Value | None:
        """
        title: Emit vector div.
        parameters:
          node:
            type: DivBinOp
          llvm_lhs:
            type: ir.Value
          llvm_rhs:
            type: ir.Value
          unsigned:
            type: bool
        returns:
          type: ir.Value | None
        """
        if not (is_vector(llvm_lhs) and is_vector(llvm_rhs)):
            return None

        is_float_vec = is_fp_type(llvm_lhs.type.element)
        prev_fast_math = self._fast_math_enabled
        if is_float_vec and semantic_flag(node, "fast_math"):
            self.set_fast_math(True)
        try:
            if is_float_vec:
                result = self._llvm.ir_builder.fdiv(
                    llvm_lhs, llvm_rhs, name="vfdivtmp"
                )
                self._apply_fast_math(result)
            else:
                result = emit_int_div(
                    self._llvm.ir_builder, llvm_lhs, llvm_rhs, unsigned
                )
        finally:
            self.set_fast_math(prev_fast_math)
        return result

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.BinaryOp) -> None:
        """
        title: Visit BinaryOp nodes.
        parameters:
          node:
            type: astx.BinaryOp
        """
        specialized = self._resolved_binary_variant(node)
        if specialized is node:
            raise Exception(f"Binary op {node.op_code} not implemented yet.")
        self.visit_child(specialized)

    @VisitorCore.visit.dispatch
    def visit(self, node: AssignmentBinOp) -> None:
        """
        title: Visit AssignmentBinOp nodes.
        parameters:
          node:
            type: AssignmentBinOp
        """
        var_lhs = node.lhs
        if not isinstance(
            var_lhs,
            (
                astx.Identifier,
                astx.FieldAccess,
                astx.BaseFieldAccess,
                astx.StaticFieldAccess,
            ),
        ):
            raise Exception("destination of '=' must be a variable or field")

        lhs_name = (
            var_lhs.name
            if isinstance(var_lhs, astx.Identifier)
            else getattr(var_lhs, "field_name", "field")
        )
        lhs_key = semantic_assignment_key(node, lhs_name)
        if isinstance(var_lhs, astx.Identifier) and lhs_key in self.const_vars:
            raise Exception(
                f"Cannot assign to '{lhs_name}': declared as constant"
            )

        self.visit_child(node.rhs)
        llvm_rhs = safe_pop(self.result_stack)
        if llvm_rhs is None:
            raise Exception("codegen: Invalid rhs expression.")
        llvm_rhs = self._cast_ast_value(
            llvm_rhs,
            source_type=self._resolved_ast_type(node.rhs),
            target_type=self._resolved_ast_type(node),
        )

        llvm_lhs = self._lvalue_address(var_lhs)
        if isinstance(self._resolved_ast_type(node), astx.ListType):
            if not isinstance(var_lhs, astx.Identifier):
                raise_lowering_internal_error(
                    "list field assignment reached lowering without an "
                    "object-field ownership contract",
                    node=node,
                )
            self._destroy_replaced_list(
                node,
                llvm_lhs,
                target_name=lhs_name,
            )
        elif is_string_type(self._resolved_ast_type(node)) and isinstance(
            var_lhs,
            astx.Identifier,
        ):
            self._destroy_replaced_string(
                node,
                llvm_lhs,
                target_name=lhs_name,
            )
        self._llvm.ir_builder.store(llvm_rhs, llvm_lhs)
        self.result_stack.append(llvm_rhs)

    @VisitorCore.visit.dispatch
    def visit(self, node: AddBinOp) -> None:
        """
        title: Visit AddBinOp nodes.
        parameters:
          node:
            type: AddBinOp
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(node)

        vector_result = self._emit_vector_add(node, llvm_lhs, llvm_rhs)
        if vector_result is not None:
            self.result_stack.append(vector_result)
            return

        if (
            isinstance(llvm_lhs.type, ir.PointerType)
            and isinstance(llvm_rhs.type, ir.PointerType)
            and llvm_lhs.type.pointee == self._llvm.INT8_TYPE
            and llvm_rhs.type.pointee == self._llvm.INT8_TYPE
        ):
            result = self._handle_string_concatenation(
                node,
                llvm_lhs,
                llvm_rhs,
            )
            self._register_owned_string_temporary(node, result)
        else:
            result = emit_add(
                self._llvm.ir_builder, llvm_lhs, llvm_rhs, "addtmp"
            )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: SubBinOp) -> None:
        """
        title: Visit SubBinOp nodes.
        parameters:
          node:
            type: SubBinOp
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(node)

        if self._try_set_binary_op(llvm_lhs, llvm_rhs, node.op_code):
            return

        vector_result = self._emit_vector_sub(node, llvm_lhs, llvm_rhs)
        if vector_result is not None:
            self.result_stack.append(vector_result)
            return

        if is_fp_type(llvm_lhs.type):
            result = self._llvm.ir_builder.fsub(llvm_lhs, llvm_rhs, "subtmp")
            self._apply_fast_math(result)
        else:
            result = self._llvm.ir_builder.sub(llvm_lhs, llvm_rhs, "subtmp")
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: MulBinOp) -> None:
        """
        title: Visit MulBinOp nodes.
        parameters:
          node:
            type: MulBinOp
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(node)

        vector_result = self._emit_vector_mul(node, llvm_lhs, llvm_rhs)
        if vector_result is not None:
            self.result_stack.append(vector_result)
            return

        if is_fp_type(llvm_lhs.type):
            result = self._llvm.ir_builder.fmul(llvm_lhs, llvm_rhs, "multmp")
            self._apply_fast_math(result)
        else:
            result = self._llvm.ir_builder.mul(llvm_lhs, llvm_rhs, "multmp")
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: DivBinOp) -> None:
        """
        title: Visit DivBinOp nodes.
        parameters:
          node:
            type: DivBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        vector_result = self._emit_vector_div(
            node,
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
        )
        if vector_result is not None:
            self.result_stack.append(vector_result)
            return

        if is_fp_type(llvm_lhs.type):
            result = self._llvm.ir_builder.fdiv(llvm_lhs, llvm_rhs, "divtmp")
            self._apply_fast_math(result)
        elif unsigned:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=True,
            )
            result = self._llvm.ir_builder.udiv(llvm_lhs, llvm_rhs, "divtmp")
        else:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=False,
            )
            result = self._llvm.ir_builder.sdiv(llvm_lhs, llvm_rhs, "divtmp")
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: ModBinOp) -> None:
        """
        title: Visit ModBinOp nodes.
        parameters:
          node:
            type: ModBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise Exception(f"Vector binop {node.op_code} not implemented.")

        if is_fp_type(llvm_lhs.type) or is_fp_type(llvm_rhs.type):
            result = self._llvm.ir_builder.frem(llvm_lhs, llvm_rhs, "fremtmp")
        elif unsigned:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=True,
            )
            result = self._llvm.ir_builder.urem(llvm_lhs, llvm_rhs, "uremtmp")
        else:
            self._guard_scalar_integer_divisor(
                node,
                llvm_lhs,
                llvm_rhs,
                unsigned=False,
            )
            result = self._llvm.ir_builder.srem(llvm_lhs, llvm_rhs, "sremtmp")
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: LogicalAndBinOp) -> None:
        """
        title: Visit LogicalAndBinOp nodes.
        parameters:
          node:
            type: LogicalAndBinOp
        """
        self._lower_short_circuit_boolean(
            node,
            short_circuit_value=False,
            name="andtmp",
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: LogicalOrBinOp) -> None:
        """
        title: Visit LogicalOrBinOp nodes.
        parameters:
          node:
            type: LogicalOrBinOp
        """
        self._lower_short_circuit_boolean(
            node,
            short_circuit_value=True,
            name="ortmp",
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: LtBinOp) -> None:
        """
        title: Visit LtBinOp nodes.
        parameters:
          node:
            type: LtBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise Exception(f"Vector binop {node.op_code} not implemented.")
        result = self._emit_numeric_compare(
            "<",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="lttmp",
        )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: GtBinOp) -> None:
        """
        title: Visit GtBinOp nodes.
        parameters:
          node:
            type: GtBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise Exception(f"Vector binop {node.op_code} not implemented.")
        result = self._emit_numeric_compare(
            ">",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="gttmp",
        )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: LeBinOp) -> None:
        """
        title: Visit LeBinOp nodes.
        parameters:
          node:
            type: LeBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise Exception(f"Vector binop {node.op_code} not implemented.")
        result = self._emit_numeric_compare(
            "<=",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="letmp",
        )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: GeBinOp) -> None:
        """
        title: Visit GeBinOp nodes.
        parameters:
          node:
            type: GeBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)
        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise Exception(f"Vector binop {node.op_code} not implemented.")
        result = self._emit_numeric_compare(
            ">=",
            llvm_lhs,
            llvm_rhs,
            unsigned=unsigned,
            name="getmp",
        )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: EqBinOp) -> None:
        """
        title: Visit EqBinOp nodes.
        parameters:
          node:
            type: EqBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise Exception(f"Vector binop {node.op_code} not implemented.")

        if (
            isinstance(llvm_lhs.type, ir.PointerType)
            and isinstance(llvm_rhs.type, ir.PointerType)
            and llvm_lhs.type.pointee == self._llvm.INT8_TYPE
            and llvm_rhs.type.pointee == self._llvm.INT8_TYPE
        ):
            result = self._handle_string_comparison(llvm_lhs, llvm_rhs, "==")
        else:
            result = self._emit_numeric_compare(
                "==",
                llvm_lhs,
                llvm_rhs,
                unsigned=unsigned,
                name="eqtmp",
            )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: NeBinOp) -> None:
        """
        title: Visit NeBinOp nodes.
        parameters:
          node:
            type: NeBinOp
        """
        llvm_lhs, llvm_rhs, unsigned = self._load_binary_operands(node)

        if is_vector(llvm_lhs) and is_vector(llvm_rhs):
            raise Exception(f"Vector binop {node.op_code} not implemented.")

        if (
            isinstance(llvm_lhs.type, ir.PointerType)
            and isinstance(llvm_rhs.type, ir.PointerType)
            and llvm_lhs.type.pointee == self._llvm.INT8_TYPE
            and llvm_rhs.type.pointee == self._llvm.INT8_TYPE
        ):
            result = self._handle_string_comparison(llvm_lhs, llvm_rhs, "!=")
        else:
            result = self._emit_numeric_compare(
                "!=",
                llvm_lhs,
                llvm_rhs,
                unsigned=unsigned,
                name="netmp",
            )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: BitOrBinOp) -> None:
        """
        title: Visit BitOrBinOp nodes.
        parameters:
          node:
            type: BitOrBinOp
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if self._try_set_binary_op(llvm_lhs, llvm_rhs, node.op_code):
            return
        raise Exception(f"Binary op {node.op_code} not implemented yet.")

    @VisitorCore.visit.dispatch
    def visit(self, node: BitAndBinOp) -> None:
        """
        title: Visit BitAndBinOp nodes.
        parameters:
          node:
            type: BitAndBinOp
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if self._try_set_binary_op(llvm_lhs, llvm_rhs, node.op_code):
            return
        raise Exception(f"Binary op {node.op_code} not implemented yet.")

    @VisitorCore.visit.dispatch
    def visit(self, node: BitXorBinOp) -> None:
        """
        title: Visit BitXorBinOp nodes.
        parameters:
          node:
            type: BitXorBinOp
        """
        llvm_lhs, llvm_rhs, _unsigned = self._load_binary_operands(
            node,
            unify_numeric=False,
        )
        if self._try_set_binary_op(llvm_lhs, llvm_rhs, node.op_code):
            return
        raise Exception(f"Binary op {node.op_code} not implemented yet.")
