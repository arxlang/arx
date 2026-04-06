"""
title: Test code generation to file object.
"""

import shutil

from pathlib import Path
from typing import Any, Literal, cast

import astx
import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser

TMP_PATH = Path("/tmp/arxtmp")
TMP_PATH.mkdir(exist_ok=True)
HAS_CLANG = shutil.which("clang") is not None

_MIN_FLOAT_MAIN = "fn main() -> f32:\n  return 1.0 + 1.0\n"


def _parse_min_module(code: str = _MIN_FLOAT_MAIN) -> astx.Module:
    """
    title: Parse a minimal one-line main module for codegen tests.
    parameters:
      code:
        type: str
    returns:
      type: astx.Module
    """
    ArxIO.string_to_buffer(code)
    tree = Parser().parse(Lexer().lex())
    assert isinstance(tree, astx.Module)
    return tree


@pytest.mark.parametrize(
    "code",
    [
        "fn main() -> f32:\n  return 1.0 + 1.0",
        "fn main() -> f32:\n  return 1.0 + 2.0 * (3.0 - 2.0)",
        # "fn main():\n  if (1 < 2):\n    return 3\nelse:\n    return 2\n",
    ],
)
@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for object build")
def test_object_generation(code: str) -> None:
    """
    title: Test object generation.
    parameters:
      code:
        type: str
    """
    lexer = Lexer()
    parser = Parser()
    ir = ArxBuilder()

    ArxIO.string_to_buffer(code)
    module_ast = parser.parse(lexer.lex())

    bin_path = TMP_PATH / "testtmp"
    ir.build(module_ast, str(bin_path))
    bin_path.unlink()


def test_build_without_link_writes_object_bytes(
    tmp_path: Path,
) -> None:
    """
    title: link=False writes the LLVM object to output_file and skips clang.
    parameters:
      tmp_path:
        type: Path
    """
    module_ast = _parse_min_module()
    out = tmp_path / "only.o"
    ArxBuilder().build(module_ast, str(out), link=False)
    assert out.is_file()
    assert out.stat().st_size > 0


def test_build_rejects_unknown_link_mode(tmp_path: Path) -> None:
    """
    title: Unknown link_mode raises before invoking the linker.
    parameters:
      tmp_path:
        type: Path
    """
    module_ast = _parse_min_module()
    invalid: Any = "not-a-link-mode"
    with pytest.raises(ValueError, match="Invalid link mode"):
        ArxBuilder().build(
            module_ast,
            str(tmp_path / "never"),
            link=True,
            link_mode=invalid,
        )


@pytest.mark.parametrize(
    ("mode", "expect_flag"),
    [
        ("pie", "-pie"),
        ("no-pie", "-no-pie"),
    ],
)
@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for object build")
def test_build_passes_explicit_link_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expect_flag: str,
) -> None:
    """
    title: pie and no-pie link modes forward the matching flag to clang.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
      mode:
        type: str
      expect_flag:
        type: str
    """
    module_ast = _parse_min_module()
    exe = tmp_path / f"out-{mode}"
    recorded: dict[str, object] = {}

    def fake_clang(*args: object, **_kwargs: object) -> None:
        """
        title: Record clang argv and create the declared output artifact.
        parameters:
          args:
            type: object
            variadic: positional
        """
        recorded["args"] = args
        Path(str(args[-1])).write_bytes(b"")

    monkeypatch.setattr("arx.codegen.xh.clang", fake_clang)

    link_mode = cast(Literal["auto", "pie", "no-pie"], mode)
    ArxBuilder().build(module_ast, str(exe), link=True, link_mode=link_mode)

    args_tuple = recorded["args"]
    assert isinstance(args_tuple, tuple)
    assert expect_flag in args_tuple
    assert args_tuple[-1] == str(exe)
    assert exe.is_file()
