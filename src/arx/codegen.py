"""
title: Arx LLVM-IR integration helpers.
"""

from __future__ import annotations

import os
import tempfile

from pathlib import Path
from typing import Literal

import astx

from irx.analysis.module_interfaces import ImportResolver, ParsedModule
from irx.builder import Builder as LLVMBuilder
from irx.builder import Visitor as LLVMVisitor
from irx.builder.runtime.linking import link_executable
from llvmlite import binding as llvm


class ArxVisitor(LLVMVisitor):
    """
    title: Arx-specific backend visitor customizations.
    """

    ...


class ArxBuilder(LLVMBuilder):
    """
    title: Arx backend builder with Arx overrides.
    attributes:
      translator:
        type: ArxVisitor
    """

    LINK_MODES = {"auto", "pie", "no-pie"}

    def __init__(self) -> None:
        """
        title: Initialize ArxBuilder.
        """
        super().__init__()
        self.translator: ArxVisitor = self._new_translator()

    def _new_translator(self) -> ArxVisitor:
        """
        title: Create the Arx visitor.
        returns:
          type: ArxVisitor
        """
        return ArxVisitor(
            active_runtime_features=set(self.runtime_feature_names)
        )

    def _build_from_ir_result(
        self,
        result: str,
        output_file: str,
        link: bool,
        link_mode: Literal["auto", "pie", "no-pie"],
    ) -> None:
        """
        title: Materialize LLVM IR into either an object file or executable.
        parameters:
          result:
            type: str
          output_file:
            type: str
          link:
            type: bool
          link_mode:
            type: Literal[auto, pie, no-pie]
        """
        result_mod = llvm.parse_assembly(result)
        result_object = self.translator.target_machine.emit_object(result_mod)

        self.output_file = output_file

        if not link:
            with open(self.output_file, "wb") as file_handler:
                file_handler.write(result_object)
            return

        if link_mode not in self.LINK_MODES:
            raise ValueError(
                "Invalid link mode. Expected one of: auto, pie, no-pie."
            )

        extra_linker_flags: tuple[str, ...] = ()
        if link_mode == "pie":
            extra_linker_flags = ("-pie",)
        elif link_mode == "no-pie":
            extra_linker_flags = ("-no-pie",)

        with tempfile.TemporaryDirectory() as temp_dir:
            self.tmp_path = temp_dir
            file_path_o = Path(temp_dir) / "arx_module.o"
            with open(file_path_o, "wb") as file_handler:
                file_handler.write(result_object)

            link_executable(
                primary_object=file_path_o,
                output_file=Path(self.output_file),
                artifacts=self.translator.runtime_features.native_artifacts(),
                linker_flags=(
                    *self.translator.runtime_features.linker_flags(),
                    *extra_linker_flags,
                ),
            )

        os.chmod(self.output_file, 0o755)

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
        result = self.translate(node)
        self._build_from_ir_result(result, output_file, link, link_mode)

    def build_modules(
        self,
        root: ParsedModule,
        resolver: ImportResolver,
        output_file: str,
        link: bool = True,
        link_mode: Literal["auto", "pie", "no-pie"] = "auto",
    ) -> None:
        """
        title: Build a reachable graph of parsed modules.
        parameters:
          root:
            type: ParsedModule
          resolver:
            type: ImportResolver
          output_file:
            type: str
          link:
            type: bool
          link_mode:
            type: Literal[auto, pie, no-pie]
        """
        result = self.translate_modules(root, resolver)
        self._build_from_ir_result(result, output_file, link, link_mode)
