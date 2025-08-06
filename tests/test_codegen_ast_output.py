"""Test code generation AST output."""

import pytest

from irx.builders.llvmliteir import LLVMLiteIR

from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


@pytest.mark.parametrize(
    "code",
    [
        "1 + 1",
        "1 + 2 * (3 - 2)",
        "if (1 < 2):\n    3\nelse:\n    2\n",
        "fn add_one(a):\n    a + 1\nadd_one(1)\n",
    ],
)
def test_ast_to_output(code: str) -> None:
    """Test AST to output."""
    lexer = Lexer()
    parser = Parser()
    ir = LLVMLiteIR()

    ArxIO.string_to_buffer(code)

    module_ast = parser.parse(lexer.lex())

    print(ir.translator.translate(module_ast))
