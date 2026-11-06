# mypy: disable-error-code=no-redef

"""
title: Unary-operator lowering implementations for llvmliteir.
"""

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_lowered_value,
)
from irx.builder.lowering.contracts import UnaryServices
from irx.builder.runtime import safe_pop
from irx.builder.types import is_fp_type, is_int_type
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class UnaryLowering:
    """
    title: Lower unary operations to LLVM.
    attributes:
      services:
        type: UnaryServices
    """

    services: UnaryServices

    def __init__(self, services: UnaryServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: UnaryServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Fail closed for nodes not exported by this feature family.
        parameters:
          node:
            type: astx.AST
        """
        raise_lowering_internal_error(
            f"no unary_ops handler for {type(node).__name__}", node=node
        )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: >-
          Export explicit concrete signatures without mutating a shared
          dispatcher.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return (
            contribute_node(
                "llvm.unary_ops.UnaryOp",
                "irx.unary_ops",
                "lowering",
                astx.UnaryOp,
                self.visit,
                source="irx.builder.lowering.unary_ops.UnaryLowering.visit",
            ),
        )

    @dispatch
    def visit(self, node: astx.UnaryOp) -> None:
        """
        title: Visit UnaryOp nodes.
        parameters:
          node:
            type: astx.UnaryOp
        """
        if self.services.lower_column_operation(node):
            return
        if node.op_code in {"+", "-"}:
            self.services.visit_child(node.operand)
            value = require_lowered_value(
                safe_pop(self.services.function_state.result_stack),
                node=node.operand,
                context="unary sign",
            )
            if node.op_code == "-":
                value = (
                    self.services.llvm.ir_builder.fneg(value)
                    if is_fp_type(value.type)
                    else self.services.numeric.resolved_integer_operation(
                        node, ir.Constant(value.type, 0), value, "-"
                    )
                )
            self.services.function_state.result_stack.append(value)
            return
        if node.op_code in {"++", "--"}:
            target_addr = self.services.layout.lvalue_address(node.operand)
            operand_val = self.services.llvm.ir_builder.load(target_addr)
            one = ir.Constant(operand_val.type, 1)
            if is_fp_type(operand_val.type):
                result = (
                    self.services.llvm.ir_builder.fadd
                    if node.op_code == "++"
                    else self.services.llvm.ir_builder.fsub
                )(operand_val, one)
            else:
                result = self.services.numeric.resolved_integer_operation(
                    node,
                    operand_val,
                    one,
                    "+" if node.op_code == "++" else "-",
                )
            self.services.llvm.ir_builder.store(result, target_addr)
            self.services.function_state.result_stack.append(result)
            return

        if node.op_code == "!":
            self.services.visit_child(node.operand)
            val = safe_pop(self.services.function_state.result_stack)
            if val is None:
                raise_lowering_internal_error(
                    "codegen: Invalid unary operand.", node=node
                )
            if not is_int_type(val.type) or val.type.width != 1:
                raise_lowering_internal_error(
                    (
                        "codegen: unary operator '!' must lower a "
                        "Boolean operand."
                    ),
                    node=node,
                )

            result = self.services.llvm.ir_builder.xor(
                val,
                ir.Constant(self.services.llvm.BOOLEAN_TYPE, 1),
                "nottmp",
            )

            self.services.function_state.result_stack.append(result)
            return

        raise_lowering_error(
            f"Unary operator {node.op_code} not implemented yet.",
            code=DiagnosticCodes.LOWERING_MISSING_HANDLER,
            node=node,
        )
