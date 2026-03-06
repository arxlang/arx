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
import astx
import pytest

from arx import __version__, builtins
from arx.docstrings import validate_docstring
from arx.exceptions import CodeGenException, ParserException
from arx.io import ArxBuffer, ArxFile, ArxIO
from irx import system


def test_builtins_helpers() -> None:
    """
    title: Test builtins helper functions.
    """
    assert builtins.is_builtin("cast")
    assert builtins.is_builtin("print")
    assert not builtins.is_builtin("custom_fn")

    cast_node = builtins.build_cast(astx.LiteralInt32(1), astx.Float32())
    print_node = builtins.build_print(astx.LiteralString("hello"))
    assert isinstance(cast_node, system.Cast)
    assert isinstance(print_node, system.PrintExpr)


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
    sample.write_text("fn main():\n  return 1\n", encoding="utf-8")
    ArxIO.file_to_buffer(str(sample))
    assert "fn main()" in ArxIO.buffer.buffer

    calls: dict[str, str] = {}

    def fake_file_to_buffer(cls: type[ArxIO], filename: str) -> None:
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
        ]
    )

    assert args.input_files == ["examples/sum.x"]
    assert args.output_file == "out.o"
    assert args.is_lib is True
    assert args.show_tokens is True
    assert args.run is False


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
            return Namespace(
                input_files=[],
                version=True,
                output_file="",
                is_lib=False,
                show_ast=False,
                show_tokens=False,
                show_llvm_ir=False,
                shell=False,
                run=False,
            )

    called: dict[str, bool] = {"version": False}

    def fake_show_version() -> None:
        called["version"] = True

    def fake_get_args() -> DummyParser:
        return DummyParser()

    monkeypatch.setattr(cli_module, "get_args", fake_get_args)
    monkeypatch.setattr(cli_module, "show_version", fake_show_version)

    cli_module.app()
    assert called["version"] is True


def test_cli_app_run_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    title: Test CLI app run branch.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    class DummyParser:
        def parse_args(self) -> Namespace:
            return Namespace(
                input_files=["a.x"],
                version=False,
                output_file="out.o",
                is_lib=True,
                show_ast=False,
                show_tokens=True,
                show_llvm_ir=False,
                shell=False,
                run=False,
            )

    class DummyMain:
        called_kwargs: dict[str, object] = {}

        def run(self, **kwargs: object) -> None:
            DummyMain.called_kwargs = kwargs

    def fake_get_args() -> DummyParser:
        return DummyParser()

    monkeypatch.setattr(cli_module, "get_args", fake_get_args)
    monkeypatch.setattr(cli_module, "ArxMain", DummyMain)

    cli_module.app()
    assert DummyMain.called_kwargs["input_files"] == ["a.x"]
    assert DummyMain.called_kwargs["show_tokens"] is True


def test_cli_app_run_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    title: Test CLI app run alias dispatch.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """

    class DummyParser:
        def parse_args(self) -> Namespace:
            return Namespace(
                input_files=["run", "prog.x"],
                version=False,
                output_file="",
                is_lib=True,
                show_ast=False,
                show_tokens=False,
                show_llvm_ir=False,
                shell=False,
                run=False,
            )

    class DummyMain:
        called_kwargs: dict[str, object] = {}

        def run(self, **kwargs: object) -> None:
            DummyMain.called_kwargs = kwargs

    def fake_get_args() -> DummyParser:
        return DummyParser()

    monkeypatch.setattr(cli_module, "get_args", fake_get_args)
    monkeypatch.setattr(cli_module, "ArxMain", DummyMain)

    cli_module.app()
    assert DummyMain.called_kwargs["input_files"] == ["prog.x"]
    assert DummyMain.called_kwargs["run"] is True


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
        called["app"] = True

    monkeypatch.setattr(cli_module, "app", fake_app)
    runpy.run_module("arx.__main__", run_name="__main__")
    assert called["app"] is True


def test_main_module_name_helper() -> None:
    """
    title: Test module-name extraction helper.
    """
    assert (
        main_module.get_module_name_from_file_path(
            "/tmp/project/examples/sample.x"
        )
        == "sample"
    )


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
            return ["TOKENS"]

    class DummyParser:
        def parse(
            self, tokens: list[str], module_name: str = "main"
        ) -> astx.Module:
            assert tokens == ["TOKENS"]
            parsed_modules.append(module_name)
            return astx.Module(module_name)

    def fake_file_to_buffer(cls: type[ArxIO], filename: str) -> None:
        loaded_files.append(filename)

    monkeypatch.setattr(main_module, "Lexer", DummyLexer)
    monkeypatch.setattr(main_module, "Parser", DummyParser)
    monkeypatch.setattr(
        ArxIO, "file_to_buffer", classmethod(fake_file_to_buffer)
    )

    app = main_module.ArxMain(
        input_files=["/tmp/demo/a.x", "/tmp/demo/b.x"],
        output_file="out.o",
    )
    tree = app._get_astx()

    assert loaded_files == ["/tmp/demo/a.x", "/tmp/demo/b.x"]
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
        called["ast"] = True

    def fake_show_tokens() -> None:
        called["tokens"] = True

    def fake_show_llvm_ir() -> None:
        called["llvm"] = True

    def fake_run_shell() -> None:
        called["shell"] = True

    def fake_run_binary() -> None:
        called["run_binary"] = True

    monkeypatch.setattr(app, "show_ast", fake_show_ast)
    monkeypatch.setattr(app, "show_tokens", fake_show_tokens)
    monkeypatch.setattr(app, "show_llvm_ir", fake_show_llvm_ir)
    monkeypatch.setattr(app, "run_shell", fake_run_shell)
    monkeypatch.setattr(app, "run_binary", fake_run_binary)

    compiled: dict[str, bool] = {"called": False}

    def fake_compile() -> bool:
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
            return "TREE"

    def fake_get_astx_tree() -> ReprTree:
        return ReprTree()

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    app.show_ast()
    assert "TREE" in capsys.readouterr().out

    class ReprFailTree:
        def __repr__(self) -> str:
            raise RuntimeError("repr failure")

        def __str__(self) -> str:
            return "TREE_FALLBACK"

    def fake_get_astx_tree_fallback() -> ReprFailTree:
        return ReprFailTree()

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree_fallback)
    app.show_ast()
    assert "TREE_FALLBACK" in capsys.readouterr().out

    class DummyLexer:
        def lex(self) -> list[str]:
            return ["tok-a", "tok-b"]

    def fake_file_to_buffer(cls: type[ArxIO], filename: str) -> None:
        assert filename == "sample.x"

    monkeypatch.setattr(main_module, "Lexer", DummyLexer)
    monkeypatch.setattr(
        ArxIO, "file_to_buffer", classmethod(fake_file_to_buffer)
    )
    app.show_tokens()
    out = capsys.readouterr().out
    assert "tok-a" in out
    assert "tok-b" in out

    class DummyTranslator:
        def translate(self, tree: object) -> str:
            return f"IR<{tree}>"

    class DummyIRShow:
        def __init__(self) -> None:
            self.translator = DummyTranslator()

    monkeypatch.setattr(main_module, "LLVMLiteIR", DummyIRShow)
    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    app.show_llvm_ir()
    assert "IR<TREE>" in capsys.readouterr().out

    class DummyIRBuild:
        built_tree: object | None = None
        built_out: str | None = None
        built_link: bool | None = None

        def build(
            self,
            tree: object,
            output_file: str = "",
            link: bool = True,
        ) -> None:
            DummyIRBuild.built_tree = tree
            DummyIRBuild.built_out = output_file
            DummyIRBuild.built_link = link

    monkeypatch.setattr(main_module, "LLVMLiteIR", DummyIRBuild)
    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    app.compile()
    assert DummyIRBuild.built_tree is not None
    assert DummyIRBuild.built_out == "out.o"
    assert DummyIRBuild.built_link is False


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
        return object()

    class DummyIRBuild:
        built_out: str | None = None
        built_link: bool | None = None

        def build(
            self,
            tree: object,
            output_file: str = "",
            link: bool = True,
        ) -> None:
            del tree
            DummyIRBuild.built_out = output_file
            DummyIRBuild.built_link = link

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    monkeypatch.setattr(main_module, "LLVMLiteIR", DummyIRBuild)

    app.compile()

    assert DummyIRBuild.built_out == "print-star"
    assert DummyIRBuild.built_link is False
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
        return object()

    class DummyIRBuild:
        built_link: bool | None = None

        def build(
            self,
            tree: object,
            output_file: str = "",
            link: bool = True,
        ) -> None:
            del tree, output_file
            DummyIRBuild.built_link = link

    def fake_has_main_entry(node: object) -> bool:
        del node
        return True

    monkeypatch.setattr(app, "_get_astx", fake_get_astx_tree)
    monkeypatch.setattr(app, "_has_main_entry", fake_has_main_entry)
    monkeypatch.setattr(main_module, "LLVMLiteIR", DummyIRBuild)

    app.compile()

    assert DummyIRBuild.built_link is True


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
