"""
title: Tests for `arx`.`lexer`.
"""

import pytest

from arx.io import ArxIO
from arx.lexer import Lexer, Token, TokenKind


def test_token_name() -> None:
    """
    title: Test token name.
    """
    assert Token(kind=TokenKind.eof, value="").get_name() == "eof"
    assert Token(kind=TokenKind.kw_function, value="").get_name() == "function"
    assert Token(kind=TokenKind.kw_return, value="").get_name() == "return"
    assert (
        Token(kind=TokenKind.identifier, value="").get_name() == "identifier"
    )
    assert Token(kind=TokenKind.kw_if, value="").get_name() == "if"
    assert Token(kind=TokenKind.kw_for, value="").get_name() == "for"
    assert Token(kind=TokenKind.operator, value="+").get_name() == "+"
    assert Token(kind=TokenKind.operator, value="+").get_name() == "+"


@pytest.mark.parametrize("value", ["123", "234", "345"])
def test_advance(value: str) -> None:
    """
    title: Test advance lexer method.
    parameters:
      value:
        type: str
    """
    ArxIO.string_to_buffer(value)
    lexer = Lexer()
    assert lexer.advance() == value[0]
    assert lexer.advance() == value[1]
    assert lexer.advance() == value[2]


def test_get_tok_simple() -> None:
    """
    title: Test get_token.
    """
    ArxIO.string_to_buffer("11")
    lexer = Lexer()
    assert lexer.get_token() == Token(kind=TokenKind.int_literal, value=11)

    ArxIO.string_to_buffer("21")
    assert lexer.get_token() == Token(kind=TokenKind.int_literal, value=21)

    ArxIO.string_to_buffer("31")
    assert lexer.get_token() == Token(kind=TokenKind.int_literal, value=31)


def test_get_next_token_simple() -> None:
    """
    title: Test get_next_token.
    """
    lexer = Lexer()
    ArxIO.string_to_buffer("11")
    tokens = lexer.lex()
    assert tokens.get_next_token() == Token(
        kind=TokenKind.int_literal, value=11
    )

    ArxIO.string_to_buffer("21")
    tokens = lexer.lex()
    assert tokens.get_next_token() == Token(
        kind=TokenKind.int_literal, value=21
    )

    ArxIO.string_to_buffer("31")
    tokens = lexer.lex()
    assert tokens.get_next_token() == Token(
        kind=TokenKind.int_literal, value=31
    )


def test_get_tok() -> None:
    """
    title: Test gettok for main tokens.
    """
    ArxIO.string_to_buffer(
        "fn math(x):\n"
        "  if x > 10:\n"
        "    return x + 1\n"
        "  else:\n"
        "    return x * 20\n"
        "math(1)\n"
    )
    lexer = Lexer()
    assert lexer.get_token() == Token(kind=TokenKind.kw_function, value="fn")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="math")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value="(")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="x")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=")")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=":")
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=2)
    assert lexer.get_token() == Token(kind=TokenKind.kw_if, value="if")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="x")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=">")
    assert lexer.get_token() == Token(kind=TokenKind.int_literal, value=10)
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=":")
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=4)
    assert lexer.get_token() == Token(kind=TokenKind.kw_return, value="return")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="x")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value="+")
    assert lexer.get_token() == Token(kind=TokenKind.int_literal, value=1)
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=2)
    assert lexer.get_token() == Token(kind=TokenKind.kw_else, value="else")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=":")
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=4)
    assert lexer.get_token() == Token(kind=TokenKind.kw_return, value="return")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="x")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value="*")
    assert lexer.get_token() == Token(kind=TokenKind.int_literal, value=20)
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="math")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value="(")
    assert lexer.get_token() == Token(kind=TokenKind.int_literal, value=1)
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=")")


def test_get_tok_module_docstring() -> None:
    """
    title: Test tokenization of module docstrings.
    """
    ArxIO.string_to_buffer("```\nmodule docs\n```\nfn main():\n  return 1\n")
    lexer = Lexer()

    assert lexer.get_token().kind == TokenKind.docstring
    assert lexer.get_token() == Token(kind=TokenKind.kw_function, value="fn")


def test_get_tok_function_docstring() -> None:
    """
    title: Test tokenization of function docstrings.
    """
    ArxIO.string_to_buffer(
        "fn main():\n  ```\n  function docs\n  ```\n  return 1\n"
    )
    lexer = Lexer()

    assert lexer.get_token() == Token(kind=TokenKind.kw_function, value="fn")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="main")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value="(")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=")")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=":")
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=2)
    assert lexer.get_token().kind == TokenKind.docstring
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=2)
    assert lexer.get_token() == Token(kind=TokenKind.kw_return, value="return")


def test_get_tok_multi_char_operators() -> None:
    """
    title: Test tokenization of multi-character operators.
    """
    ArxIO.string_to_buffer("a == b != c <= d >= e && f || g -> h ++i --j")
    lexer = Lexer()

    expected = [
        Token(TokenKind.identifier, "a"),
        Token(TokenKind.operator, "=="),
        Token(TokenKind.identifier, "b"),
        Token(TokenKind.operator, "!="),
        Token(TokenKind.identifier, "c"),
        Token(TokenKind.operator, "<="),
        Token(TokenKind.identifier, "d"),
        Token(TokenKind.operator, ">="),
        Token(TokenKind.identifier, "e"),
        Token(TokenKind.operator, "&&"),
        Token(TokenKind.identifier, "f"),
        Token(TokenKind.operator, "||"),
        Token(TokenKind.identifier, "g"),
        Token(TokenKind.operator, "->"),
        Token(TokenKind.identifier, "h"),
        Token(TokenKind.operator, "++"),
        Token(TokenKind.identifier, "i"),
        Token(TokenKind.operator, "--"),
        Token(TokenKind.identifier, "j"),
    ]

    for token in expected:
        assert lexer.get_token() == token


def test_get_tok_literals_and_keywords() -> None:
    """
    title: Test tokenization for string/char/bool/none and while keyword.
    """
    ArxIO.string_to_buffer(
        "while true:\n  x = none\n  y = \"hello\"\n  z = 'A'\n"
    )
    lexer = Lexer()

    assert lexer.get_token() == Token(TokenKind.kw_while, "while")
    assert lexer.get_token() == Token(TokenKind.bool_literal, True)
    assert lexer.get_token() == Token(TokenKind.operator, ":")
    assert lexer.get_token() == Token(TokenKind.indent, 2)
    assert lexer.get_token() == Token(TokenKind.identifier, "x")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.none_literal, None)
    assert lexer.get_token() == Token(TokenKind.indent, 2)
    assert lexer.get_token() == Token(TokenKind.identifier, "y")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.string_literal, "hello")
    assert lexer.get_token() == Token(TokenKind.indent, 2)
    assert lexer.get_token() == Token(TokenKind.identifier, "z")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.char_literal, "A")


def test_skip_hash_comments() -> None:
    """
    title: Test that hash comments are ignored by lexer.
    """
    ArxIO.string_to_buffer("a = 1  # comment\nb = 2\n")
    lexer = Lexer()

    assert lexer.get_token() == Token(TokenKind.identifier, "a")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.int_literal, 1)
    assert lexer.get_token() == Token(TokenKind.identifier, "b")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.int_literal, 2)
