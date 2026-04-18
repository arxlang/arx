"""
title: Arx main module.
"""

import importlib
import os
import subprocess

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import astx

from irx.analysis.module_interfaces import ParsedModule

from arx.codegen import ArxBuilder
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
class FileImportResolver:
    """
    title: Resolve import specifiers to Arx source files on disk.
    attributes:
      input_files:
        type: tuple[str, Ellipsis]
      cache:
        type: dict[str, ParsedModule]
    """

    input_files: tuple[str, ...]
    cache: dict[str, ParsedModule] = field(default_factory=dict)

    def _candidate_roots(self) -> tuple[Path, ...]:
        """
        title: Build the ordered search roots for module resolution.
        returns:
          type: tuple[Path, Ellipsis]
        """
        roots: list[Path] = []
        seen: set[Path] = set()

        def add_root(path: Path) -> None:
            """
            title: Build the ordered search roots for module resolution.
            parameters:
              path:
                type: Path
            """
            resolved = path.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            roots.append(resolved)

        add_root(Path.cwd())
        for input_file in self.input_files:
            current = Path(input_file).resolve().parent
            while True:
                add_root(current)
                if current == current.parent:
                    break
                current = current.parent

        return tuple(roots)

    def _resolve_module_file(self, requested_specifier: str) -> Path:
        """
        title: Resolve one dotted module specifier to a source file.
        parameters:
          requested_specifier:
            type: str
        returns:
          type: Path
        """
        relative_path = Path(*requested_specifier.split(".")).with_suffix(".x")
        for root in self._candidate_roots():
            candidate = root / relative_path
            if candidate.is_file():
                return candidate
        raise LookupError(requested_specifier)

    def __call__(
        self,
        requesting_module_key: str,
        import_node: astx.ImportStmt | astx.ImportFromStmt,
        requested_specifier: str,
    ) -> ParsedModule:
        """
        title: Resolve one import request to a parsed source module.
        parameters:
          requesting_module_key:
            type: str
          import_node:
            type: astx.ImportStmt | astx.ImportFromStmt
          requested_specifier:
            type: str
        returns:
          type: ParsedModule
        """
        _ = requesting_module_key
        _ = import_node

        cached = self.cache.get(requested_specifier)
        if cached is not None:
            return cached

        module_file = self._resolve_module_file(requested_specifier)
        ArxIO.file_to_buffer(str(module_file))
        module_ast = Parser().parse(Lexer().lex(), requested_specifier)
        parsed_module = ParsedModule(
            key=requested_specifier,
            ast=module_ast,
            display_name=requested_specifier,
            origin=str(module_file),
        )
        self.cache[requested_specifier] = parsed_module
        return parsed_module


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
      link_mode:
        type: Literal[auto, pie, no-pie]
    """

    input_files: list[str] = field(default_factory=list)
    output_file: str = ""
    is_lib: bool = False
    link_mode: Literal["auto", "pie", "no-pie"] = "auto"

    def _format_ast_fallback(self, node: object) -> str:
        """
        title: Format a fallback AST representation.
        parameters:
          node:
            type: object
        returns:
          type: str
        """
        lines: list[str] = []
        seen: set[int] = set()
        self._walk_ast_node(node, lines, depth=0, seen=seen)
        return "\n".join(lines)

    def _walk_ast_node(
        self, node: object, lines: list[str], depth: int, seen: set[int]
    ) -> None:
        """
        title: Walk one AST node for fallback formatting.
        parameters:
          node:
            type: object
          lines:
            type: list[str]
          depth:
            type: int
          seen:
            type: set[int]
        """
        prefix = "  " * depth
        if not isinstance(node, astx.AST):
            lines.append(f"{prefix}{node!r}")
            return

        node_id = id(node)
        if node_id in seen:
            lines.append(f"{prefix}{node.__class__.__name__} (cycle)")
            return
        seen.add(node_id)

        lines.append(f"{prefix}{node.__class__.__name__}")
        for key, value in vars(node).items():
            if key in {
                "kind",
                "loc",
                "ref",
                "comment",
                "parent",
                "position",
            }:
                continue
            self._walk_ast_field(key, value, lines, depth + 1, seen)

    def _walk_ast_field(
        self,
        key: str,
        value: object,
        lines: list[str],
        depth: int,
        seen: set[int],
    ) -> None:
        """
        title: Walk one AST field for fallback formatting.
        parameters:
          key:
            type: str
          value:
            type: object
          lines:
            type: list[str]
          depth:
            type: int
          seen:
            type: set[int]
        """
        prefix = "  " * depth
        if isinstance(value, astx.AST):
            lines.append(f"{prefix}{key}:")
            self._walk_ast_node(value, lines, depth + 1, seen)
            return

        if isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                self._walk_ast_node(item, lines, depth + 1, seen)
            return

        if isinstance(value, (str, int, float, bool)) or value is None:
            lines.append(f"{prefix}{key}: {value!r}")
            return

        lines.append(f"{prefix}{key}: {type(value).__name__}")

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

    def _get_astx(self) -> astx.AST:
        """
        title: Build the parsed AST for the current input files.
        returns:
          type: astx.AST
        """
        lexer = Lexer()
        parser = Parser()
        modules: list[astx.Module] = []

        for input_file in self.input_files:
            ArxIO.file_to_buffer(input_file)
            module_name = get_module_name_from_file_path(input_file)
            module_ast = parser.parse(lexer.lex(), module_name)
            modules.append(module_ast)

        if len(modules) == 1:
            return modules[0]

        tree_ast = astx.Block()
        tree_ast.nodes.extend(modules)
        return tree_ast

    def _get_codegen_astx(self) -> astx.AST:
        """
        title: Build the AST used for code generation.
        returns:
          type: astx.AST
        """
        tree_ast = self._get_astx()
        if (
            isinstance(tree_ast, astx.Block)
            and not isinstance(tree_ast, astx.Module)
            and len(tree_ast.nodes) > 1
        ):
            raise ValueError(
                "Compiling multiple input files in a single invocation "
                "is not supported yet."
            )
        return tree_ast

    def _module_has_imports(self, module: astx.Module) -> bool:
        """
        title: Return whether one module contains import statements.
        parameters:
          module:
            type: astx.Module
        returns:
          type: bool
        """
        return any(
            isinstance(node, (astx.ImportStmt, astx.ImportFromStmt))
            for node in module.nodes
        )

    def _build_multimodule_context(
        self,
        module: astx.Module,
    ) -> tuple[ParsedModule, FileImportResolver]:
        """
        title: Build the IRx multi-module compilation context.
        parameters:
          module:
            type: astx.Module
        returns:
          type: tuple[ParsedModule, FileImportResolver]
        """
        origin = self.input_files[0] if self.input_files else None
        root = ParsedModule(
            key=module.name,
            ast=module,
            display_name=module.name,
            origin=origin,
        )
        return root, FileImportResolver(tuple(self.input_files))

    def _has_main_entry(self, node: astx.AST) -> bool:
        """
        title: Check whether the AST contains a main entry point.
        parameters:
          node:
            type: astx.AST
        returns:
          type: bool
        """
        modules: list[astx.Module] = []

        if isinstance(node, astx.Module):
            modules = [node]
        elif isinstance(node, astx.Block):
            modules = [
                mod_node
                for mod_node in node.nodes
                if isinstance(mod_node, astx.Module)
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
        title: Compile the given source code.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        """
        self.input_files = kwargs.get("input_files", [])
        output_file = kwargs.get("output_file")
        self.output_file = output_file.strip() if output_file else ""
        self.is_lib = kwargs.get("is_lib", False)
        link_mode = str(kwargs.get("link_mode", "auto")).strip().lower()
        if link_mode not in {"auto", "pie", "no-pie"}:
            raise ValueError(
                "Invalid link mode. Expected one of: auto, pie, no-pie."
            )
        self.link_mode = cast(
            Literal["auto", "pie", "no-pie"],
            link_mode,
        )

        if kwargs.get("show_ast"):
            return self.show_ast()

        if kwargs.get("show_tokens"):
            return self.show_tokens()

        if kwargs.get("show_llvm_ir"):
            return self.show_llvm_ir()

        if kwargs.get("shell"):
            return self.run_shell()

        emits_executable = self.compile()
        if kwargs.get("run"):
            if emits_executable is False:
                raise ValueError(
                    "`--run` requires `fn main` (or disable `--lib`)."
                )
            self.run_binary()

    def run_tests(self, **kwargs: Any) -> int:
        """
        title: Collect and execute compiled tests from one Arx entry file.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        returns:
          type: int
        """
        entry_file = str(kwargs.get("input_file", "tests/main.x")).strip()
        name_filter = str(kwargs.get("name_filter", "")).strip()
        fail_fast = bool(kwargs.get("fail_fast", False))
        keep_artifacts = bool(kwargs.get("keep_artifacts", False))
        list_only = bool(kwargs.get("list_only", False))

        link_mode = str(kwargs.get("link_mode", "auto")).strip().lower()
        if link_mode not in {"auto", "pie", "no-pie"}:
            raise ValueError(
                "Invalid link mode. Expected one of: auto, pie, no-pie."
            )
        self.link_mode = cast(
            Literal["auto", "pie", "no-pie"],
            link_mode,
        )

        testing_module = importlib.import_module("arx.testing")
        runner_cls = testing_module.ArxTestRunner

        runner = runner_cls(
            entry_file=entry_file,
            name_filter=name_filter,
            fail_fast=fail_fast,
            keep_artifacts=keep_artifacts,
            list_only=list_only,
            link_mode=self.link_mode,
        )
        summary = runner.run()
        return int(summary.exit_code)

    def show_ast(self) -> None:
        """
        title: Print the AST for the given input file.
        """
        tree_ast = self._get_astx()
        try:
            print(repr(tree_ast))
        except Exception:
            try:
                if hasattr(tree_ast, "to_json"):
                    print(tree_ast.to_json())
                    return
            except Exception:
                pass

            if isinstance(tree_ast, astx.AST):
                print(self._format_ast_fallback(tree_ast))
                return

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
        tree_ast = self._get_codegen_astx()
        ir = ArxBuilder()

        if isinstance(tree_ast, astx.Module) and self._module_has_imports(
            tree_ast
        ):
            root, resolver = self._build_multimodule_context(tree_ast)
            print(ir.translate_modules(root, resolver))
            return

        print(ir.translate(tree_ast))

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

    def compile(self, show_llvm_ir: bool = False) -> bool:
        """
        title: Compile the given input file.
        parameters:
          show_llvm_ir:
            type: bool
        returns:
          type: bool
        """
        _ = show_llvm_ir
        tree_ast = self._get_codegen_astx()
        ir = ArxBuilder()
        self.output_file = self._resolve_output_file()
        emits_executable = not self.is_lib and self._has_main_entry(tree_ast)

        if isinstance(tree_ast, astx.Module) and self._module_has_imports(
            tree_ast
        ):
            root, resolver = self._build_multimodule_context(tree_ast)
            ir.build_modules(
                root,
                resolver,
                output_file=self.output_file,
                link=emits_executable,
                link_mode=self.link_mode,
            )
            return emits_executable

        ir.build(
            tree_ast,
            output_file=self.output_file,
            link=emits_executable,
            link_mode=self.link_mode,
        )
        return emits_executable
