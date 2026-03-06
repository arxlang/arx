"""
title: Test code generation AST output.
"""

import pytest

from arx.codegen import LLVMLiteIR
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


@pytest.mark.parametrize(
    "code",
    [
        "fn main() -> f32:\n  return 0.0 + 1.0",
        "fn main() -> f32:\n  return 1.0 + 2.0 * (3.0 - 2.0)",
        "fn main() -> i32:\n  print(42)\n  return 0",
        "fn main() -> i32:\n  print(3.5)\n  return 0",
        (
            "fn average(x: f32, y: f32) -> f32:\n"
            "  return (x + y) * 0.5\n"
            "fn main() -> i32:\n"
            "  print(average(10.0, 20.0))\n"
            "  return 0"
        ),
        (
            "fn fib(x: i32) -> i32:\n"
            "  if x < 3:\n"
            "    return 1\n"
            "  else:\n"
            "    return fib(x-1)+fib(x-2)\n"
            "fn main() -> i32:\n"
            "  print(fib(10))\n"
            "  return 0"
        ),
        # "fn main():\n  if (1 < 2):\n    return 3\n  else:\n    return 2\n",
    ],
)
def test_ast_to_output(code: str) -> None:
    """
    title: Test AST to output.
    parameters:
      code:
        type: str
    """
    lexer = Lexer()
    parser = Parser()
    ir = LLVMLiteIR()

    ArxIO.string_to_buffer(code)

    module_ast = parser.parse(lexer.lex())

    result = ir.translator.translate(module_ast)
    assert result
