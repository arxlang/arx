"""Test code generation AST output."""

import pytest

from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.builders.llvmliteir import LLVMLiteIR


@pytest.mark.parametrize(
    "code",
    [
        "fn main():\n  return 0 + 1",
        "fn main():\n  return 1 + 2 * (3 - 2)",
        # "fn main():\n  if (1 < 2):\n    return 3\n  else:\n    return 2\n",
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
