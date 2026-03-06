"""
title: Arx main module.
"""

import os
import subprocess

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import astx

from irx.builders.llvmliteir import LLVMLiteIR

from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


def get_module_name_from_file_path(filepath: str) -> str:
    """
    title: Return the module name from the source file name.
    parameters:
      filepath:
        type: str
    returns:
      type: str
    """
    return filepath.rsplit(os.sep, maxsplit=1)[-1].replace(".x", "")


@dataclass
class ArxMain:
    """
    title: The main class for calling Arx compiler.
    attributes:
      input_files:
        type: list[str]
      output_file:
        type: str
      is_lib:
        type: bool
    """

    input_files: list[str] = field(default_factory=list)
    output_file: str = ""
    is_lib: bool = False

    def _resolve_output_file(self) -> str:
        """
        title: Resolve the final compiler output path.
        returns:
          type: str
        """
        if self.output_file:
            return self.output_file
        if not self.input_files:
            return "a.out"
        return Path(self.input_files[0]).stem or "a.out"

    def _get_astx(self) -> astx.Block:
        lexer = Lexer()
        parser = Parser()
        tree_ast = astx.Block()

        for input_file in self.input_files:
            ArxIO.file_to_buffer(input_file)
            module_name = get_module_name_from_file_path(input_file)
            module_ast = parser.parse(lexer.lex(), module_name)
            tree_ast.nodes.append(module_ast)

        return tree_ast

    def run(self, **kwargs: Any) -> None:
        """
        title: Compile the given source code.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        """
        self.input_files = kwargs.get("input_files", [])
        output_file = kwargs.get("output_file")
        self.output_file = output_file.strip() if output_file else ""
        # is_lib now is the only available option
        self.is_lib = kwargs.get("is_lib", True) or True

        if kwargs.get("show_ast"):
            return self.show_ast()

        if kwargs.get("show_tokens"):
            return self.show_tokens()

        if kwargs.get("show_llvm_ir"):
            return self.show_llvm_ir()

        if kwargs.get("shell"):
            return self.run_shell()

        self.compile()
        if kwargs.get("run"):
            self.run_binary()

    def show_ast(self) -> None:
        """
        title: Print the AST for the given input file.
        """
        tree_ast = self._get_astx()
        try:
            print(repr(tree_ast))
        except Exception:
            # Fallback for nodes whose repr visualizer path is not supported.
            print(str(tree_ast))

    def show_tokens(self) -> None:
        """
        title: Print the AST for the given input file.
        """
        lexer = Lexer()

        for input_file in self.input_files:
            ArxIO.file_to_buffer(input_file)
            tokens = lexer.lex()
            for token in tokens:
                print(token)

    def show_llvm_ir(self) -> None:
        """
        title: Compile into LLVM IR the given input file.
        """
        tree_ast = self._get_astx()
        ir = LLVMLiteIR()
        print(ir.translator.translate(tree_ast))

    def run_shell(self) -> None:
        """
        title: Open arx in shell mode.
        """
        raise Exception("Arx Shell is not implemented yet.")

    def run_binary(self) -> None:
        """
        title: Run the generated binary.
        """
        binary_path = Path(self.output_file)
        if not binary_path.is_absolute():
            binary_path = Path.cwd() / binary_path
        result = subprocess.run([str(binary_path)], check=False)
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    def compile(self, show_llvm_ir: bool = False) -> None:
        """
        title: Compile the given input file.
        parameters:
          show_llvm_ir:
            type: bool
        """
        tree_ast = self._get_astx()
        ir = LLVMLiteIR()
        self.output_file = self._resolve_output_file()
        ir.build(tree_ast, output_file=self.output_file)
