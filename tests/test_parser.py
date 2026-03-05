"""
title: Test parser methods.
"""

import astx
import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser


def test_binop_precedence() -> None:
    """
    title: Test BinOp precedence.
    """
    lexer = Lexer()
    parser = Parser(lexer.lex())

    assert parser.bin_op_precedence["="] == 2
    assert parser.bin_op_precedence["<"] == 10
    assert parser.bin_op_precedence[">"] == 10
    assert parser.bin_op_precedence["+"] == 20
    assert parser.bin_op_precedence["-"] == 20
    assert parser.bin_op_precedence["*"] == 40


def test_parse_float_expr() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer("1 2")
    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat32)
    assert expr.value == 1.0

    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat32)
    assert expr.value == 2

    ArxIO.string_to_buffer("3")
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat32)
    assert expr.value == 3


def test_parse() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer(
        "if 1 > 2:\n" + "  a = 1\n" + "else:\n" + "  a = 2\n"
    )
    lexer = Lexer()
    parser = Parser()

    expr = parser.parse(lexer.lex())
    assert expr
    assert isinstance(expr, astx.Block)


def test_parse_if_stmt() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer(
        "if 1 > 2:\n" + "  a = 1\n" + "else:\n" + "  a = 2\n"
    )

    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_primary()
    assert expr
    assert isinstance(expr, astx.IfStmt)
    assert isinstance(expr.condition, astx.BinaryOp)
    assert isinstance(expr.then, astx.Block)
    assert isinstance(expr.then.nodes[0], astx.BinaryOp)
    assert isinstance(expr.else_, astx.Block)
    assert isinstance(expr.else_.nodes[0], astx.BinaryOp)


def test_parse_fn() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer(
        "fn math(x):\n"
        + "  if 1 > 2:\n"
        + "    a = 1\n"
        + "  else:\n"
        + "    a = 2\n"
        + "  return a\n"
    )

    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_function()
    assert expr
    assert isinstance(expr, astx.FunctionDef)
    assert isinstance(expr.prototype, astx.FunctionPrototype)
    assert isinstance(expr.prototype.args[0], astx.Variable)
    assert isinstance(expr.body, astx.Block)
    assert isinstance(expr.body.nodes[0], astx.IfStmt)
    assert isinstance(expr.body.nodes[0].condition, astx.BinaryOp)
    assert isinstance(expr.body.nodes[0].then, astx.Block)
    assert isinstance(expr.body.nodes[0].then.nodes[0], astx.BinaryOp)
    assert isinstance(expr.body.nodes[0].else_, astx.Block)
    assert isinstance(expr.body.nodes[0].else_.nodes[0], astx.BinaryOp)
    assert isinstance(expr.body.nodes[1], astx.FunctionReturn)
    assert isinstance(expr.body.nodes[1].value, astx.Variable)
    assert expr.body.nodes[1].value.name == "a"


def test_parse_module_docstring() -> None:
    """
    title: Test module docstring placement and parser ignore behavior.
    """
    ArxIO.string_to_buffer("```\nModule docs\n```\nfn main():\n  return 1\n")

    lexer = Lexer()
    parser = Parser()
    tree = parser.parse(lexer.lex())

    assert isinstance(tree, astx.Block)
    assert len(tree.nodes) == 1
    assert isinstance(tree.nodes[0], astx.FunctionDef)


def test_parse_module_docstring_must_start_first_line() -> None:
    """
    title: Test module docstring must start at line 1, column 1.
    """
    ArxIO.string_to_buffer("  ```\nmodule docs\n```\nfn main():\n  return 1\n")

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())


def test_parse_function_docstring() -> None:
    """
    title: Test function docstring as first body statement.
    """
    ArxIO.string_to_buffer(
        "fn main():\n  ```\n  function docs\n  ```\n  return 1\n"
    )

    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_function()

    assert isinstance(expr, astx.FunctionDef)
    assert len(expr.body.nodes) == 1
    assert isinstance(expr.body.nodes[0], astx.FunctionReturn)


def test_parse_function_docstring_must_be_first_stmt() -> None:
    """
    title: Test function docstring invalid placement after expressions.
    """
    ArxIO.string_to_buffer(
        "fn main():\n  return 1\n  ```\n  function docs\n  ```\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())
