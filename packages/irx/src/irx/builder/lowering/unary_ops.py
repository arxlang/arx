# mypy: disable-error-code=no-redef

"""
title: Unary-operator visitor mixins for llvmliteir.
"""

from typing import cast

import astx

from llvmlite import ir

from irx.builder.core import VisitorCore
from irx.builder.diagnostics import require_lowered_value
from irx.builder.lowering.nullable import NullableVisitorMixin
from irx.builder.numeric import resolved_integer_operation
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.types import is_fp_type, is_int_type
from irx.typecheck import typechecked


@typechecked
class UnaryOpVisitorMixin(VisitorMixinBase):
    """
    title: Lower unary operations to LLVM.
    """

    @VisitorCore.visit.dispatch  # type: ignore[attr-defined,untyped-decorator]
    def visit(self, node: astx.UnaryOp) -> None:
        """
        title: Visit UnaryOp nodes.
        parameters:
          node:
            type: astx.UnaryOp
        """
        if cast(NullableVisitorMixin, self).lower_column_operation(node):
            return
        if node.op_code in {"+", "-"}:
            self.visit_child(node.operand)
            value = require_lowered_value(
                safe_pop(self.result_stack),
                node=node.operand,
                context="unary sign",
            )
            if node.op_code == "-":
                value = (
                    self._llvm.ir_builder.fneg(value)
                    if is_fp_type(value.type)
                    else resolved_integer_operation(
                        cast(VisitorCore, self),
                        node,
                        ir.Constant(value.type, 0),
                        value,
                        "-",
                    )
                )
            self.result_stack.append(value)
            return
        if node.op_code in {"++", "--"}:
            target_addr = self._lvalue_address(node.operand)
            operand_val = self._llvm.ir_builder.load(target_addr)
            one = ir.Constant(operand_val.type, 1)
            if is_fp_type(operand_val.type):
                result = (
                    self._llvm.ir_builder.fadd
                    if node.op_code == "++"
                    else self._llvm.ir_builder.fsub
                )(operand_val, one)
            else:
                result = resolved_integer_operation(
                    cast(VisitorCore, self),
                    node,
                    operand_val,
                    one,
                    "+" if node.op_code == "++" else "-",
                )
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
