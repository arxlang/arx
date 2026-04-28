"""
title: Coverage-oriented tests for app/runtime modules.
"""

from __future__ import annotations

import io
import runpy
import subprocess
import sys

from argparse import Namespace
from pathlib import Path

import arx.cli as cli_module
import arx.main as main_module
import arx.testing as testing_module
import astx
import astx as irx_astx
import pytest

from arx import __version__, builtins
from arx.docstrings import validate_docstring
from arx.exceptions import CodeGenException, ParserException
from arx.io import ArxBuffer, ArxFile, ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from arx.testing import TestRunSummary as _TestRunSummary


def test_builtins_helpers() -> None:
    """
    title: Test builtins helper functions.
    """
    assert builtins.is_builtin("cast")
    assert builtins.is_builtin("isinstance")
    assert builtins.is_builtin("print")
    assert builtins.is_builtin("type")
    assert not builtins.is_builtin("custom_fn")

    cast_node = builtins.build_cast(astx.LiteralInt32(1), astx.Float32())
    isinstance_node = builtins.build_isinstance(
        astx.LiteralInt32(1),
        astx.Int32(),
    )
    print_node = builtins.build_print(astx.LiteralString("hello"))
    type_node = builtins.build_type_of(astx.LiteralInt32(1))
    assert isinstance(cast_node, irx_astx.Cast)
    assert isinstance(isinstance_node, irx_astx.IsInstanceExpr)
    assert isinstance(print_node, irx_astx.PrintExpr)
    assert isinstance(type_node, irx_astx.TypeOfExpr)


def test_custom_exceptions_prefixes() -> None:
    """
    title: Test custom exception message prefixes.
    """
    assert str(ParserException("bad parser")) == "ParserError: bad parser"
    assert str(CodeGenException("bad codegen")) == "CodeGenError: bad codegen"


def test_validate_docstring_error_paths() -> None:
    """
    title: Cover docstring validation error branches.
    """
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_docstring("   ")

    with pytest.raises(ValueError, match="valid YAML"):
        validate_docstring("title: [")

    with pytest.raises(ValueError, match="object mapping"):
        validate_docstring("- item")

    with pytest.raises(ValueError, match="douki schema"):
        validate_docstring("summary: missing required title")

    valid = validate_docstring("title: Valid\nsummary: ok")
    assert valid["title"] == "Valid"


def test_arxbuffer_read_past_end_returns_empty() -> None:
    """
    title: Test ArxBuffer EOF behavior.
    """
    buffer = ArxBuffer()
    buffer.write("ab")

    assert buffer.read() == "a"
    assert buffer.read() == "b"
    assert buffer.read() == ""


def test_arxio_get_char_from_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    title: Test stdin path in ArxIO.get_char.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.setattr(sys, "stdin", io.StringIO("z"))
    ArxIO.INPUT_FROM_STDIN = True
    try:
        assert ArxIO.get_char() == "z"
    finally:
        ArxIO.INPUT_FROM_STDIN = False


def test_arxio_file_and_stdin_loaders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    title: Test ArxIO input loading helpers.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    sample = tmp_path / "sample.x"
    sample.write_text("fn main() -> i32:\n  return 1\n", encoding="utf-8")
    ArxIO.file_to_buffer(str(sample))
    assert "fn main()" in ArxIO.buffer.buffer

    calls: dict[str, str] = {}

    def fake_file_to_buffer(cls: type[ArxIO], filename: str) -> None:
        """
        title: Fake file-to-buffer loader.
        parameters:
          cls:
            type: type[ArxIO]
          filename:
            type: str
        """
        calls["filename"] = filename

    monkeypatch.setattr(
        ArxIO, "file_to_buffer", classmethod(fake_file_to_buffer)
    )
    ArxIO.INPUT_FILE = str(sample)
    ArxIO.load_input_to_buffer()
    assert calls["filename"] == str(sample.resolve())

    ArxIO.INPUT_FILE = ""
    monkeypatch.setattr(sys, "stdin", io.StringIO("  abc  "))
    ArxIO.buffer.clean()
    ArxIO.load_input_to_buffer()
    assert ArxIO.buffer.buffer == "abc"

    monkeypatch.setattr(sys, "stdin", io.StringIO("   "))
    ArxIO.buffer.write("keep")
    ArxIO.load_input_to_buffer()
    assert ArxIO.buffer.buffer.endswith("keep")


def test_arxfile_create_and_delete_roundtrip() -> None:
    """
    title: Test temporary file creation and deletion.
    """
    filename = ArxFile.create_tmp_file("int main() { return 0; }")
    assert filename.endswith(".cpp")
    assert Path(filename).exists()

    assert ArxFile.delete_file(filename) == 0
    assert not Path(filename).exists()
    assert ArxFile.delete_file(filename) == -1


def test_cli_get_args_parsing() -> None:
    """
    title: Test CLI parser options.
    """
    parser = cli_module.get_args()
    args = parser.parse_args(
        [
            "examples/sum.x",
            "--output-file",
            "out.o",
            "--lib",
            "--show-tokens",
            "--link-mode",
            "no-pie",
        ]
    )

    assert args.input_files == ["examples/sum.x"]
    assert args.output_file == "out.o"
    assert args.is_lib is True
    assert args.show_tokens is True
    assert args.link_mode == "no-pie"
    assert args.run is False


def test_cli_get_test_args_parsing() -> None:
    """
    title: Test `arx test` CLI parser options.
    """
    parser = cli_module.get_test_args()
    args = parser.parse_args(
        [
            "tests/arx/test_math.x",
            "tests/arx/integration",
            "--list",
            "-k",
            "fib",
            "-x",
            "--keep-artifacts",
            "--exclude",
            "tests/arx/slow_*.x",
            "--file-pattern",
            "check_*.x",
            "--function-pattern",
            "check_*",
            "--link-mode",
            "no-pie",
        ]
    )

    assert args.paths == ["tests/arx/test_math.x", "tests/arx/integration"]
    assert args.list_only is True
    assert args.name_filter == "fib"
    assert args.fail_fast is True
    assert args.keep_artifacts is True
    assert args.exclude == ["tests/arx/slow_*.x"]
    assert args.file_pattern == "check_*.x"
    assert args.function_pattern == "check_*"
    assert args.link_mode == "no-pie"


def test_cli_show_version(capsys: pytest.CaptureFixture[str]) -> None:
    """
    title: Test version output.
    parameters:
      capsys:
        type: pytest.CaptureFixture[str]
    """
    cli_module.show_version()
    assert __version__ in capsys.readouterr().out


def test_cli_app_version_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    title: Test CLI app version branch.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    class DummyParser:
        def parse_args(self) -> Namespace:
            """
            title: Return CLI args for the version branch.
            returns:
              type: Namespace
            """
            return Namespace(
                input_files=[],
                version=True,
                output_file="",
                is_lib=False,
                link_mode="auto",
                show_ast=False,
                show_tokens=False,
                show_llvm_ir=False,
                shell=False,
                run=False,
            )

    called: dict[str, bool] = {"version": False}

    def fake_show_version() -> None:
        """
        title: Record that show_version was called.
        """
        called["version"] = True

    def fake_get_args() -> DummyParser:
        """
        title: Return a dummy CLI parser.
        returns:
          type: DummyParser
        """
        return DummyParser()

    monkeypatch.setattr(cli_module, "get_args", fake_get_args)
    monkeypatch.setattr(cli_module, "show_version", fake_show_version)

    cli_module.app()
    assert called["version"] is True


def test_cli_app_test_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    title: Test CLI dispatch for the `arx test` subcommand.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    class DummyMain:
        called_kwargs: dict[str, object] = {}

        def run_tests(self, **kwargs: object) -> int:
            """
            title: Record forwarded test-runner kwargs.
            parameters:
              kwargs:
                type: object
                variadic: keyword
            returns:
              type: int
            """
            DummyMain.called_kwargs = kwargs
            return 0

    monkeypatch.setattr(cli_module, "ArxMain", DummyMain)
    cli_module.app(
        [
            "test",
            "tests/arx/test_math.x",
            "--list",
            "--exclude",
            "tests/arx/slow_*.x",
        ]
    )

    assert DummyMain.called_kwargs["paths"] == ["tests/arx/test_math.x"]
    assert DummyMain.called_kwargs["list_only"] is True
    assert DummyMain.called_kwargs["exclude"] == ["tests/arx/slow_*.x"]


def test_cli_app_test_branch_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test CLI exits nonzero when `arx test` reports failures.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    class DummyMain:
        def run_tests(self, **kwargs: object) -> int:
            """
            title: Return a failing exit status for the test branch.
            parameters:
              kwargs:
                type: object
                variadic: keyword
            returns:
              type: int
            """
            del kwargs
            return 1

    monkeypatch.setattr(cli_module, "ArxMain", DummyMain)
    with pytest.raises(SystemExit, match="1"):
        cli_module.app(["test"])


def test_cli_app_test_autoloads_tests_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Auto-load tests settings from .arxproject.toml when present.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    (tmp_path / ".arxproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n\n'
        '[tests]\npaths = ["custom"]\nexclude = ["custom/skip_*.x"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    captured_kwargs: dict[str, object] = {}

    class DummyRunner:
        def __init__(self, **kwargs: object) -> None:
            """
            title: Record runner kwargs.
            parameters:
              kwargs:
                type: object
                variadic: keyword
            """
            captured_kwargs.update(kwargs)

        def run(self) -> object:
            """
            title: Return a passing summary placeholder.
            returns:
              type: object
            """
            return _TestRunSummary(
                selected=0,
                executed=0,
                passed=0,
                failed=0,
                exit_code=0,
                results=(),
            )

    monkeypatch.setattr(testing_module, "ArxTestRunner", DummyRunner)
    cli_module.app(["test"])

    assert captured_kwargs["paths"] == ("custom",)
    assert captured_kwargs["exclude"] == ("custom/skip_*.x",)


def test_cli_app_test_cli_exclude_reaches_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: CLI `--exclude` flag forwards to the runner as a tuple.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    monkeypatch.chdir(tmp_path)

    captured_kwargs: dict[str, object] = {}

    class DummyRunner:
        def __init__(self, **kwargs: object) -> None:
            """
            title: Record runner kwargs.
            parameters:
              kwargs:
                type: object
                variadic: keyword
            """
            captured_kwargs.update(kwargs)

        def run(self) -> object:
            """
            title: Return a passing summary placeholder.
            returns:
              type: object
            """
            return _TestRunSummary(
                selected=0,
                executed=0,
                passed=0,
                failed=0,
                exit_code=0,
                results=(),
            )

    monkeypatch.setattr(testing_module, "ArxTestRunner", DummyRunner)
    cli_module.app(
        [
            "test",
            "--exclude",
            "slow_*.x",
            "--exclude",
            "wip_*.x",
        ]
    )

    assert captured_kwargs["exclude"] == ("slow_*.x", "wip_*.x")


def test_cli_app_test_invalid_tests_config_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Invalid .arxproject.toml tests section exits 2 with an error.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    (tmp_path / ".arxproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.1"\n\n[tests]\npaths = 1\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    class BoomRunner:
        def __init__(self, **kwargs: object) -> None:
            """
            title: Fail if the runner is ever constructed.
            parameters:
              kwargs:
                type: object
                variadic: keyword
            """
            del kwargs
            raise AssertionError("runner must not be constructed")

        def run(self) -> object:
            """
            title: Unreachable.
            returns:
              type: object
            """
            raise AssertionError("runner must not run")

    monkeypatch.setattr(testing_module, "ArxTestRunner", BoomRunner)

    with pytest.raises(SystemExit) as excinfo:
        cli_module.app(["test"])

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "ERROR: invalid [tests] configuration" in err


def test_cli_app_run_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Test CLI app run branch.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    entry = tmp_path / "a.x"
    entry.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    class DummyParser:
        def parse_args(self) -> Namespace:
            """
            title: Return CLI args for the run branch.
            returns:
              type: Namespace
            """
            return Namespace(
                input_files=["a.x"],
                version=False,
                output_file="out.o",
                is_lib=True,
                link_mode="auto",
                show_ast=False,
                show_tokens=True,
                show_llvm_ir=False,
                shell=False,
                run=False,
            )

    class DummyMain:
        called_kwargs: dict[str, object] = {}

        def run(self, **kwargs: object) -> None:
            """
            title: Record forwarded CLI kwargs.
            parameters:
              kwargs:
                type: object
                variadic: keyword
            """
            DummyMain.called_kwargs = kwargs

    def fake_get_args() -> DummyParser:
        """
        title: Return a dummy CLI parser.
        returns:
          type: DummyParser
        """
        return DummyParser()

    monkeypatch.setattr(cli_module, "get_args", fake_get_args)
    monkeypatch.setattr(cli_module, "ArxMain", DummyMain)

    cli_module.app()
    assert DummyMain.called_kwargs["input_files"] == ["a.x"]
    assert DummyMain.called_kwargs["show_tokens"] is True


def test_cli_app_run_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """
    title: Test CLI app run alias dispatch.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    entry = tmp_path / "prog.x"
    entry.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    class DummyParser:
        def parse_args(self) -> Namespace:
            """
            title: Return CLI args for the run alias branch.
            returns:
              type: Namespace
            """
            return Namespace(
                input_files=["run", "prog.x"],
                version=False,
                output_file="",
                is_lib=True,
                link_mode="auto",
                show_ast=False,
                show_tokens=False,
                show_llvm_ir=False,
                shell=False,
                run=False,
            )

    class DummyMain:
        called_kwargs: dict[str, object] = {}

        def run(self, **kwargs: object) -> None:
            """
            title: Record forwarded CLI kwargs.
            parameters:
              kwargs:
                type: object
                variadic: keyword
            """
            DummyMain.called_kwargs = kwargs

    def fake_get_args() -> DummyParser:
        """
        title: Return a dummy CLI parser.
        returns:
          type: DummyParser
        """
        return DummyParser()

    monkeypatch.setattr(cli_module, "get_args", fake_get_args)
    monkeypatch.setattr(cli_module, "ArxMain", DummyMain)

    cli_module.app()
    assert DummyMain.called_kwargs["input_files"] == ["prog.x"]
    assert DummyMain.called_kwargs["run"] is True


def test_cli_app_unknown_subcommand_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test unknown subcommand tokens exit with code 2 and no traceback.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        cli_module.app(["healthcheck"])

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "unknown command 'healthcheck'" in err
    assert "known subcommands" in err
    assert "test" in err


def test_cli_app_missing_input_file_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: Test missing .x input file reports a precise file-not-found error.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
      capsys:
        type: pytest.CaptureFixture[str]
    """
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        cli_module.app(["missing.x"])

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "input file not found: 'missing.x'" in err
    assert "unknown command" not in err


def test_python_m_entrypoint_calls_cli_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test python -m arx entrypoint.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    called: dict[str, bool] = {"app": False}

    def fake_app() -> None:
        """
        title: Record that the CLI app was invoked.
        """
        called["app"] = True

    monkeypatch.setattr(cli_module, "app", fake_app)
    runpy.run_module("arx.__main__", run_name="__main__")
    assert called["app"] is True


def test_main_module_name_helper(tmp_path: Path) -> None:
    """
    title: Test module-name extraction helper outside project src_dir.
    parameters:
      tmp_path:
        type: Path
    """
    sample = tmp_path / "examples" / "sample.x"
    sample.parent.mkdir()
    sample.write_text(
        "fn main() -> i32:\n  return 0\n",
        encoding="utf-8",
    )

    assert main_module.get_module_name_from_file_path(str(sample)) == "sample"


def test_main_module_name_helper_uses_package_init_module_name(
    tmp_path: Path,
) -> None:
    """
    title: Package __init__ files map to the package dotted name.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "workspace"
    module_file = project_root / "src" / "samplepkg" / "__init__.x"
    module_file.parent.mkdir(parents=True)
    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n',
        encoding="utf-8",
    )
    module_file.write_text(
        "fn helper() -> i32:\n  return 1\n",
        encoding="utf-8",
    )

    assert (
        main_module.get_module_name_from_file_path(str(module_file))
        == "samplepkg"
    )


def test_main_module_name_helper_uses_src_relative_package_name(
    tmp_path: Path,
) -> None:
    """
    title: Module-name extraction uses dotted names under [build].src_dir.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "workspace"
    module_file = project_root / "src" / "samplepkg" / "core.x"
    module_file.parent.mkdir(parents=True)
    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    module_file.write_text(
        "fn helper() -> i32:\n  return 1\n",
        encoding="utf-8",
    )

    assert (
        main_module.get_module_name_from_file_path(str(module_file))
        == "samplepkg.core"
    )


def test_arxmain_resolve_output_file_empty_inputs() -> None:
    """
    title: Default output base is a.out when no inputs and no output set.
    """
    app = main_module.ArxMain(input_files=[], output_file="")
    assert app._resolve_output_file() == "a.out"


def test_arxmain_get_astx_single_file_returns_module(tmp_path: Path) -> None:
    """
    title: Single input file yields an astx.Module from _get_astx.
    parameters:
      tmp_path:
        type: Path
    """
    src = tmp_path / "one.x"
    src.write_text(
        "```\ntitle: One\n```\nfn main() -> i32:\n  return 0\n",
        encoding="utf-8",
    )
    app = main_module.ArxMain(input_files=[str(src)])
    tree = app._get_astx()
    assert isinstance(tree, astx.Module)
    assert tree.name == "one"


def test_arxmain_get_astx_uses_package_init_module_name(
    tmp_path: Path,
) -> None:
    """
    title: _get_astx maps package __init__ files to package names.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "workspace"
    src = project_root / "src" / "samplepkg" / "__init__.x"
    src.parent.mkdir(parents=True)
    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    src.write_text(
        "```\ntitle: Package\n```\nfn main() -> i32:\n  return 0\n",
        encoding="utf-8",
    )

    app = main_module.ArxMain(input_files=[str(src)])
    tree = app._get_astx()
    assert isinstance(tree, astx.Module)
    assert tree.name == "samplepkg"


def test_arxmain_get_astx_uses_src_relative_module_name(
    tmp_path: Path,
) -> None:
    """
    title: _get_astx uses dotted module names for package files.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "workspace"
    src = project_root / "src" / "samplepkg" / "core.x"
    src.parent.mkdir(parents=True)
    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    src.write_text(
        "```\ntitle: Core\n```\nfn main() -> i32:\n  return 0\n",
        encoding="utf-8",
    )

    app = main_module.ArxMain(input_files=[str(src)])
    tree = app._get_astx()
    assert isinstance(tree, astx.Module)
    assert tree.name == "samplepkg.core"


def test_arxmain_get_codegen_rejects_multi_module_block() -> None:
    """
    title: Codegen entry rejects a Block with multiple modules.
    """
    app = main_module.ArxMain()
    bundle = astx.Block()
    bundle.nodes.extend([astx.Module("a"), astx.Module("b")])

    def fake_get_astx() -> astx.AST:
        """
        title: Return a multi-module block.
        returns:
          type: astx.AST
        """
        return bundle

    setattr(app, "_get_astx", fake_get_astx)

    with pytest.raises(ValueError, match="multiple input files"):
        app._get_codegen_astx()


def test_arxmain_run_invalid_link_mode() -> None:
    """
    title: run() rejects unknown link_mode values.
    """
    app = main_module.ArxMain()
    with pytest.raises(ValueError, match="Invalid link mode"):
        app.run(input_files=[], link_mode="bogus")


def test_arxmain_has_main_entry_block_of_modules() -> None:
    """
    title: _has_main_entry finds main inside a Block of Module nodes.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: M\n```\nfn main() -> i32:\n  return 0\n"
    )
    lexer = Lexer()
    parser = Parser()
    mod = parser.parse(lexer.lex(), "boxed")

    app = main_module.ArxMain()
    assert app._has_main_entry(mod) is True

    block = astx.Block()
    block.nodes.append(mod)
    assert app._has_main_entry(block) is True

    empty = astx.Block()
    empty.nodes.append(astx.Module("empty"))
    assert app._has_main_entry(empty) is False


def test_arxmain_format_ast_fallback_walks_simple_values() -> None:
    """
    title: Fallback AST formatter handles non-AST roots and simple fields.
    """
    app = main_module.ArxMain()
    assert "42" in app._format_ast_fallback(42)


def test_arxmain_format_ast_fallback_cycle_and_exotic_fields() -> None:
    """
    title: Fallback walker reports cycles and unknown field value types.
    """
    ArxIO.string_to_buffer(
        "```\ntitle: M\n```\nfn main() -> i32:\n  return 0\n"
    )
    lexer = Lexer()
    parser = Parser()
    mod = parser.parse(lexer.lex(), "walk")

    outer = astx.Block()
    inner = astx.Block()
    outer.nodes.append(inner)
    inner.nodes.append(outer)

    app = main_module.ArxMain()
    out = app._format_ast_fallback(outer)
    assert "cycle" in out

    setattr(mod, "meta", object())
    meta_out = app._format_ast_fallback(mod)
    assert "meta" in meta_out
    assert "object" in meta_out


def test_arxmain_show_ast_prefers_to_json_when_repr_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    title: show_ast prints to_json when repr fails but to_json works.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      capsys:
        type: pytest.CaptureFixture[str]
    """
    app = main_module.ArxMain(input_files=["irrelevant.x"])

    class JsonTree(astx.Module):
        """
        title: Module-like node with failing repr and working to_json.
        """

        def __init__(self) -> None:
            """
            title: Initialize the synthetic tree root.
            """
            super().__init__("j")

        def __repr__(self) -> str:
            """
            title: Force repr failure.
            returns:
              type: str
            """
            raise RuntimeError("repr unavailable")

        def to_json(self, simplified: bool = False) -> str:
            """
            title: Return deterministic JSON text.
            parameters:
              simplified:
                type: bool
            returns:
              type: str
            """
            del simplified
            return '{"via": "json"}'

    def fake_get_astx_json() -> JsonTree:
        """
        title: Supply JsonTree for show_ast coverage.
        returns:
          type: JsonTree
        """
        return JsonTree()

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_json)
    app.show_ast()
    assert '{"via": "json"}' in capsys.readouterr().out


def test_arxmain_show_ast_fallback_tree_formatter_when_repr_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    title: show_ast uses _format_ast_fallback when repr and to_json fail.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      capsys:
        type: pytest.CaptureFixture[str]
    """
    app = main_module.ArxMain(input_files=["irrelevant.x"])

    class BadReprModule(astx.Module):
        """
        title: Real AST node with broken repr and failing to_json.
        """

        def __init__(self) -> None:
            """
            title: Initialize the synthetic module node.
            """
            super().__init__("badrepr")

        def __repr__(self) -> str:
            """
            title: Force repr failure for AST nodes.
            returns:
              type: str
            """
            raise RuntimeError("repr broken")

        def to_json(self, simplified: bool = False) -> str:
            """
            title: Force the JSON path to fail after repr fails.
            parameters:
              simplified:
                type: bool
            returns:
              type: str
            """
            del simplified
            raise RuntimeError("json also broken")

    def fake_get_astx_badrepr() -> BadReprModule:
        """
        title: Supply BadReprModule for fallback formatter coverage.
        returns:
          type: BadReprModule
        """
        return BadReprModule()

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_badrepr)
    app.show_ast()
    out = capsys.readouterr().out
    assert "Module" in out or "badrepr" in out


def test_arxmain_get_astx_uses_all_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test ArxMain internal AST aggregation.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    loaded_files: list[str] = []
    parsed_modules: list[str] = []

    class DummyLexer:
        def lex(self) -> list[str]:
            """
            title: Return placeholder lexer tokens.
            returns:
              type: list[str]
            """
            return ["TOKENS"]

    class DummyParser:
        def parse(
            self, tokens: list[str], module_name: str = "main"
        ) -> astx.Module:
            """
            title: Return a module for the requested name.
            parameters:
              tokens:
                type: list[str]
              module_name:
                type: str
            returns:
              type: astx.Module
            """
            assert tokens == ["TOKENS"]
            parsed_modules.append(module_name)
            return astx.Module(module_name)

    def fake_file_to_buffer(cls: type[ArxIO], filename: str) -> None:
        """
        title: Record file loading requests.
        parameters:
          cls:
            type: type[ArxIO]
          filename:
            type: str
        """
        loaded_files.append(filename)

    monkeypatch.setattr(main_module, "Lexer", DummyLexer)
    monkeypatch.setattr(main_module, "Parser", DummyParser)
    monkeypatch.setattr(
        ArxIO, "file_to_buffer", classmethod(fake_file_to_buffer)
    )

    app = main_module.ArxMain(
        input_files=[".tmp/tests/demo/a.x", ".tmp/tests/demo/b.x"],
        output_file="out.o",
    )
    tree = app._get_astx()

    assert loaded_files == [".tmp/tests/demo/a.x", ".tmp/tests/demo/b.x"]
    assert parsed_modules == ["a", "b"]
    assert isinstance(tree, astx.Block)
    assert len(tree.nodes) == 2


def test_arxmain_run_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    title: Test ArxMain.run dispatch branches.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    app = main_module.ArxMain()

    called: dict[str, bool] = {
        "ast": False,
        "tokens": False,
        "llvm": False,
        "shell": False,
        "run_binary": False,
    }

    def fake_show_ast() -> None:
        """
        title: Record show_ast dispatch.
        """
        called["ast"] = True

    def fake_show_tokens() -> None:
        """
        title: Record show_tokens dispatch.
        """
        called["tokens"] = True

    def fake_show_llvm_ir() -> None:
        """
        title: Record show_llvm_ir dispatch.
        """
        called["llvm"] = True

    def fake_run_shell() -> None:
        """
        title: Record run_shell dispatch.
        """
        called["shell"] = True

    def fake_run_binary() -> None:
        """
        title: Record run_binary dispatch.
        """
        called["run_binary"] = True

    monkeypatch.setattr(app, "show_ast", fake_show_ast)
    monkeypatch.setattr(app, "show_tokens", fake_show_tokens)
    monkeypatch.setattr(app, "show_llvm_ir", fake_show_llvm_ir)
    monkeypatch.setattr(app, "run_shell", fake_run_shell)
    monkeypatch.setattr(app, "run_binary", fake_run_binary)

    compiled: dict[str, bool] = {"called": False}

    def fake_compile() -> bool:
        """
        title: Record compile dispatch.
        returns:
          type: bool
        """
        compiled["called"] = True
        return True

    monkeypatch.setattr(app, "compile", fake_compile)

    app.run(
        input_files=["a.x"],
        output_file="o",
        is_lib=False,
        show_ast=True,
    )
    app.run(show_tokens=True)
    app.run(show_llvm_ir=True)
    app.run(shell=True)
    app.run(run=True)

    app.run()
    assert compiled["called"] is True
    assert called["ast"] is True
    assert called["tokens"] is True
    assert called["llvm"] is True
    assert called["shell"] is True
    assert called["run_binary"] is True
    assert app.is_lib is False


def test_arxmain_show_methods_and_compile(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    title: Test ArxMain show/compile helpers.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      capsys:
        type: pytest.CaptureFixture[str]
    """
    app = main_module.ArxMain(input_files=["sample.x"], output_file="out.o")

    class ReprTree:
        def __repr__(self) -> str:
            """
            title: Return a stable repr string.
            returns:
              type: str
            """
            return "TREE"

    def fake_get_astx_tree() -> ReprTree:
        """
        title: Return a tree with a stable repr.
        returns:
          type: ReprTree
        """
        return ReprTree()

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    app.show_ast()
    assert "TREE" in capsys.readouterr().out

    class ReprFailTree:
        def __repr__(self) -> str:
            """
            title: Raise when repr is requested.
            returns:
              type: str
            """
            raise RuntimeError("repr failure")

        def __str__(self) -> str:
            """
            title: Return a fallback string form.
            returns:
              type: str
            """
            return "TREE_FALLBACK"

    def fake_get_astx_tree_fallback() -> ReprFailTree:
        """
        title: Return a tree with a failing repr.
        returns:
          type: ReprFailTree
        """
        return ReprFailTree()

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree_fallback)
    app.show_ast()
    assert "TREE_FALLBACK" in capsys.readouterr().out

    class DummyLexer:
        def lex(self) -> list[str]:
            """
            title: Return placeholder tokens for show_tokens.
            returns:
              type: list[str]
            """
            return ["tok-a", "tok-b"]

    def fake_file_to_buffer(cls: type[ArxIO], filename: str) -> None:
        """
        title: Validate the requested source filename.
        parameters:
          cls:
            type: type[ArxIO]
          filename:
            type: str
        """
        assert filename == "sample.x"

    monkeypatch.setattr(main_module, "Lexer", DummyLexer)
    monkeypatch.setattr(
        ArxIO, "file_to_buffer", classmethod(fake_file_to_buffer)
    )
    app.show_tokens()
    out = capsys.readouterr().out
    assert "tok-a" in out
    assert "tok-b" in out

    class DummyIRShow:
        def translate(self, tree: object) -> str:
            """
            title: Return placeholder LLVM IR text.
            parameters:
              tree:
                type: object
            returns:
              type: str
            """
            return f"IR<{tree}>"

    monkeypatch.setattr(main_module, "ArxBuilder", DummyIRShow)
    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    app.show_llvm_ir()
    assert "IR<TREE>" in capsys.readouterr().out

    class DummyIRBuild:
        built_tree: object | None = None
        built_out: str | None = None
        built_link: bool | None = None
        built_link_mode: str | None = None

        def build(
            self,
            tree: object,
            output_file: str = "",
            link: bool = True,
            link_mode: str = "auto",
        ) -> None:
            """
            title: Record build arguments.
            parameters:
              tree:
                type: object
              output_file:
                type: str
              link:
                type: bool
              link_mode:
                type: str
            """
            DummyIRBuild.built_tree = tree
            DummyIRBuild.built_out = output_file
            DummyIRBuild.built_link = link
            DummyIRBuild.built_link_mode = link_mode

    monkeypatch.setattr(main_module, "ArxBuilder", DummyIRBuild)
    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    app.compile()
    assert DummyIRBuild.built_tree is not None
    assert DummyIRBuild.built_out == "out.o"
    assert DummyIRBuild.built_link is False
    assert DummyIRBuild.built_link_mode == "auto"


def test_arxmain_show_llvm_ir_uses_translate_modules_for_imports(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    title: show_llvm_ir should use IRx multi-module translation for imports.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      capsys:
        type: pytest.CaptureFixture[str]
    """
    app = main_module.ArxMain(input_files=["app.x"])
    module = astx.Module("app")
    module.nodes.append(irx_astx.ImportStmt([irx_astx.AliasExpr("lib.math")]))
    sentinel_root = object()
    sentinel_resolver = object()

    def fake_get_astx_tree() -> astx.AST:
        """
        title: Return a module containing imports.
        returns:
          type: astx.AST
        """
        return module

    def fake_build_multimodule_context(
        tree: astx.Module,
    ) -> tuple[object, object]:
        """
        title: Return a sentinel multi-module context.
        parameters:
          tree:
            type: astx.Module
        returns:
          type: tuple[object, object]
        """
        assert tree is module
        return sentinel_root, sentinel_resolver

    class DummyIRShow:
        def translate(self, tree: object) -> str:
            """
            title: Single-module translation should not be used here.
            parameters:
              tree:
                type: object
            returns:
              type: str
            """
            raise AssertionError(tree)

        def translate_modules(self, root: object, resolver: object) -> str:
            """
            title: Record multi-module translation inputs.
            parameters:
              root:
                type: object
              resolver:
                type: object
            returns:
              type: str
            """
            assert root is sentinel_root
            assert resolver is sentinel_resolver
            return "IR<MODULES>"

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    monkeypatch.setattr(
        app,
        "_build_multimodule_context",
        fake_build_multimodule_context,
    )
    monkeypatch.setattr(main_module, "ArxBuilder", DummyIRShow)

    app.show_llvm_ir()

    assert "IR<MODULES>" in capsys.readouterr().out


def test_arxmain_compile_uses_build_modules_for_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: compile should use IRx multi-module build for imports.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    app = main_module.ArxMain(input_files=["app.x"], output_file="out.o")
    module = astx.Module("app")
    module.nodes.append(irx_astx.ImportStmt([irx_astx.AliasExpr("lib.math")]))
    sentinel_root = object()
    sentinel_resolver = object()

    def fake_get_astx_tree() -> astx.AST:
        """
        title: Return a module containing imports.
        returns:
          type: astx.AST
        """
        return module

    def fake_build_multimodule_context(
        tree: astx.Module,
    ) -> tuple[object, object]:
        """
        title: Return a sentinel multi-module build context.
        parameters:
          tree:
            type: astx.Module
        returns:
          type: tuple[object, object]
        """
        assert tree is module
        return sentinel_root, sentinel_resolver

    class DummyIRBuild:
        built_root: object | None = None
        built_resolver: object | None = None
        built_out: str | None = None
        built_link: bool | None = None
        built_link_mode: str | None = None

        def build(self, tree: object, **kwargs: object) -> None:
            """
            title: Single-module build should not be used here.
            parameters:
              tree:
                type: object
              kwargs:
                type: object
                variadic: keyword
            """
            del kwargs
            raise AssertionError(tree)

        def build_modules(
            self,
            root: object,
            resolver: object,
            output_file: str = "",
            link: bool = True,
            link_mode: str = "auto",
        ) -> None:
            """
            title: Record multi-module build arguments.
            parameters:
              root:
                type: object
              resolver:
                type: object
              output_file:
                type: str
              link:
                type: bool
              link_mode:
                type: str
            """
            DummyIRBuild.built_root = root
            DummyIRBuild.built_resolver = resolver
            DummyIRBuild.built_out = output_file
            DummyIRBuild.built_link = link
            DummyIRBuild.built_link_mode = link_mode

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    monkeypatch.setattr(
        app,
        "_build_multimodule_context",
        fake_build_multimodule_context,
    )
    monkeypatch.setattr(main_module, "ArxBuilder", DummyIRBuild)

    app.compile()

    assert DummyIRBuild.built_root is sentinel_root
    assert DummyIRBuild.built_resolver is sentinel_resolver
    assert DummyIRBuild.built_out == "out.o"
    assert DummyIRBuild.built_link is False
    assert DummyIRBuild.built_link_mode == "auto"


def test_arxmain_compile_default_output_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test compile default output file resolution.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    app = main_module.ArxMain(input_files=["examples/print-star.x"])

    def fake_get_astx_tree() -> object:
        """
        title: Return a placeholder AST object.
        returns:
          type: object
        """
        return object()

    class DummyIRBuild:
        built_out: str | None = None
        built_link: bool | None = None
        built_link_mode: str | None = None

        def build(
            self,
            tree: object,
            output_file: str = "",
            link: bool = True,
            link_mode: str = "auto",
        ) -> None:
            """
            title: Record build arguments.
            parameters:
              tree:
                type: object
              output_file:
                type: str
              link:
                type: bool
              link_mode:
                type: str
            """
            del tree
            DummyIRBuild.built_out = output_file
            DummyIRBuild.built_link = link
            DummyIRBuild.built_link_mode = link_mode

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    monkeypatch.setattr(main_module, "ArxBuilder", DummyIRBuild)

    app.compile()

    assert DummyIRBuild.built_out == "print-star"
    assert DummyIRBuild.built_link is False
    assert DummyIRBuild.built_link_mode == "auto"
    assert app.output_file == "print-star"


def test_arxmain_compile_links_when_main_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test compile links output when module has main.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    app = main_module.ArxMain(input_files=["examples/fibonacci.x"])

    def fake_get_astx_tree() -> object:
        """
        title: Return a placeholder AST object.
        returns:
          type: object
        """
        return object()

    class DummyIRBuild:
        built_link: bool | None = None
        built_link_mode: str | None = None

        def build(
            self,
            tree: object,
            output_file: str = "",
            link: bool = True,
            link_mode: str = "auto",
        ) -> None:
            """
            title: Record build arguments.
            parameters:
              tree:
                type: object
              output_file:
                type: str
              link:
                type: bool
              link_mode:
                type: str
            """
            del tree, output_file
            DummyIRBuild.built_link = link
            DummyIRBuild.built_link_mode = link_mode

    def fake_has_main_entry(node: object) -> bool:
        """
        title: Pretend that the AST contains main.
        parameters:
          node:
            type: object
        returns:
          type: bool
        """
        del node
        return True

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    monkeypatch.setattr(app, "_has_main_entry", fake_has_main_entry)
    monkeypatch.setattr(main_module, "ArxBuilder", DummyIRBuild)

    app.compile()

    assert DummyIRBuild.built_link is True
    assert DummyIRBuild.built_link_mode == "auto"


def test_arxmain_run_requires_executable_for_run_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Test run flag fails when compile does not produce executable.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    app = main_module.ArxMain()

    def fake_compile() -> bool:
        """
        title: Pretend that compile produced no executable.
        returns:
          type: bool
        """
        return False

    monkeypatch.setattr(app, "compile", fake_compile)

    with pytest.raises(ValueError, match="--run"):
        app.run(run=True)


def test_arxmain_run_binary_uses_absolute_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    title: Test run_binary executes resolved absolute path.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    app = main_module.ArxMain(output_file="print-star")

    recorded: dict[str, object] = {}

    def fake_subprocess_run(
        cmd: list[str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        """
        title: Record subprocess execution arguments.
        parameters:
          cmd:
            type: list[str]
          check:
            type: bool
        returns:
          type: subprocess.CompletedProcess[str]
        """
        recorded["cmd"] = cmd
        recorded["check"] = check
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    app.run_binary()

    assert recorded["check"] is False
    assert recorded["cmd"] == [str(tmp_path / "print-star")]


def test_arxmain_run_binary_nonzero_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    title: Test run_binary exits with child return code on failure.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      tmp_path:
        type: Path
    """
    app = main_module.ArxMain(output_file="print-star")

    def fake_subprocess_run(
        cmd: list[str], check: bool
    ) -> subprocess.CompletedProcess[str]:
        """
        title: Return a failing subprocess result.
        parameters:
          cmd:
            type: list[str]
          check:
            type: bool
        returns:
          type: subprocess.CompletedProcess[str]
        """
        del cmd
        del check
        return subprocess.CompletedProcess(["print-star"], 112)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    with pytest.raises(SystemExit, match="112"):
        app.run_binary()


def test_arxmain_run_shell_not_implemented() -> None:
    """
    title: Test run_shell exception path.
    """
    app = main_module.ArxMain()
    with pytest.raises(Exception, match="not implemented"):
        app.run_shell()


def _write_resolver_project(
    project_root: Path,
    name: str,
    dependencies: tuple[str, ...] = (),
) -> None:
    """
    title: Write a minimal project manifest for resolver tests.
    parameters:
      project_root:
        type: Path
      name:
        type: str
      dependencies:
        type: tuple[str, Ellipsis]
    """
    dependency_lines = ""
    if dependencies:
        dependency_values = ", ".join(
            f'"{dependency}"' for dependency in dependencies
        )
        dependency_lines = f"dependencies = [{dependency_values}]\n"

    (project_root / ".arxproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
        f'{dependency_lines}[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )


def _write_installed_arx_distribution(
    site_packages: Path,
    distribution_name: str,
    module_name: str,
    files: dict[str, str],
    requires: tuple[str, ...] = (),
) -> Path:
    """
    title: Write a minimal installed Arx distribution fixture.
    parameters:
      site_packages:
        type: Path
      distribution_name:
        type: str
      module_name:
        type: str
      files:
        type: dict[str, str]
      requires:
        type: tuple[str, Ellipsis]
    returns:
      type: Path
    """
    package_dir = site_packages / module_name
    package_dir.mkdir(parents=True)
    manifest_path = package_dir / ".arxproject.toml"
    manifest_path.write_text(
        f'[project]\nname = "{distribution_name}"\nversion = "0.1.0"\n'
        f'[build]\npackage = "{module_name}"\n\n',
        encoding="utf-8",
    )

    record_paths = [manifest_path.relative_to(site_packages)]
    for relative_name, content in files.items():
        file_path = package_dir / relative_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        record_paths.append(file_path.relative_to(site_packages))

    dist_info_name = distribution_name.replace("-", "_")
    dist_info = site_packages / f"{dist_info_name}-0.1.dist-info"
    dist_info.mkdir()
    metadata_path = dist_info / "METADATA"
    requires_lines = "".join(
        f"Requires-Dist: {requirement}\n" for requirement in requires
    )
    metadata_path.write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {distribution_name}\n"
        "Version: 0.1.0\n"
        f"{requires_lines}",
        encoding="utf-8",
    )
    record_path = dist_info / "RECORD"
    record_paths.extend(
        (
            metadata_path.relative_to(site_packages),
            record_path.relative_to(site_packages),
        )
    )
    record_path.write_text(
        "".join(f"{path.as_posix()},,\n" for path in record_paths),
        encoding="utf-8",
    )
    return package_dir


def _write_installed_arx_src_distribution(
    site_packages: Path,
    distribution_name: str,
    project_dir_name: str,
    module_name: str,
    files: dict[str, str],
    requires: tuple[str, ...] = (),
) -> Path:
    """
    title: Write an installed Arx distribution with a src package layout.
    parameters:
      site_packages:
        type: Path
      distribution_name:
        type: str
      project_dir_name:
        type: str
      module_name:
        type: str
      files:
        type: dict[str, str]
      requires:
        type: tuple[str, Ellipsis]
    returns:
      type: Path
    """
    project_dir = site_packages / project_dir_name
    package_dir = project_dir / "src" / module_name
    package_dir.mkdir(parents=True)
    manifest_path = project_dir / ".arxproject.toml"
    manifest_path.write_text(
        f'[project]\nname = "{distribution_name}"\nversion = "0.1.0"\n'
        f'[build]\nsrc_dir = "src"\npackage = "{module_name}"\n\n',
        encoding="utf-8",
    )

    record_paths = [manifest_path.relative_to(site_packages)]
    for relative_name, content in files.items():
        file_path = package_dir / relative_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        record_paths.append(file_path.relative_to(site_packages))

    dist_info_name = distribution_name.replace("-", "_")
    dist_info = site_packages / f"{dist_info_name}-0.1.dist-info"
    dist_info.mkdir()
    metadata_path = dist_info / "METADATA"
    requires_lines = "".join(
        f"Requires-Dist: {requirement}\n" for requirement in requires
    )
    metadata_path.write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {distribution_name}\n"
        "Version: 0.1.0\n"
        f"{requires_lines}",
        encoding="utf-8",
    )
    record_path = dist_info / "RECORD"
    record_paths.extend(
        (
            metadata_path.relative_to(site_packages),
            record_path.relative_to(site_packages),
        )
    )
    record_path.write_text(
        "".join(f"{path.as_posix()},,\n" for path in record_paths),
        encoding="utf-8",
    )
    return package_dir


def _write_python_only_distribution(
    site_packages: Path,
    distribution_name: str,
) -> None:
    """
    title: Write a minimal non-Arx installed distribution fixture.
    parameters:
      site_packages:
        type: Path
      distribution_name:
        type: str
    """
    dist_info_name = distribution_name.replace("-", "_")
    dist_info = site_packages / f"{dist_info_name}-0.1.dist-info"
    dist_info.mkdir(parents=True)
    metadata_path = dist_info / "METADATA"
    metadata_path.write_text(
        f"Metadata-Version: 2.1\nName: {distribution_name}\nVersion: 0.1.0\n",
        encoding="utf-8",
    )
    record_path = dist_info / "RECORD"
    record_path.write_text(
        f"{metadata_path.relative_to(site_packages).as_posix()},,\n"
        f"{record_path.relative_to(site_packages).as_posix()},,\n",
        encoding="utf-8",
    )


def test_file_import_resolver_rejects_ambiguous_package_and_module_paths(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Resolver rejects specifiers that match both pkg.x and pkg/__init__.x.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "ambiguous"
    src_dir = project_root / "src"
    package_dir = src_dir / "samplepkg"
    package_dir.mkdir(parents=True)

    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    (src_dir / "samplepkg.x").write_text(
        "fn flat() -> i32:\n  return 1\n",
        encoding="utf-8",
    )
    (package_dir / "__init__.x").write_text(
        "fn packaged() -> i32:\n  return 2\n",
        encoding="utf-8",
    )

    resolver = main_module.FileImportResolver(
        (str(package_dir / "__init__.x"),)
    )

    with pytest.raises(
        LookupError,
        match="ambiguous module specifier 'samplepkg'",
    ):
        resolver._resolve_module_file("samplepkg")


def test_file_import_resolver_honors_build_src_dir(tmp_path: Path) -> None:
    """
    title: FileImportResolver consults [build].src_dir from .arxproject.toml.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "mypkg"
    src_dir = project_root / "sources"
    tests_dir = project_root / "tests"
    src_dir.mkdir(parents=True)
    tests_dir.mkdir()

    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "mypkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "mypkg"\n'
        '[build]\nsrc_dir = "sources"\n\n',
        encoding="utf-8",
    )
    (src_dir / "mypkg" / "__init__.x").parent.mkdir(
        parents=True, exist_ok=True
    )
    (src_dir / "mypkg" / "__init__.x").write_text(
        "fn hello() -> i32:\n  return 1\n",
        encoding="utf-8",
    )
    test_file = tests_dir / "test_mypkg.x"
    test_file.write_text(
        "fn test_noop() -> none:\n  return\n", encoding="utf-8"
    )

    resolver = main_module.FileImportResolver((str(test_file),))
    roots = resolver._candidate_roots()

    assert src_dir.resolve() in roots
    resolved = resolver._resolve_module_file("mypkg")
    assert resolved == (src_dir / "mypkg" / "__init__.x").resolve()


def test_file_import_resolver_resolves_direct_installed_arx_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: FileImportResolver resolves a direct installed Arx dependency.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("import sum2 from local_lib.stats\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-local-lib",),
    )

    site_packages = tmp_path / "site-packages"
    package_dir = _write_installed_arx_distribution(
        site_packages,
        "arx-test-local-lib",
        "local_lib",
        {
            "__init__.x": "",
            "stats.x": "fn sum2() -> i32:\n  return 2\n",
        },
    )

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    import_node = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("sum2")],
        module="local_lib.stats",
        level=0,
    )
    parsed = resolver("main", import_node, "local_lib.stats")

    assert parsed.key == "local_lib.stats"
    assert parsed.origin is not None
    assert Path(parsed.origin) == (package_dir / "stats.x").resolve()


def test_file_import_resolver_resolves_transitive_installed_arx_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: FileImportResolver resolves transitive installed Arx dependencies.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("import helper from project_b.tools\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-project-a",),
    )

    site_packages = tmp_path / "site-packages"
    _write_installed_arx_distribution(
        site_packages,
        "arx-test-project-a",
        "project_a",
        {"__init__.x": "import helper from project_b.tools\n"},
        requires=("arx-test-project-b >= 0.1",),
    )
    package_b_dir = _write_installed_arx_distribution(
        site_packages,
        "arx-test-project-b",
        "project_b",
        {
            "__init__.x": "",
            "tools.x": "fn helper() -> i32:\n  return 4\n",
        },
    )

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    resolved = resolver._resolve_module_file("project_b.tools")

    assert resolved == (package_b_dir / "tools.x").resolve()


def test_file_import_resolver_skips_inactive_transitive_requirements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Inactive metadata markers are not indexed as Arx dependencies.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("fn main() -> i32:\n  return 0\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-project-a",),
    )

    site_packages = tmp_path / "site-packages"
    _write_installed_arx_distribution(
        site_packages,
        "arx-test-project-a",
        "project_a",
        {"__init__.x": ""},
        requires=(
            'arx-optional-lib; extra == "dev"',
            'arx-platform-lib; sys_platform == "never-matches"',
        ),
    )
    _write_installed_arx_distribution(
        site_packages,
        "arx-optional-lib",
        "optional_lib",
        {"__init__.x": "", "tools.x": "fn helper() -> i32:\n  return 1\n"},
    )
    _write_installed_arx_distribution(
        site_packages,
        "arx-platform-lib",
        "platform_lib",
        {"__init__.x": "", "tools.x": "fn helper() -> i32:\n  return 2\n"},
    )

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    with pytest.raises(LookupError, match="optional_lib"):
        resolver._resolve_module_file("optional_lib.tools")
    with pytest.raises(LookupError, match="platform_lib"):
        resolver._resolve_module_file("platform_lib.tools")


def test_file_import_resolver_honors_installed_package_src_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Installed Arx package discovery honors build src_dir and package.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("import sum2 from local_lib.stats\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-src-layout-lib",),
    )

    site_packages = tmp_path / "site-packages"
    package_dir = _write_installed_arx_src_distribution(
        site_packages,
        "arx-test-src-layout-lib",
        "src_layout_project",
        "local_lib",
        {
            "__init__.x": "",
            "stats.x": "fn sum2() -> i32:\n  return 2\n",
        },
    )

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    resolved = resolver._resolve_module_file("local_lib.stats")

    assert resolved == (package_dir / "stats.x").resolve()


def test_file_import_resolver_local_source_shadows_installed_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Local project source keeps precedence over installed packages.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    local_package = src_dir / "local_lib"
    local_package.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("import sum2 from local_lib.stats\n", encoding="utf-8")
    local_stats = local_package / "stats.x"
    local_stats.write_text("fn sum2() -> i32:\n  return 1\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-shadow-lib",),
    )

    site_packages = tmp_path / "site-packages"
    _write_installed_arx_distribution(
        site_packages,
        "arx-test-shadow-lib",
        "local_lib",
        {
            "__init__.x": "",
            "stats.x": "fn sum2() -> i32:\n  return 2\n",
        },
    )

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    resolved = resolver._resolve_module_file("local_lib.stats")

    assert resolved == local_stats.resolve()


def test_file_import_resolver_ignores_python_only_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Python-only installed dependencies are not Arx import roots.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("fn main() -> i32:\n  return 0\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-python-only",),
    )

    site_packages = tmp_path / "site-packages"
    _write_python_only_distribution(site_packages, "arx-test-python-only")

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    with pytest.raises(LookupError, match="python_only"):
        resolver._resolve_module_file("python_only")


def test_file_import_resolver_reports_missing_installed_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Missing declared installed dependencies get a clear error.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text(
        "import helper from arx_missing_lib.tools\n", encoding="utf-8"
    )
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-missing-lib",),
    )

    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    with pytest.raises(
        LookupError,
        match="declared Arx dependency 'arx-missing-lib' is not installed",
    ):
        resolver._resolve_module_file("arx_missing_lib.tools")


def test_file_import_resolver_rejects_ambiguous_installed_module_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Installed packages reject ambiguous module and package paths.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("import value from local_lib.mod\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-ambiguous-lib",),
    )

    site_packages = tmp_path / "site-packages"
    _write_installed_arx_distribution(
        site_packages,
        "arx-test-ambiguous-lib",
        "local_lib",
        {
            "__init__.x": "",
            "mod.x": "fn value() -> i32:\n  return 1\n",
            "mod/__init__.x": "fn value() -> i32:\n  return 2\n",
        },
    )

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    with pytest.raises(
        LookupError,
        match=r"ambiguous module specifier 'local_lib\.mod'",
    ):
        resolver._resolve_module_file("local_lib.mod")


def test_file_import_resolver_keeps_reserved_namespaces_bundled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: Installed packages do not shadow reserved compiler namespaces.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    project_root = tmp_path / "app"
    src_dir = project_root / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "main.x"
    source.write_text("import math from stdlib\n", encoding="utf-8")
    _write_resolver_project(
        project_root,
        "app",
        dependencies=("arx-test-stdlib-shadow",),
    )

    site_packages = tmp_path / "site-packages"
    _write_installed_arx_distribution(
        site_packages,
        "arx-test-stdlib-shadow",
        "stdlib",
        {
            "__init__.x": "",
            "math.x": "fn square(value: i32) -> i32:\n  return value\n",
        },
    )

    monkeypatch.syspath_prepend(str(site_packages))
    monkeypatch.chdir(project_root)

    resolver = main_module.FileImportResolver((str(source),))
    resolved = resolver._resolve_module_file("stdlib.math")

    assert (
        resolved
        == (main_module.get_bundled_stdlib_root() / "math.x").resolve()
    )


def test_file_import_resolver_supports_nested_relative_imports(
    tmp_path: Path,
) -> None:
    """
    title: >-
      Nested package modules support same-level and parent relative imports.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "samplepkg"
    src_dir = project_root / "src"
    package_root = src_dir / "samplepkg"
    shapes_dir = package_root / "shapes"
    shared_dir = package_root / "shared"
    shapes_dir.mkdir(parents=True)
    shared_dir.mkdir(parents=True)

    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    (package_root / "__init__.x").write_text(
        "import area from .shapes.area\n",
        encoding="utf-8",
    )
    (shapes_dir / "mod.x").write_text(
        "import helper from .sibling\nimport clamp from ..shared.util\n",
        encoding="utf-8",
    )
    (shapes_dir / "sibling.x").write_text(
        "fn helper() -> i32:\n  return 1\n",
        encoding="utf-8",
    )
    (shared_dir / "util.x").write_text(
        "fn clamp() -> i32:\n  return 2\n",
        encoding="utf-8",
    )

    resolver = main_module.FileImportResolver(
        (str(package_root / "__init__.x"),)
    )

    sibling_import = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("helper")],
        module="sibling",
        level=1,
    )
    resolved_sibling = resolver(
        "samplepkg.shapes.mod",
        sibling_import,
        ".sibling",
    )
    assert resolved_sibling.key == "samplepkg.shapes.sibling"
    assert resolved_sibling.origin is not None
    assert (
        Path(resolved_sibling.origin) == (shapes_dir / "sibling.x").resolve()
    )

    parent_import = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("clamp")],
        module="shared.util",
        level=2,
    )
    resolved_parent = resolver(
        "samplepkg.shapes.mod",
        parent_import,
        "..shared.util",
    )
    assert resolved_parent.key == "samplepkg.shared.util"
    assert resolved_parent.origin is not None
    assert Path(resolved_parent.origin) == (shared_dir / "util.x").resolve()


def test_file_import_resolver_rejects_top_level_parent_relative_import(
    tmp_path: Path,
) -> None:
    """
    title: Top-level package modules cannot climb beyond the package root.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "samplepkg"
    src_dir = project_root / "src"
    package_dir = src_dir / "samplepkg"
    package_dir.mkdir(parents=True)

    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    (package_dir / "mod.x").write_text(
        "import helper from ..shared.util\n",
        encoding="utf-8",
    )

    resolver = main_module.FileImportResolver((str(package_dir / "mod.x"),))
    parent_import = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("helper")],
        module="shared.util",
        level=2,
    )

    with pytest.raises(LookupError, match="top-level package"):
        resolver("samplepkg.mod", parent_import, "..shared.util")


def test_file_import_resolver_normalizes_relative_imports(
    tmp_path: Path,
) -> None:
    """
    title: FileImportResolver normalizes relative imports against package keys.
    parameters:
      tmp_path:
        type: Path
    """
    project_root = tmp_path / "samplepkg"
    src_dir = project_root / "src"
    package_dir = src_dir / "samplepkg"
    package_dir.mkdir(parents=True)

    (project_root / ".arxproject.toml").write_text(
        '[project]\nname = "samplepkg"\nversion = "0.1.0"\n'
        '[environment]\nkind = "conda"\nname = "samplepkg"\n'
        '[build]\nsrc_dir = "src"\n\n',
        encoding="utf-8",
    )
    (package_dir / "__init__.x").write_text(
        "import helper from .core\n",
        encoding="utf-8",
    )
    (package_dir / "core.x").write_text(
        "import sum2 from .stats\nfn helper() -> i32:\n  return 1\n",
        encoding="utf-8",
    )
    (package_dir / "stats.x").write_text(
        "fn sum2() -> i32:\n  return 2\n",
        encoding="utf-8",
    )

    resolver = main_module.FileImportResolver(
        (str(package_dir / "__init__.x"),)
    )

    relative_core = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("helper")],
        module="core",
        level=1,
    )
    parsed_core = resolver("samplepkg", relative_core, ".core")
    assert parsed_core.key == "samplepkg.core"
    assert parsed_core.origin is not None
    assert Path(parsed_core.origin) == (package_dir / "core.x").resolve()

    relative_stats = irx_astx.ImportFromStmt(
        [irx_astx.AliasExpr("sum2")],
        module="stats",
        level=1,
    )
    parsed_stats = resolver("samplepkg.core", relative_stats, ".stats")
    assert parsed_stats.key == "samplepkg.stats"
    assert parsed_stats.origin is not None
    assert Path(parsed_stats.origin) == (package_dir / "stats.x").resolve()

    with pytest.raises(LookupError, match="top-level package"):
        resolver("samplepkg.core", relative_stats, "..stats")
