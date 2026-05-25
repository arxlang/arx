"""
title: AIX main compiler frontend orchestration.
"""

from __future__ import annotations

import subprocess

from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Literal, cast

import astx

from aix.io import AixIO
from aix.lexer import Lexer
from aix.parser import Parser

SOURCE_EXTENSION = ".aix"


def get_module_name_from_file_path(filepath: str) -> str:
    """
    title: Return module name from one AIX source path.
    parameters:
      filepath:
        type: str
    returns:
      type: str
    """
    return Path(filepath).with_suffix("").name


class AixMain:
    """
    title: Main AIX frontend facade used by the CLI.
    attributes:
      input_files:
        type: list[str]
      output_file:
        type: str
      is_lib:
        type: bool
      link_mode:
        type: Literal[auto, pie, no-pie]
    """

    input_files: list[str]
    output_file: str
    is_lib: bool
    link_mode: Literal["auto", "pie", "no-pie"]

    def __init__(self) -> None:
        """
        title: Initialize AIX main state.
        """
        self.input_files = []
        self.output_file = ""
        self.is_lib = False
        self.link_mode = "auto"

    def _get_astx(self) -> astx.AST:
        """
        title: Parse configured input files into ASTx nodes.
        returns:
          type: astx.AST
        """
        parser = Parser()
        modules: list[astx.Module] = []
        for input_file in self.input_files:
            AixIO.file_to_buffer(input_file)
            module_name = get_module_name_from_file_path(input_file)
            modules.append(parser.parse(Lexer().lex(), module_name))

        if len(modules) == 1:
            return modules[0]

        tree_ast = astx.Block()
        tree_ast.nodes.extend(modules)
        return tree_ast

    def _resolve_output_file(self) -> str:
        if self.output_file:
            return self.output_file
        if not self.input_files:
            return "a.out"
        return Path(self.input_files[0]).stem or "a.out"

    def _has_main_entry(self, node: astx.AST) -> bool:
        modules: list[astx.Module] = []
        if isinstance(node, astx.Module):
            modules = [node]
        elif isinstance(node, astx.Block):
            modules = [
                item for item in node.nodes if isinstance(item, astx.Module)
            ]

        for module in modules:
            for module_node in module.nodes:
                if (
                    isinstance(module_node, astx.FunctionDef)
                    and module_node.prototype.name == "main"
                ):
                    return True
        return False

    def run(self, **kwargs: Any) -> None:
        """
        title: Run one AIX compiler/frontend action.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        """
        self.input_files = list(kwargs.get("input_files", []))
        output_file = kwargs.get("output_file")
        self.output_file = output_file.strip() if output_file else ""
        self.is_lib = bool(kwargs.get("is_lib", False))
        link_mode = str(kwargs.get("link_mode", "auto")).strip().lower()
        if link_mode not in {"auto", "pie", "no-pie"}:
            raise ValueError(
                "Invalid link mode. Expected auto, pie, or no-pie."
            )
        self.link_mode = cast(Literal["auto", "pie", "no-pie"], link_mode)

        if kwargs.get("show_ast"):
            return self.show_ast()
        if kwargs.get("show_tokens"):
            return self.show_tokens()
        if kwargs.get("show_llvm_ir"):
            return self.show_llvm_ir()
        if kwargs.get("shell"):
            return self.run_shell()
        if not self.input_files:
            return None

        emits_executable = self.compile()
        if kwargs.get("run"):
            if not emits_executable:
                raise ValueError("`--run` requires an AIX main function.")
            self.run_binary()
        return None

    def run_tests(self, **kwargs: Any) -> int:
        """
        title: Discover and parse AIX test source files.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        returns:
          type: int
        """
        paths = tuple(kwargs.get("paths") or ("tests/aix",))
        file_pattern = str(kwargs.get("file_pattern") or "test_*.aix")
        excludes = tuple(kwargs.get("exclude") or ())
        list_only = bool(kwargs.get("list_only", False))

        files = self._discover_test_files(paths, file_pattern, excludes)
        if list_only:
            for path in files:
                print(path)
            return 0

        parser = Parser()
        for path in files:
            try:
                AixIO.file_to_buffer(str(path))
                parser.parse(Lexer().lex(), path.stem)
            except Exception as err:
                print(f"FAILED {path}: {err}")
                return 1
            print(f"PASSED {path}")
        return 0

    def _discover_test_files(
        self,
        paths: tuple[str, ...],
        file_pattern: str,
        excludes: tuple[str, ...],
    ) -> list[Path]:
        files: list[Path] = []
        for entry in paths:
            path = Path(entry)
            if path.is_file() and self._is_included_test(path, excludes):
                files.append(path)
                continue
            if not path.is_dir():
                continue
            for candidate in sorted(path.rglob(file_pattern)):
                if candidate.is_file() and self._is_included_test(
                    candidate,
                    excludes,
                ):
                    files.append(candidate)
        return files

    def _is_included_test(self, path: Path, excludes: tuple[str, ...]) -> bool:
        text = path.as_posix()
        return not any(fnmatch(text, pattern) for pattern in excludes)

    def show_ast(self) -> None:
        """
        title: Print AST for configured input files.
        """
        tree_ast = self._get_astx()
        if hasattr(tree_ast, "to_json"):
            print(tree_ast.to_json())
            return
        print(repr(tree_ast))

    def show_tokens(self) -> None:
        """
        title: Print token stream for configured input files.
        """
        for input_file in self.input_files:
            AixIO.file_to_buffer(input_file)
            for token in Lexer().lex():
                print(token)

    def show_llvm_ir(self) -> None:
        """
        title: Translate configured input to LLVM IR when backend supports it.
        """
        from aix.codegen import AixBuilder

        print(AixBuilder().translate(self._get_astx()))

    def run_shell(self) -> None:
        """
        title: Open shell mode.
        """
        raise NotImplementedError("AIX shell is not implemented yet.")

    def run_binary(self) -> None:
        """
        title: Run generated binary.
        """
        binary_path = Path(self.output_file)
        if not binary_path.is_absolute():
            binary_path = Path.cwd() / binary_path
        result = subprocess.run([str(binary_path)], check=False)
        if result.returncode != 0:
            raise SystemExit(result.returncode)

    def compile(self, show_llvm_ir: bool = False) -> bool:
        """
        title: Compile configured input with the existing IRx backend.
        parameters:
          show_llvm_ir:
            type: bool
        returns:
          type: bool
        """
        _ = show_llvm_ir
        from aix.codegen import AixBuilder

        tree_ast = self._get_astx()
        self.output_file = self._resolve_output_file()
        emits_executable = not self.is_lib and self._has_main_entry(tree_ast)
        AixBuilder().build(
            tree_ast,
            output_file=self.output_file,
            link=emits_executable,
            link_mode=self.link_mode,
        )
        return emits_executable


ArxMain = AixMain
