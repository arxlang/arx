"""
title: Restricted open builtin parser, semantics, and native execution.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from pathlib import Path

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.main import ArxMain
from arx.parser import Parser
from irx.analysis import SemanticError
from irx.builder.runtime.errors import parse_runtime_failure_output
from llvmlite import binding as llvm

from .file_support import analyze_arx as analyze


def parse_module(body: str, declarations: str = "") -> astx.Module:
    """
    title: Parse a documented module with a main body.
    parameters:
      body:
        type: str
      declarations:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(
        "```\ntitle: File I/O regression\n```\n"
        + declarations
        + "\nfn main() -> i32:\n"
        + "\n".join("  " + line for line in body.splitlines())
        + "\n  return 0\n"
    )
    return Parser().parse(Lexer().lex())


def execute(
    tmp_path: Path, body: str, declarations: str = ""
) -> subprocess.CompletedProcess[str]:
    """
    title: Build and execute an isolated native file-I/O test.
    parameters:
      tmp_path:
        type: Path
      body:
        type: str
      declarations:
        type: str
    returns:
      type: subprocess.CompletedProcess[str]
    """
    if shutil.which("clang") is None:
        pytest.skip("clang is required for native open execution")
    module = parse_module(body, declarations)
    builder = ArxBuilder()
    llvm.parse_assembly(builder.translate(module)).verify()
    executable = tmp_path / "program"
    builder.build(module, str(executable))
    return subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        '"data.txt"',
        'file="data.txt"',
        '"data.txt", "r", -1, none, none, none, true, none',
        'mode="rt", file="data.txt", encoding="utf-8", errors="strict",',
    ],
)
def test_open_parameters_and_translation(arguments: str) -> None:
    """
    title: Positional/default/keyword forms share resolved file metadata.
    parameters:
      arguments:
        type: str
    """
    module = parse_module(f"var f: file = open({arguments})\nf.close()")
    llvm.parse_assembly(ArxBuilder().translate(module)).verify()


@pytest.mark.parametrize(
    "arguments, message",
    [
        ("", "requires a file path"),
        ("1", "requires a string"),
        ('"x", "wb"', "supports only"),
        ('"x", buffering=0', "buffering"),
        ('"x", encoding="latin-1"', "encoding"),
        ('"x", errors="ignore"', "errors"),
        ('"x", newline=""', "newline"),
        ('"x", closefd=false', "closefd"),
        ('"x", opener=1', "opener"),
        ('"x", file="y"', "duplicate"),
        ('"x", other=1', "unknown"),
        ('"x", mode="r", mode="w"', "duplicate"),
        ('"x", "r", -1, none, none, none, true, none, none', "eight"),
    ],
)
def test_open_rejects_unsupported_arguments(
    arguments: str, message: str
) -> None:
    """
    title: Invalid arguments fail before native filesystem effects.
    parameters:
      arguments:
        type: str
      message:
        type: str
    """
    with pytest.raises(SemanticError, match=message):
        analyze(parse_module(f"var f: file = open({arguments})"))


@pytest.mark.parametrize(
    "call",
    [
        'open(file="x", "r")',
    ],
)
def test_open_keyword_syntax_restrictions(call: str) -> None:
    """
    title: Keywords do not become assignments or generic call syntax.
    parameters:
      call:
        type: str
    """
    with pytest.raises(ParserException):
        parse_module(call)


def test_public_file_containers_remain_unsupported() -> None:
    """
    title: The public class retains the existing class-container boundary.
    """
    with pytest.raises((SemanticError, ParserException)):
        analyze(parse_module("var f: list[file]"))


def test_open_shadowing() -> None:
    """
    title: User functions and non-callable locals take precedence over open.
    """
    declarations = "fn open(value: i32) -> i32:\n  return value\n"
    module = parse_module("assert open(7) == 7", declarations)
    assert "irx_file_open" not in ArxBuilder().translate(module)
    with pytest.raises(SemanticError, match="unknown argument"):
        analyze(parse_module("open(file=7)", declarations))
    with pytest.raises(SemanticError, match="does not resolve to a function"):
        analyze(parse_module('var open: i32 = 1\nopen("x")'))


@pytest.mark.parametrize("factory", ["open", "File"])
def test_open_native_roundtrip_and_cleanup(
    tmp_path: Path, factory: str
) -> None:
    """
    title: Native text counts, independent reads, append, and cleanup.
    parameters:
      tmp_path:
        type: Path
      factory:
        type: str
    """
    result = execute(
        tmp_path,
        """var f: file = open("data.txt", "wt")
assert f.write("hé😀") == 3
f.flush()
f.close()
f.close()
var appended: file = open("data.txt", "a")
appended.write("!\\n")
appended.close()
var input: file = open("data.txt")
var data: str = input.read()
assert input.read() == ""
input.close()
assert data == "hé😀!\\n"
open("discarded.txt", "w").write("temporary")
assert open("discarded.txt").read() == "temporary"
var automatic: file = open("automatic.txt", "w")
automatic.write("flushed on return")""".replace("open(", factory + "("),
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data.txt").read_text() == "hé😀!\n"
    assert (tmp_path / "automatic.txt").read_text() == "flushed on return"
    assert (tmp_path / "discarded.txt").is_file()


@pytest.mark.parametrize("content", [b"x\r\ny\rz\n", b"", b"a" * 5000])
def test_open_native_reads(tmp_path: Path, content: bytes) -> None:
    """
    title: Compiled reads handle newlines, growth, and empty data.
    parameters:
      tmp_path:
        type: Path
      content:
        type: bytes
    """
    (tmp_path / "data.txt").write_bytes(content)
    expected = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n").decode()
    result = execute(
        tmp_path,
        'var f: file = open("data.txt")\n'
        f"assert f.read() == {json.dumps(expected)}",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("content", [b"a\0b", b"\xff", b"\xe2\x82"])
def test_open_native_bad_text(tmp_path: Path, content: bytes) -> None:
    """
    title: Runtime read failures are structured and never publish bad strings.
    parameters:
      tmp_path:
        type: Path
      content:
        type: bytes
    """
    (tmp_path / "bad").write_bytes(content)
    result = execute(tmp_path, 'var f: file = open("bad")\nf.read()')
    failure = parse_runtime_failure_output(result.stderr)
    assert result.returncode == 1
    assert failure is not None and failure.code == "ARX-RUNTIME-FILE-001"


@pytest.mark.parametrize("factory", ["open", "File"])
def test_open_runtime_mode_is_checked_before_truncation(
    tmp_path: Path,
    factory: str,
) -> None:
    """
    title: Runtime values are validated before calling fopen.
    parameters:
      tmp_path:
        type: Path
      factory:
        type: str
    """
    (tmp_path / "keep").write_bytes(b"unchanged")
    result = execute(
        tmp_path,
        f'var mode: str = "wb"\nvar f: file = {factory}("keep", mode)',
    )
    assert result.returncode == 1
    assert (tmp_path / "keep").read_bytes() == b"unchanged"


@pytest.mark.parametrize("arguments", ['"missing"', '"folder", "w"'])
def test_open_filesystem_failures(tmp_path: Path, arguments: str) -> None:
    """
    title: Missing paths and non-writable targets report checked open errors.
    parameters:
      tmp_path:
        type: Path
      arguments:
        type: str
    """
    (tmp_path / "folder").mkdir()
    result = execute(tmp_path, f"var f: file = open({arguments})")
    failure = parse_runtime_failure_output(result.stderr)
    assert result.returncode == 1
    assert failure is not None and failure.code == "ARX-RUNTIME-FILE-001"
    assert "open failed" in result.stderr


@pytest.mark.parametrize("factory", ["open", "File"])
def test_open_keyword_evaluation_order(tmp_path: Path, factory: str) -> None:
    """
    title: Source-order keyword evaluation survives ABI-slot reordering.
    parameters:
      tmp_path:
        type: Path
      factory:
        type: str
    """
    declarations = """fn mode() -> str:
  print("mode")
  return "w"
fn path() -> str:
  print("path")
  return "out"
"""
    result = execute(
        tmp_path,
        f"var f: file = {factory}(mode=mode(), file=path())",
        declarations,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "mode\npath\n"


def test_imported_module_can_open(tmp_path: Path) -> None:
    """
    title: Imported Arx modules reach the same native builtin and cleanup path.
    parameters:
      tmp_path:
        type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("clang is required")
    helper = tmp_path / "helper.x"
    helper.write_text(
        "```\ntitle: Helper\n```\nfn create() -> none:\n"
        '  var f: file = open("created", "w")\n'
        '  f.write("ok")\n  return none\n',
        encoding="utf-8",
    )
    entry = tmp_path / "main.x"
    entry.write_text(
        "```\ntitle: Entry\n```\nimport create from helper\n"
        "fn main() -> i32:\n  create()\n  return 0\n",
        encoding="utf-8",
    )
    executable = tmp_path / "program"
    app = ArxMain(input_files=[str(entry)], output_file=str(executable))
    assert app.compile()
    result = subprocess.run(
        [str(executable)],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "created").read_bytes() == b"ok"


def test_file_scope_cleanup_on_early_return(tmp_path: Path) -> None:
    """
    title: Explicit returns release file owners before leaving the function.
    parameters:
      tmp_path:
        type: Path
    """
    declarations = """fn early() -> i32:
  var f: file = open("early", "w")
  f.write("saved")
  return 7
"""
    result = execute(
        tmp_path,
        "assert early() == 7\n"
        'var source: file = open("early")\n'
        'assert source.read() == "saved"',
        declarations,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "early").read_bytes() == b"saved"


@pytest.mark.parametrize(
    "body",
    [
        'var f: file = open("x")\nf.read(1)',
        'var f: file = open("x")\nf.write(1)',
        'var f: file = open("x")\nf.seek(0)',
        'var f: file = open("x")\nvar other: file = cast(f, file)',
        'var encoding: str = "utf-8"\nopen("x", encoding=encoding)',
    ],
)
def test_deferred_file_forms_fail_in_analysis(body: str) -> None:
    """
    title: Unsupported operations fail before lowering, not in libc.
    parameters:
      body:
        type: str
    """
    with pytest.raises(SemanticError):
        analyze(parse_module(body))


def test_closed_file_error_has_real_method_location(tmp_path: Path) -> None:
    """
    title: Native diagnostics preserve the method token's source location.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        tmp_path, 'var f: file = open("out", "w")\nf.close()\nf.read()'
    )
    failure = parse_runtime_failure_output(result.stderr)
    assert result.returncode == 1
    assert failure is not None
    assert failure.line == 8
    assert failure.col == 5
    assert "closed" in failure.message


def test_read_string_can_return_after_lexical_file_release(
    tmp_path: Path,
) -> None:
    """
    title: File reads use the existing independently owned string return ABI.
    parameters:
      tmp_path:
        type: Path
    """
    (tmp_path / "source").write_text("independent", encoding="utf-8")
    declarations = """fn load() -> str:
  var f: file = open("source")
  return f.read()
"""
    result = execute(tmp_path, 'assert load() == "independent"', declarations)
    assert result.returncode == 0, result.stderr
