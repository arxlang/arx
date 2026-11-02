"""
title: Restricted open builtin parser, semantics, and native execution.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

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
from irx.builder.runtime.exceptions import parse_exception_output
from llvmlite import binding as llvm

from .file_support import analyze_arx as analyze
from .test_file_class_native import build_audited_file_program


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
    text = builder.translate(module)
    llvm.parse_assembly(text).verify()
    executable = tmp_path / "program"
    builder._build_from_ir_result(text, str(executable), True, "auto")
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
        ('"x", "wb+"', "supports only"),
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
    failure = parse_exception_output(result.stderr)
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
        f'var mode: str = "wb+"\nvar f: file = {factory}("keep", mode)',
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
    failure = parse_exception_output(result.stderr)
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
    failure = parse_exception_output(result.stderr)
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


@pytest.mark.parametrize(
    "body,match",
    [
        ("bytes([true])", "integer items"),
        ("bytes([1.5])", "integer items"),
        ('bytes("text")', "integer items"),
        ("bytes(10)", "integer items"),
        ("bytes([1], [2])", "expects one input"),
        ("var value: bytes = bytes([1])\nvalue.append(2)", "list|class"),
        (
            "var value: bytes = bytes([1])\nvar alias: bytes = value",
            "borrowed storage",
        ),
        ("var value: bytes = cast(bytes([1]), bytes)", "bytes casts"),
        ("var value: list[bytes]", "nested ownership"),
        (
            'var stream: File = open("x", "rb")\nstream.write_bytes("text")',
            "requires bytes|expects",
        ),
        (
            'var stream: File = open("x", "rb")\nstream.read_bytes(true)',
            "requires|expects",
        ),
        ('var stream: File = open("x", "rb")\nstream.read_bytes()', "expects"),
        (
            'var stream: File = open("x", "wb", encoding="utf-8")',
            "binary mode",
        ),
        ('var stream: File = open("x", "ab", errors="strict")', "binary mode"),
        ("var bytes: i32 = 0\nbytes([1])", "does not resolve"),
    ],
)
def test_binary_semantic_restrictions(body: str, match: str) -> None:
    """
    title: Reject unsafe coercion, mutation, aliases, and binary text options.
    parameters:
      body:
        type: str
      match:
        type: str
    """
    with pytest.raises(SemanticError, match=match):
        analyze(parse_module(body))


@pytest.fixture(scope="module")
def binary_failure_program(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: Reuse one binary across recoverable constructor and File errors.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    if shutil.which("clang") is None:
        pytest.skip("binary failure checks require clang")
    source = """```
title: Binary errors
```
extern getchar() -> i32
fn main() -> i32:
  var scenario: i32 = getchar()
  try:
    if scenario == 0:
      var negative: i8 = -1
      bytes([negative])
    if scenario == 1:
      var large: u64 = 18446744073709551615
      bytes([large])
    if scenario == 2:
      bytes([0, 255, 256])
    if scenario == 3:
      var mode: str = "wb"
      open("keep", mode, encoding="utf-8")
    if scenario == 4:
      open("keep", "rb").read()
    if scenario == 5:
      open("keep", "wb").write("")
    if scenario == 6:
      open("keep", "r").read_bytes(0)
    if scenario == 7:
      open("keep", "w").write_bytes(bytes())
    if scenario == 8:
      open("keep", "rb").read_bytes(-1)
    if scenario == 9:
      open("missing", "rb")
    if scenario == 10:
      open("directory", "wb")
    if scenario == 11:
      var data: bytes = bytes([0, 255])
      data[2]
    if scenario == 12:
      var empty: bytes = bytes()
      empty[0]
    if scenario == 13:
      var signed: bytes = bytes([0, 255])
      signed[-1]
    return 1
  except ValueError:
    return 10
  except OSError:
    return 11
  except IndexError:
    return 12
"""
    ArxIO.string_to_buffer(source)
    builder = ArxBuilder()
    text = builder.translate(Parser().parse(Lexer().lex()))
    llvm.parse_assembly(text).verify()
    program = tmp_path_factory.mktemp("binary-errors") / "program"
    if sys.platform == "linux":
        return build_audited_file_program(builder, text, program.parent)
    builder._build_from_ir(text, str(program))
    return program


@pytest.mark.parametrize(
    "scenario,expected",
    [(i, 10 if i < 9 else 11 if i < 11 else 12) for i in range(14)],
)
def test_binary_failures_are_recoverable(
    binary_failure_program: Path, tmp_path: Path, scenario: int, expected: int
) -> None:
    """
    title: Check values, modes, bounds and filesystem failures before success.
    parameters:
      binary_failure_program:
        type: Path
      tmp_path:
        type: Path
      scenario:
        type: int
      expected:
        type: int
    """
    (tmp_path / "keep").write_bytes(b"unchanged")
    (tmp_path / "directory").mkdir()
    result = subprocess.run(
        [str(binary_failure_program)],
        input=bytes([scenario]),
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == expected, result.stderr
    if sys.platform == "linux":
        assert b"AUDIT live=0 " in result.stderr
    if scenario == 3:
        assert (tmp_path / "keep").read_bytes() == b"unchanged"


@pytest.mark.parametrize(
    "declarations,match",
    [
        ("extern expose(value: bytes) -> bytes\n", "FFI|unsupported"),
        ("class Box:\n  data: bytes\n", "field|ownership"),
        ("fn borrow(data: bytes) -> bytes:\n  return data\n", "borrowed"),
        (
            "fn pending() -> bytes:\n"
            "  var data: bytes = bytes([1])\n"
            "  try:\n    return data\n"
            "  finally:\n    print(len(data))\n",
            "finally cannot reuse",
        ),
    ],
)
def test_bytes_cannot_escape_ownership(declarations: str, match: str) -> None:
    """
    title: >-
      Reject unmodeled byte-buffer escapes and reuse after return transfer.
    parameters:
      declarations:
        type: str
      match:
        type: str
    """
    with pytest.raises(SemanticError, match=match):
        analyze(parse_module("bytes()", declarations))
