"""
title: Arx LLVM-IR integration helpers.
"""

from __future__ import annotations

import os
import tempfile

from typing import Any, Callable

import astx
import xh

from irx.builders.llvmliteir import (
    LLVMLiteIR as BaseLLVMLiteIR,
)
from irx.builders.llvmliteir import (
    LLVMLiteIRVisitor,
)
from llvmlite import binding as llvm


class ArxLLVMLiteIRVisitor(LLVMLiteIRVisitor):
    """
    title: Arx-specific LLVM-IR visitor customizations.
    """

    ...


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

    def build(
        self, node: astx.AST, output_file: str, link: bool = True
    ) -> None:
        """
        title: >-
          Transpile the ASTx to LLVM-IR and build it to an executable file.
        parameters:
          node:
            type: astx.AST
          output_file:
            type: str
          link:
            type: bool
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

        if not link:
            with open(self.output_file, "wb") as file_handler:
                file_handler.write(result_object)
            return

        # fix xh typing
        clang: Callable[..., Any] = xh.clang
        clang(
            file_path_o,
            "-o",
            self.output_file,
        )
        os.chmod(self.output_file, 0o755)
