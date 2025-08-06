"""Test code generation AST output."""

import pytest

from arx.codegen.ast_output import ASTtoOutput
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
    printer = ASTtoOutput()

    ArxIO.string_to_buffer(code)

    module_ast = parser.parse(lexer.lex())
    printer.emit_ast(module_ast)
