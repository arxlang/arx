"""
title: Test parser methods.
"""

import astx
import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx import system


def test_binop_precedence() -> None:
    """
    title: Test BinOp precedence.
    """
    lexer = Lexer()
    parser = Parser(lexer.lex())

    assert parser.bin_op_precedence["="] == 2
    assert parser.bin_op_precedence["<"] == 10
    assert parser.bin_op_precedence[">"] == 10
    assert parser.bin_op_precedence["<="] == 10
    assert parser.bin_op_precedence[">="] == 10
    assert parser.bin_op_precedence["=="] == 10
    assert parser.bin_op_precedence["!="] == 10
    assert parser.bin_op_precedence["+"] == 20
    assert parser.bin_op_precedence["-"] == 20
    assert parser.bin_op_precedence["*"] == 40
    assert parser.bin_op_precedence["/"] == 40


def test_parse_float_expr() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer("1.0 2.5")
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
    assert expr.value == 2.5

    ArxIO.string_to_buffer("3.25")
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_float_expr()
    assert expr
    assert isinstance(expr, astx.LiteralFloat32)
    assert expr.value == 3.25


def test_parse_int_expr() -> None:
    """
    title: Test integer literal parsing.
    """
    ArxIO.string_to_buffer("7")
    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    expr = parser.parse_int_expr()
    assert isinstance(expr, astx.LiteralInt32)
    assert expr.value == 7


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
    assert isinstance(expr.prototype.args[0], astx.Argument)
    assert isinstance(expr.body, astx.Block)
    assert isinstance(expr.body.nodes[0], astx.IfStmt)
    assert isinstance(expr.body.nodes[0].condition, astx.BinaryOp)
    assert isinstance(expr.body.nodes[0].then, astx.Block)
    assert isinstance(expr.body.nodes[0].then.nodes[0], astx.BinaryOp)
    assert isinstance(expr.body.nodes[0].else_, astx.Block)
    assert isinstance(expr.body.nodes[0].else_.nodes[0], astx.BinaryOp)
    assert isinstance(expr.body.nodes[1], astx.FunctionReturn)
    assert isinstance(expr.body.nodes[1].value, astx.Identifier)
    assert expr.body.nodes[1].value.name == "a"


def test_parse_module_docstring() -> None:
    """
    title: Test module docstring placement and parser ignore behavior.
    """
    ArxIO.string_to_buffer(
        "```\n"
        "title: Module docs\n"
        "summary: Main module reference\n"
        "```\n"
        "fn main():\n"
        "  return 1\n"
    )

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
    ArxIO.string_to_buffer(
        "  ```\n  title: module docs\n  ```\nfn main():\n  return 1\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())


def test_parse_function_docstring() -> None:
    """
    title: Test function docstring as first body statement.
    """
    ArxIO.string_to_buffer(
        "fn main():\n"
        "  ```\n"
        "  title: Function docs\n"
        "  summary: Function summary\n"
        "  ```\n"
        "  return 1\n"
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
        "fn main():\n  return 1\n  ```\n  title: Function docs\n  ```\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())


def test_parse_module_docstring_invalid_douki_schema() -> None:
    """
    title: Test module docstring validation against Douki schema.
    """
    ArxIO.string_to_buffer(
        "```\nsummary: Missing required title\n```\nfn main():\n  return 1\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException, match="Invalid module docstring"):
        parser.parse(lexer.lex())


def test_parse_function_docstring_invalid_douki_schema() -> None:
    """
    title: Test function docstring validation against Douki schema.
    """
    ArxIO.string_to_buffer(
        "fn main():\n"
        "  ```\n"
        "  bad_field: this is not allowed by schema\n"
        "  ```\n"
        "  return 1\n"
    )

    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException, match="Invalid function docstring"):
        parser.parse(lexer.lex())


def test_parse_typed_function_signature() -> None:
    """
    title: Test typed function signature parsing.
    """
    ArxIO.string_to_buffer(
        "fn main(arg1: i32, arg2: str) -> i32:\n  return arg1\n"
    )
    lexer = Lexer()
    parser = Parser(lexer.lex())

    parser.tokens.get_next_token()
    fn = parser.parse_function()

    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.prototype.args[0], astx.Argument)
    assert fn.prototype.args[0].name == "arg1"
    assert isinstance(fn.prototype.args[0].type_, astx.Int32)
    assert isinstance(fn.prototype.args[1].type_, astx.String)
    assert isinstance(fn.prototype.return_type, astx.Int32)


def test_parse_while_stmt() -> None:
    """
    title: Test while statement parsing.
    """
    ArxIO.string_to_buffer(
        "fn main():\n"
        "  var a: i32 = 0\n"
        "  while a < 10:\n"
        "    a = a + 1\n"
        "  return a\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[1], astx.WhileStmt)


def test_parse_for_count_stmt() -> None:
    """
    title: Test count-style for parsing.
    """
    ArxIO.string_to_buffer(
        "fn main():\n  for var i: i32 = 0; i < 5; i = i + 1:\n    return i\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[0], astx.ForCountLoopStmt)


def test_parse_for_range_slice_style() -> None:
    """
    title: Test range-style for parsing with colon-separated bounds.
    """
    ArxIO.string_to_buffer("fn main():\n  for j in (0:5:1):\n    return j\n")
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[0], astx.ForRangeLoopStmt)


def test_parse_for_range_tuple_style_is_rejected() -> None:
    """
    title: Tuple-style for range must be rejected.
    """
    ArxIO.string_to_buffer("fn main():\n  for j in (0, 5, 1):\n    return j\n")
    lexer = Lexer()
    parser = Parser()

    with pytest.raises(ParserException):
        parser.parse(lexer.lex())


def test_parse_builtin_cast_and_print() -> None:
    """
    title: Test builtin cast and print node generation.
    """
    ArxIO.string_to_buffer(
        "fn main():\n  var a: i32 = 1\n  print(cast(a, str))\n  return a\n"
    )
    lexer = Lexer()
    parser = Parser()

    tree = parser.parse(lexer.lex())
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.body.nodes[1], system.PrintExpr)
