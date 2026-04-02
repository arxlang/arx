"""
title: Test code generation to file object.
"""

import shutil

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser

TMP_PATH = Path("/tmp/arxtmp")
TMP_PATH.mkdir(exist_ok=True)
HAS_CLANG = shutil.which("clang") is not None


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
