"""
title: Arx main module.
"""

import importlib
import subprocess
import sys

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import astx

from irx.analysis.module_interfaces import ParsedModule

from arx import settings as arx_settings
from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser

STDLIB_NAMESPACE = "stdlib"


def get_bundled_stdlib_root() -> Path:
    """
    title: Return the bundled stdlib root shipped inside the arx package.
    returns:
      type: Path
    """
    return (Path(__file__).resolve().parent / STDLIB_NAMESPACE).resolve()


def _is_stdlib_specifier(requested_specifier: str) -> bool:
    """
    title: Return whether one import specifier targets the bundled stdlib.
    parameters:
      requested_specifier:
        type: str
    returns:
      type: bool
    """
    return (
        requested_specifier == STDLIB_NAMESPACE
        or requested_specifier.startswith(f"{STDLIB_NAMESPACE}.")
    )


def _find_project_source_root(start: Path) -> Path | None:
    """
    title: Find the configured project source root for a path.
    parameters:
      start:
        type: Path
    returns:
      type: Path | None
    """
    config = arx_settings.find_config_file(start=start)
    if config is None:
        return None

    try:
        project = arx_settings.load_settings(config)
        return arx_settings.resolve_source_root(project)
    except arx_settings.ArxProjectError:
        return None


def _module_name_from_source_root(
    filepath: Path, source_root: Path
) -> str | None:
    """
    title: Derive one dotted module name relative to a source root.
    parameters:
      filepath:
        type: Path
      source_root:
        type: Path
    returns:
      type: str | None
    """
    resolved = filepath.resolve()
    try:
        relative_path = resolved.relative_to(source_root)
    except ValueError:
        return None

    if relative_path.suffix != ".x":
        return None

    module_path = relative_path.with_suffix("")
    if module_path.name == "__init__":
        module_path = module_path.parent

    if not module_path.parts:
        return None

    return ".".join(module_path.parts)


def get_module_name_from_file_path(filepath: str) -> str:
    """
    title: Return the module name from the source file name.
    parameters:
      filepath:
        type: str
    returns:
      type: str
    """
    file_path = Path(filepath)
    source_root = _find_project_source_root(file_path.parent)
    if source_root is not None:
        module_name = _module_name_from_source_root(file_path, source_root)
        if module_name is not None:
            return module_name
    return file_path.stem


@dataclass
class FileImportResolver:
    """
    title: Resolve import specifiers to Arx source files on disk.
    attributes:
      input_files:
        type: tuple[str, Ellipsis]
      cache:
        type: dict[str, ParsedModule]
      _source_root_cache:
        type: dict[Path, Path | None]
    """

    input_files: tuple[str, ...]
    cache: dict[str, ParsedModule] = field(default_factory=dict)
    _source_root_cache: dict[Path, Path | None] = field(default_factory=dict)

    def _project_source_root(self, directory: Path) -> Path | None:
        """
        title: Look up the effective project source root from a manifest.
        parameters:
          directory:
            type: Path
        returns:
          type: Path | None
        """
        if directory in self._source_root_cache:
            return self._source_root_cache[directory]

        config = directory / ".arxproject.toml"
        result: Path | None = None
        if config.is_file():
            settings_module = importlib.import_module("arx.settings")
            try:
                project = settings_module.load_settings(config)
                result = settings_module.resolve_source_root(project)
            except settings_module.ArxProjectError:
                result = None

        self._source_root_cache[directory] = result
        return result

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

            source_root = self._project_source_root(resolved)
            if source_root is not None and source_root not in seen:
                seen.add(source_root)
                roots.append(source_root)

        add_root(Path.cwd())
        for input_file in self.input_files:
            current = Path(input_file).resolve().parent
            while True:
                add_root(current)
                if current == current.parent:
                    break
                current = current.parent

        return tuple(roots)

    def _stdlib_shadow_roots(self) -> tuple[Path, ...]:
        """
        title: Build the local roots that may validly shadow stdlib.
        returns:
          type: tuple[Path, Ellipsis]
        """
        roots: list[Path] = []
        seen: set[Path] = set()

        for input_file in self.input_files:
            input_root = Path(input_file).resolve().parent
            source_root = _find_project_source_root(input_root)
            root = source_root if source_root is not None else input_root
            if root in seen:
                continue
            seen.add(root)
            roots.append(root)

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
        if _is_stdlib_specifier(requested_specifier):
            return self._resolve_stdlib_module_file(requested_specifier)

        package_path = Path(*requested_specifier.split("."))
        file_candidate = package_path.with_suffix(".x")
        init_candidate = package_path / "__init__.x"
        for root in self._candidate_roots():
            init_path = (root / init_candidate).resolve()
            file_path = (root / file_candidate).resolve()
            has_init = init_path.is_file()
            has_file = file_path.is_file()
            if has_init and has_file:
                raise LookupError(
                    "ambiguous module specifier "
                    f"'{requested_specifier}': both "
                    f"'{file_path}' and '{init_path}' exist"
                )
            if has_init:
                return init_path
            if has_file:
                return file_path
        raise LookupError(requested_specifier)

    def _shadowing_stdlib_path(
        self,
        requested_specifier: str,
    ) -> Path | None:
        """
        title: Return one local path that attempts to shadow the stdlib.
        parameters:
          requested_specifier:
            type: str
        returns:
          type: Path | None
        """
        package_path = Path(*requested_specifier.split("."))
        file_candidate = package_path.with_suffix(".x")
        init_candidate = package_path / "__init__.x"
        for root in self._stdlib_shadow_roots():
            init_path = (root / init_candidate).resolve()
            file_path = (root / file_candidate).resolve()
            if init_path.is_file():
                return init_path
            if file_path.is_file():
                return file_path
        return None

    def _resolve_stdlib_module_file(self, requested_specifier: str) -> Path:
        """
        title: Resolve one stdlib module specifier from bundled package data.
        parameters:
          requested_specifier:
            type: str
        returns:
          type: Path
        """
        shadowing_path = self._shadowing_stdlib_path(requested_specifier)
        if shadowing_path is not None:
            raise ValueError(
                "reserved stdlib namespace 'stdlib' cannot be shadowed by "
                f"local source file '{shadowing_path}'"
            )

        stdlib_root = get_bundled_stdlib_root()
        relative_parts = requested_specifier.split(".")[1:]
        if not relative_parts:
            init_path = (stdlib_root / "__init__.x").resolve()
            if init_path.is_file():
                return init_path
            raise LookupError(requested_specifier)

        package_path = Path(*relative_parts)
        file_path = (stdlib_root / package_path).with_suffix(".x").resolve()
        init_path = (stdlib_root / package_path / "__init__.x").resolve()
        has_init = init_path.is_file()
        has_file = file_path.is_file()
        if has_init and has_file:
            raise LookupError(
                "ambiguous module specifier "
                f"'{requested_specifier}': both "
                f"'{file_path}' and '{init_path}' exist"
            )
        if has_init:
            return init_path
        if has_file:
            return file_path
        raise LookupError(requested_specifier)

    def _current_package_parts(
        self, requesting_module_key: str
    ) -> tuple[str, ...]:
        """
        title: Resolve the current package path for relative imports.
        parameters:
          requesting_module_key:
            type: str
        returns:
          type: tuple[str, Ellipsis]
        """
        module_file = self._resolve_module_file(requesting_module_key)
        parts = tuple(
            part for part in requesting_module_key.split(".") if part
        )
        if module_file.name == "__init__.x":
            return parts
        if len(parts) > 1:
            return parts[:-1]
        raise LookupError(
            "relative imports require the requesting module to live inside "
            "a package"
        )

    def _normalize_module_specifier(
        self,
        requesting_module_key: str,
        requested_specifier: str,
    ) -> str:
        """
        title: Normalize one requested module specifier to a dotted key.
        parameters:
          requesting_module_key:
            type: str
          requested_specifier:
            type: str
        returns:
          type: str
        """
        if not requested_specifier.startswith("."):
            return requested_specifier

        level = len(requested_specifier) - len(requested_specifier.lstrip("."))
        module_path = requested_specifier[level:]
        if not module_path:
            raise LookupError(
                "relative imports require a module path after the leading dots"
            )

        package_parts = self._current_package_parts(requesting_module_key)
        if level > len(package_parts):
            raise LookupError(
                "relative import climbs beyond the top-level package for "
                f"module '{requesting_module_key}'"
            )

        base_parts = package_parts[: len(package_parts) - (level - 1)]
        if not base_parts:
            raise LookupError(
                "relative import climbs beyond the top-level package for "
                f"module '{requesting_module_key}'"
            )

        return ".".join([*base_parts, *module_path.split(".")])

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
        _ = import_node

        resolved_specifier = self._normalize_module_specifier(
            requesting_module_key,
            requested_specifier,
        )

        cached = self.cache.get(resolved_specifier)
        if cached is not None:
            return cached

        module_file = self._resolve_module_file(resolved_specifier)
        ArxIO.file_to_buffer(str(module_file))
        module_ast = Parser().parse(Lexer().lex(), resolved_specifier)
        parsed_module = ParsedModule(
            key=resolved_specifier,
            ast=module_ast,
            display_name=resolved_specifier,
            origin=str(module_file),
        )
        self.cache[resolved_specifier] = parsed_module
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
        title: Collect and execute compiled tests from configured paths.
        parameters:
          kwargs:
            type: Any
            variadic: keyword
        returns:
          type: int
        """
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
        settings_module = importlib.import_module("arx.settings")
        try:
            runner_kwargs = self._build_test_runner_kwargs(kwargs)
        except settings_module.ArxProjectError as err:
            print(
                f"ERROR: invalid [tests] configuration: {err}",
                file=sys.stderr,
            )
            return 2

        runner = runner_cls(
            **runner_kwargs,
            name_filter=name_filter,
            fail_fast=fail_fast,
            keep_artifacts=keep_artifacts,
            list_only=list_only,
            link_mode=self.link_mode,
        )
        summary = runner.run()
        return int(summary.exit_code)

    def _build_test_runner_kwargs(
        self,
        cli_kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        title: Layer runner defaults, [tests] settings, and CLI args.
        parameters:
          cli_kwargs:
            type: dict[str, Any]
        returns:
          type: dict[str, Any]
        """
        testing_module = importlib.import_module("arx.testing")
        resolved: dict[str, Any] = {
            "paths": testing_module.DEFAULT_TEST_PATHS,
            "exclude": (),
            "file_pattern": testing_module.DEFAULT_TEST_FILE_PATTERN,
            "function_pattern": testing_module.DEFAULT_TEST_FUNCTION_PATTERN,
        }

        tests_settings = self._load_tests_settings()
        if tests_settings is not None:
            if tests_settings.paths is not None:
                resolved["paths"] = tuple(tests_settings.paths)
            if tests_settings.exclude is not None:
                resolved["exclude"] = tuple(tests_settings.exclude)
            if tests_settings.file_pattern is not None:
                resolved["file_pattern"] = tests_settings.file_pattern
            if tests_settings.function_pattern is not None:
                resolved["function_pattern"] = tests_settings.function_pattern

        cli_paths = cli_kwargs.get("paths")
        if cli_paths:
            resolved["paths"] = tuple(cli_paths)

        cli_exclude = cli_kwargs.get("exclude")
        if cli_exclude is not None:
            resolved["exclude"] = tuple(cli_exclude)

        cli_file_pattern = cli_kwargs.get("file_pattern")
        if cli_file_pattern is not None:
            resolved["file_pattern"] = cli_file_pattern

        cli_function_pattern = cli_kwargs.get("function_pattern")
        if cli_function_pattern is not None:
            resolved["function_pattern"] = cli_function_pattern

        return resolved

    def _load_tests_settings(self) -> Any:
        """
        title: Load ``[tests]`` from ``.arxproject.toml`` if present.
        returns:
          type: Any
        """
        try:
            settings_module = importlib.import_module("arx.settings")
        except ImportError:
            return None

        config_path = settings_module.find_config_file()
        if config_path is None:
            return None
        project = settings_module.load_settings(config_path)
        return project.tests

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
