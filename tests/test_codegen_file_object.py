"""Test code generation to file object."""

from pathlib import Path

import pytest

from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.builders.llvmliteir import LLVMLiteIR

TMP_PATH = Path("/tmp/arxtmp")
TMP_PATH.mkdir(exist_ok=True)


@pytest.mark.parametrize(
    "code",
    [
        "fn main():\n  return 1 + 1",
        "fn main():\n  return 1 + 2 * (3 - 2)",
        # "fn main():\n  if (1 < 2):\n    return 3\nelse:\n    return 2\n",
    ],
)
def test_object_generation(code: str) -> None:
    """Test object generation."""
    lexer = Lexer()
    parser = Parser()
    ir = LLVMLiteIR()

    ArxIO.string_to_buffer(code)
    module_ast = parser.parse(lexer.lex())

    bin_path = TMP_PATH / "testtmp"
    ir.build(module_ast, str(bin_path))
    bin_path.unlink()
