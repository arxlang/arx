"""
title: Arx LLVM-IR integration helpers.
"""

from __future__ import annotations

import os
import tempfile

from typing import Any, Callable, Literal

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

    LINK_MODES = {"auto", "pie", "no-pie"}

    def __init__(self) -> None:
        """
        title: Initialize LLVMIR.
        """
        super().__init__()
        self.translator: ArxLLVMLiteIRVisitor = ArxLLVMLiteIRVisitor()

    def build(
        self,
        node: astx.AST,
        output_file: str,
        link: bool = True,
        link_mode: Literal["auto", "pie", "no-pie"] = "auto",
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
          link_mode:
            type: Literal[auto, pie, no-pie]
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

        if link_mode not in self.LINK_MODES:
            raise ValueError(
                "Invalid link mode. Expected one of: auto, pie, no-pie."
            )

        # fix xh typing
        clang: Callable[..., Any] = xh.clang
        clang_args = [file_path_o]
        if link_mode == "pie":
            clang_args.append("-pie")
        elif link_mode == "no-pie":
            clang_args.append("-no-pie")
        clang_args.extend(["-o", self.output_file])
        clang(*clang_args)
        os.chmod(self.output_file, 0o755)
