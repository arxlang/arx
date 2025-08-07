"""Arx main module."""

import os

from dataclasses import dataclass, field
from typing import Any

import astx

from irx.builders.llvmliteir import LLVMLiteIR

from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


def get_module_name_from_file_path(filepath: str) -> str:
    """Return the module name from the source file name."""
    return filepath.split(os.sep)[-1].replace(".arx", "")


@dataclass
class ArxMain:
    """The main class for calling Arx compiler."""

    input_files: list[str] = field(default_factory=list)
    output_file: str = ""
    is_lib: bool = False

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

    def run(self, *args: Any, **kwargs: Any) -> None:
        """Compile the given source code."""
        self.input_files = kwargs.get("input_files", [])
        self.output_file = kwargs.get("output_file", "")
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

    def show_ast(self) -> None:
        """Print the AST for the given input file."""
        tree_ast = self._get_astx()
        print(tree_ast)

    def show_tokens(self) -> None:
        """Print the AST for the given input file."""
        lexer = Lexer()

        for input_file in self.input_files:
            ArxIO.file_to_buffer(input_file)
            tokens = lexer.lex()
            for token in tokens:
                print(token)

    def show_llvm_ir(self) -> None:
        """Compile into LLVM IR the given input file."""
        tree_ast = self._get_astx()
        ir = LLVMLiteIR()
        print(ir.translator.translate(tree_ast))

    def run_shell(self) -> None:
        """Open arx in shell mode."""
        raise Exception("Arx Shell is not implemented yet.")

    def compile(self, show_llvm_ir: bool = False) -> None:
        """Compile the given input file."""
        tree_ast = self._get_astx()
        ir = LLVMLiteIR()
        ir.build(tree_ast, output_file=self.output_file)
