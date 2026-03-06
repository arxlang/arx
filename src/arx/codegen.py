"""
title: Arx LLVM-IR integration helpers.
"""

from __future__ import annotations

import os
import tempfile

from typing import Any, Callable, cast

import astx
import xh

from irx import system
from irx.builders.llvmliteir import (
    LLVMLiteIR as BaseLLVMLiteIR,
)
from irx.builders.llvmliteir import (
    LLVMLiteIRVisitor,
    is_fp_type,
    is_int_type,
)
from llvmlite import binding as llvm
from llvmlite import ir
from plum import dispatch


class ArxLLVMLiteIRVisitor(LLVMLiteIRVisitor):
    """
    title: Arx-specific LLVM-IR visitor customizations.
    """

    @dispatch
    def visit(self, node: astx.IfStmt) -> None:
        """
        title: Generate LLVM IR for statement-style if blocks.
        parameters:
          node:
            type: astx.IfStmt
        """
        self.visit(cast(Any, node.condition))
        cond_v = self.result_stack.pop() if self.result_stack else None
        if cond_v is None:
            raise Exception("codegen: Invalid condition expression.")

        if is_fp_type(cond_v.type):
            cmp_instruction = self._llvm.ir_builder.fcmp_ordered
            zero_val = ir.Constant(cond_v.type, 0.0)
        else:
            cmp_instruction = self._llvm.ir_builder.icmp_signed
            zero_val = ir.Constant(cond_v.type, 0)

        cond_v = cmp_instruction(
            "!=",
            cond_v,
            zero_val,
        )

        then_bb = self._llvm.ir_builder.function.append_basic_block(
            "bb_if_then"
        )
        else_bb = self._llvm.ir_builder.function.append_basic_block(
            "bb_if_else"
        )
        merge_bb = self._llvm.ir_builder.function.append_basic_block(
            "bb_if_end"
        )

        self._llvm.ir_builder.cbranch(cond_v, then_bb, else_bb)

        self._llvm.ir_builder.position_at_start(then_bb)
        self.visit(cast(Any, node.then))
        then_v = self.result_stack.pop() if self.result_stack else None
        then_block_end = self._llvm.ir_builder.block
        then_terminated = then_block_end.terminator is not None
        if not then_terminated:
            self._llvm.ir_builder.branch(merge_bb)
            then_block_end = self._llvm.ir_builder.block

        self._llvm.ir_builder.position_at_start(else_bb)
        else_v = None
        if node.else_ is not None:
            self.visit(cast(Any, node.else_))
            else_v = self.result_stack.pop() if self.result_stack else None
        else_block_end = self._llvm.ir_builder.block
        else_terminated = else_block_end.terminator is not None
        if not else_terminated:
            self._llvm.ir_builder.branch(merge_bb)
            else_block_end = self._llvm.ir_builder.block

        if then_terminated and else_terminated:
            self._llvm.ir_builder.position_at_start(merge_bb)
            self._llvm.ir_builder.unreachable()
            return

        self._llvm.ir_builder.position_at_start(merge_bb)

        if (
            then_v is not None
            and else_v is not None
            and then_v.type == else_v.type
            and not then_terminated
            and not else_terminated
        ):
            phi = self._llvm.ir_builder.phi(then_v.type, "iftmp")
            phi.add_incoming(then_v, then_block_end)
            phi.add_incoming(else_v, else_block_end)
            self.result_stack.append(phi)

    @dispatch  # type: ignore[no-redef]
    def visit(self, node: system.PrintExpr) -> None:
        """
        title: Generate LLVM IR for PrintExpr with numeric support.
        parameters:
          node:
            type: system.PrintExpr
        """
        self.visit(cast(Any, node.message))
        value = self.result_stack.pop() if self.result_stack else None
        if value is None:
            raise Exception("Invalid message in PrintExpr")

        if isinstance(value.type, ir.PointerType) and (
            value.type.pointee == self._llvm.INT8_TYPE
        ):
            ptr = value
        elif is_int_type(value.type):
            arg, fmt_str = self._normalize_int_for_printf(value)
            fmt_gv = self._get_or_create_format_global(fmt_str)
            ptr = self._snprintf_heap(fmt_gv, [arg])
        elif isinstance(
            value.type, (ir.FloatType, ir.DoubleType, ir.HalfType)
        ):
            if isinstance(value.type, (ir.FloatType, ir.HalfType)):
                value_prom = self._llvm.ir_builder.fpext(
                    value, self._llvm.DOUBLE_TYPE, "to_double"
                )
            else:
                value_prom = value
            fmt_gv = self._get_or_create_format_global("%.6f")
            ptr = self._snprintf_heap(fmt_gv, [value_prom])
        else:
            raise Exception(
                f"Unsupported print argument type: '{value.type}'."
            )

        puts_fn = self._llvm.module.globals.get("puts")
        if puts_fn is None:
            puts_ty = ir.FunctionType(
                self._llvm.INT32_TYPE,
                [ir.PointerType(self._llvm.INT8_TYPE)],
            )
            puts_fn = ir.Function(self._llvm.module, puts_ty, name="puts")

        self._llvm.ir_builder.call(cast(ir.Function, puts_fn), [ptr])
        self.result_stack.append(ir.Constant(self._llvm.INT32_TYPE, 0))


class LLVMLiteIR(BaseLLVMLiteIR):
    """
    title: LLVM-IR transpiler and compiler with Arx overrides.
    attributes:
      translator:
        type: ArxLLVMLiteIRVisitor
    """

    def __init__(self) -> None:
        """
        title: Initialize LLVMIR.
        """
        super().__init__()
        self.translator: ArxLLVMLiteIRVisitor = ArxLLVMLiteIRVisitor()

    def build(self, node: astx.AST, output_file: str) -> None:
        """
        title: >-
          Transpile the ASTx to LLVM-IR and build it to an executable file.
        parameters:
          node:
            type: astx.AST
          output_file:
            type: str
        """
        self.translator = ArxLLVMLiteIRVisitor()
        result = self.translator.translate(node)

        result_mod = llvm.parse_assembly(result)
        result_object = self.translator.target_machine.emit_object(result_mod)

        with tempfile.NamedTemporaryFile(suffix="", delete=True) as temp_file:
            self.tmp_path = temp_file.name

        file_path_o = f"{self.tmp_path}.o"
        with open(file_path_o, "wb") as file_handler:
            file_handler.write(result_object)

        self.output_file = output_file

        # fix xh typing
        clang: Callable[..., Any] = xh.clang
        clang(
            file_path_o,
            "-o",
            self.output_file,
        )
        os.chmod(self.output_file, 0o755)
