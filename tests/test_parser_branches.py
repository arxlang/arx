"""
title: Additional parser branch coverage tests.
"""

from __future__ import annotations

import astx
import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer, Token, TokenKind, TokenList
from arx.parser import Parser


def _parse(code: str) -> astx.Module:
    ArxIO.string_to_buffer(code)
    return Parser().parse(Lexer().lex())


def test_parse_literal_kinds_and_list_literal() -> None:
    """
    title: Parse string/char/bool/none and list literals.
    """
    tree = _parse(
        "fn main() -> list[i32]:\n"
        '  var s: str = "abc"\n'
        "  var c: char = 'A'\n"
        "  var b: bool = true\n"
        "  var n: none = none\n"
        "  return [1, 2, 3]\n"
    )

    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    ret = fn.body.nodes[-1]
    assert isinstance(ret, astx.FunctionReturn)
    assert isinstance(ret.value, astx.LiteralList)


def test_parse_list_literal_rejects_non_literal_elements() -> None:
    """
    title: List literals reject non-literal values.
    """
    with pytest.raises(
        ParserException,
        match=(
            r"(only literal elements|"
            r"Unknown token when expecting an expression)"
        ),
    ):
        _parse("fn main() -> list[i32]:\n  return [foo]\n")


def test_parse_datetime_and_timestamp_builtins() -> None:
    """
    title: Parse datetime/timestamp builtin literals.
    """
    tree = _parse(
        "fn dt() -> datetime:\n"
        '  return datetime("2026-01-01T00:00:00")\n'
        "fn ts() -> timestamp:\n"
        '  return timestamp("2026-01-01T00:00:00Z")\n'
    )

    fn_dt = tree.nodes[0]
    fn_ts = tree.nodes[1]
    assert isinstance(fn_dt, astx.FunctionDef)
    assert isinstance(fn_ts, astx.FunctionDef)
    assert isinstance(fn_dt.body.nodes[0], astx.FunctionReturn)
    assert isinstance(fn_ts.body.nodes[0], astx.FunctionReturn)
    assert isinstance(fn_dt.body.nodes[0].value, astx.LiteralDateTime)
    assert isinstance(fn_ts.body.nodes[0].value, astx.LiteralTimestamp)


def test_parse_datetime_requires_string_literal() -> None:
    """
    title: Datetime builtin expects a string literal.
    """
    with pytest.raises(ParserException, match="expects a string literal"):
        _parse("fn main() -> datetime:\n  return datetime(1)\n")


@pytest.mark.parametrize(
    "code, expected",
    [
        (
            "fn main() -> i32:\n  for 1 in (0:1:1):\n    return 1\n",
            "identifier",
        ),
        (
            "fn main() -> i32:\n  for i (0:1:1):\n    return i\n",
            "Expected 'in'",
        ),
    ],
)
def test_parse_for_error_paths(code: str, expected: str) -> None:
    """
    title: For-loop parser errors.
    parameters:
      code:
        type: str
      expected:
        type: str
    """
    with pytest.raises(ParserException, match=expected):
        _parse(code)


def test_parse_inline_var_declaration_error_paths() -> None:
    """
    title: Parse inline var declaration errors.
    """
    ArxIO.string_to_buffer("x")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected 'var'"):
        parser.parse_inline_var_declaration()

    ArxIO.string_to_buffer("var 1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="identifier after var"):
        parser.parse_inline_var_declaration()

    ArxIO.string_to_buffer("var i = 0")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="type annotation"):
        parser.parse_inline_var_declaration()


def test_parse_var_expr_error_paths() -> None:
    """
    title: Parse var expression errors.
    """
    ArxIO.string_to_buffer("var 1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="identifier after var"):
        parser.parse_var_expr()

    ArxIO.string_to_buffer("var a: i32 in")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Legacy 'var"):
        parser.parse_var_expr()

    ArxIO.string_to_buffer("var a = 1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="type annotation"):
        parser.parse_var_expr()


def test_parse_type_error_paths() -> None:
    """
    title: Parse type errors.
    """
    ArxIO.string_to_buffer("1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected a type name"):
        parser.parse_type()

    ArxIO.string_to_buffer("unknown")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Unknown type"):
        parser.parse_type()


def test_parse_type_list_and_default_values() -> None:
    """
    title: Parse list type and default-value helper branches.
    """
    tree = _parse("fn main(arg: list[i32]) -> i32:\n  return 1\n")
    fn = tree.nodes[0]
    assert isinstance(fn, astx.FunctionDef)
    assert isinstance(fn.prototype.args[0].type_, astx.ListType)

    parser = Parser()
    assert isinstance(
        parser._default_value_for_type(astx.Float16()),
        astx.LiteralFloat16,
    )
    assert isinstance(
        parser._default_value_for_type(astx.Float32()),
        astx.LiteralFloat32,
    )
    assert isinstance(
        parser._default_value_for_type(astx.Int32()),
        astx.LiteralInt32,
    )
    assert isinstance(
        parser._default_value_for_type(astx.Boolean()),
        astx.LiteralBoolean,
    )
    assert isinstance(
        parser._default_value_for_type(astx.String()),
        astx.LiteralString,
    )
    assert isinstance(
        parser._default_value_for_type(astx.NoneType()),
        astx.LiteralNone,
    )
    assert isinstance(
        parser._default_value_for_type(astx.DateTime()),
        astx.LiteralDateTime
    )
    assert isinstance(
        parser._default_value_for_type(astx.Timestamp()),
        astx.LiteralTimestamp
    )
    assert isinstance(
        parser._default_value_for_type(astx.Date()),
        astx.LiteralDate
    )
    assert isinstance(
        parser._default_value_for_type(astx.Time()), 
        astx.LiteralTime
    )

    with pytest.raises(ParserException):
        parser._default_value_for_type(astx.ListType([astx.Int32()]))

def test_parse_unary_and_prototype_error_paths() -> None:
    """
    title: Parse unary expressions and prototype errors.
    """
    ArxIO.string_to_buffer("-1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    expr = parser.parse_expression()
    assert isinstance(expr, astx.UnaryOp)
    assert isinstance(expr.type_, astx.DataType)

    ArxIO.string_to_buffer("(")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected function name"):
        parser.parse_prototype(expect_colon=False)

    ArxIO.string_to_buffer("f(1)")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected argument name"):
        parser.parse_prototype(expect_colon=False)

    ArxIO.string_to_buffer("f(x)")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected type annotation"):
        parser.parse_prototype(expect_colon=False)

    ArxIO.string_to_buffer("f(x: i32)")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected return type"):
        parser.parse_prototype(expect_colon=False)


def test_parse_block_error_paths() -> None:
    """
    title: Parse block error branches.
    """
    ArxIO.string_to_buffer("1")
    parser = Parser(Lexer().lex())
    parser.tokens.get_next_token()
    with pytest.raises(ParserException, match="Expected indentation"):
        parser.parse_block()

    parser = Parser(
        TokenList([Token(TokenKind.indent, 0), Token(TokenKind.eof, "")])
    )
    parser.tokens.get_next_token()
    parser.indent_level = 0
    with pytest.raises(ParserException, match="There is no new block"):
        parser.parse_block()

    with pytest.raises(ParserException, match="Indentation not allowed here"):
        _parse("fn main() -> i32:\n  a = 1\n    b = 2\n")


def test_parse_primary_unknown_token_branch() -> None:
    """
    title: Parse unknown primary token branch.
    """
    parser = Parser(
        TokenList(
            [
                Token(TokenKind.kw_then, "then"),
                Token(TokenKind.eof, ""),
            ]
        )
    )
    parser.tokens.get_next_token()

    with pytest.raises(ParserException, match="Unknown token"):
        parser.parse_primary()
