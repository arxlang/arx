# mypy: disable-error-code=no-redef

"""
title: Unary-operator visitor mixins for llvmliteir.
"""

from typing import cast

import astx

from llvmlite import ir

from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import is_float_type, is_integer_type
from irx.builder.core import VisitorCore, semantic_assignment_key
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.lowering.nullable_operators import lower_nullable_operator
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.types import is_fp_type, is_int_type
from irx.typecheck import typechecked


@typechecked
class UnaryOpVisitorMixin(VisitorMixinBase):
    def lower_numeric_prefix(self, node: astx.UnaryOp) -> None:
        """
        title: Lower resolved scalar identity and wrapping or IEEE negation.
        parameters:
          node:
            type: astx.UnaryOp
        """
        semantic = getattr(node, "semantic", None)
        if (
            not isinstance(semantic, SemanticInfo)
            or semantic.resolved_operator is None
        ):
            raise_lowering_internal_error(
                "numeric prefix has no resolved operator", node=node
            )
        resolved = semantic.resolved_operator
        if resolved.op_code not in {"+", "-"} or not (
            is_integer_type(resolved.lhs_type)
            or is_float_type(resolved.lhs_type)
        ):
            raise_lowering_internal_error(
                "numeric prefix has incompatible resolved metadata", node=node
            )
        self.visit_child(node.operand)
        value = safe_pop(self.result_stack)
        if value is None:
            raise_lowering_internal_error(
                "numeric prefix operand produced no value", node=node
            )
        if resolved.op_code == "-":
            # fneg preserves IEEE signed-zero and NaN behavior; subtraction
            # from positive zero is not equivalent. Integer neg has no nsw/nuw
            # promise and follows the existing modular integer arithmetic.
            builder = self._llvm.ir_builder
            value = (
                builder.fneg(value, "negate")
                if is_float_type(resolved.lhs_type)
                else builder.neg(value, "negate")
            )
        self.result_stack.append(value)

    @VisitorCore.visit.dispatch  # type: ignore[attr-defined,untyped-decorator]
    def visit(self, node: astx.UnaryOp) -> None:
        """
        title: Visit UnaryOp nodes.
        parameters:
          node:
            type: astx.UnaryOp
        """
        if lower_nullable_operator(cast(VisitorCore, self), node):
            return
        if node.op_code in {"+", "-"}:
            self.lower_numeric_prefix(node)
            return
        if node.op_code == "++":
            self.visit_child(node.operand)
            operand_val = safe_pop(self.result_stack)
            if operand_val is None:
                raise Exception("codegen: Invalid unary operand.")
            operand_name = (
                node.operand.name
                if isinstance(node.operand, astx.Identifier)
                else getattr(node.operand, "field_name", "field")
            )
            operand_key = semantic_assignment_key(node, operand_name)

            one = ir.Constant(operand_val.type, 1)
            if is_fp_type(operand_val.type):
                result = self._llvm.ir_builder.fadd(operand_val, one, "inctmp")
            else:
                result = self._llvm.ir_builder.add(operand_val, one, "inctmp")

            if (
                isinstance(node.operand, astx.Identifier)
                and operand_key in self.const_vars
            ):
                raise Exception(
                    f"Cannot mutate '{operand_name}': declared as constant"
                )
            target_addr = self._lvalue_address(node.operand)
            self._llvm.ir_builder.store(result, target_addr)

            self.result_stack.append(result)
            return

        if node.op_code == "--":
            self.visit_child(node.operand)
            operand_val = safe_pop(self.result_stack)
            if operand_val is None:
                raise Exception("codegen: Invalid unary operand.")
            operand_name = (
                node.operand.name
                if isinstance(node.operand, astx.Identifier)
                else getattr(node.operand, "field_name", "field")
            )
            operand_key = semantic_assignment_key(node, operand_name)
            one = ir.Constant(operand_val.type, 1)
            if is_fp_type(operand_val.type):
                result = self._llvm.ir_builder.fsub(operand_val, one, "dectmp")
            else:
                result = self._llvm.ir_builder.sub(operand_val, one, "dectmp")

            if (
                isinstance(node.operand, astx.Identifier)
                and operand_key in self.const_vars
            ):
                raise Exception(
                    f"Cannot mutate '{operand_name}': declared as constant"
                )
            target_addr = self._lvalue_address(node.operand)
            self._llvm.ir_builder.store(result, target_addr)

            self.result_stack.append(result)
            return

        if node.op_code == "!":
            self.visit_child(node.operand)
            val = safe_pop(self.result_stack)
            if val is None:
                raise Exception("codegen: Invalid unary operand.")
            if not is_int_type(val.type) or val.type.width != 1:
                raise Exception(
                    "codegen: unary operator '!' must lower a Boolean operand."
                )

            result = self._llvm.ir_builder.xor(
                val,
                ir.Constant(self._llvm.BOOLEAN_TYPE, 1),
                "nottmp",
            )

            self.result_stack.append(result)
            return

        raise Exception(f"Unary operator {node.op_code} not implemented yet.")
