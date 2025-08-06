"""Test code generation to file object."""

from pathlib import Path

import pytest

from arx.codegen.file_object import ObjectGenerator
from arx.io import ArxIO
from arx.lexer import Lexer, TokenList
from arx.parser import Parser

PROJECT_PATH = Path(__file__).parent.parent.resolve()


@pytest.mark.parametrize(
    "code",
    [
        "1 + 1",
        "1 + 2 * (3 - 2)",
        "if (1 < 2):\n    3\nelse:\n    2\n",
        "fn add_one(a):\n    a + 1\nadd_one(1)\n",
    ],
)
@pytest.mark.skip(reason="codegen with llvm is paused for now")
def test_object_generation(code: str) -> None:
    """Test object generation."""
    lexer = Lexer()
    lexer.clean()

    parser = Parser()
    parser.clean()

    tokens = TokenList([])

    ArxIO.string_to_buffer(code)
    ast = parser.parse(tokens)
    objgen = ObjectGenerator()
    objgen.evaluate(ast)
    # remove temporary object file generated
    (PROJECT_PATH / "tmp.o").unlink()
