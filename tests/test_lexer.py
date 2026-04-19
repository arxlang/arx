"""
title: Tests for `arx`.`lexer`.
"""

import pytest

from arx.io import ArxIO
from arx.lexer import Lexer, LexerError, Token, TokenKind, TokenList
from astx import SourceLocation


def test_token_name() -> None:
    """
    title: Test token name.
    """
    assert Token(kind=TokenKind.eof, value="").get_name() == "eof"
    assert Token(kind=TokenKind.kw_function, value="").get_name() == "function"
    assert Token(kind=TokenKind.kw_return, value="").get_name() == "return"
    assert Token(kind=TokenKind.kw_class, value="").get_name() == "class"
    assert Token(kind=TokenKind.kw_import, value="").get_name() == "import"
    assert Token(kind=TokenKind.kw_assert, value="").get_name() == "assert"
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
    ArxIO.string_to_buffer(
        "```\nmodule docs\n```\nfn main() -> i32:\n  return 1\n"
    )
    lexer = Lexer()

    assert lexer.get_token().kind == TokenKind.docstring
    assert lexer.get_token() == Token(kind=TokenKind.kw_function, value="fn")


def test_get_tok_function_docstring() -> None:
    """
    title: Test tokenization of function docstrings.
    """
    ArxIO.string_to_buffer(
        "fn main() -> i32:\n  ```\n  function docs\n  ```\n  return 1\n"
    )
    lexer = Lexer()

    assert lexer.get_token() == Token(kind=TokenKind.kw_function, value="fn")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="main")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value="(")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=")")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value="->")
    assert lexer.get_token() == Token(kind=TokenKind.identifier, value="i32")
    assert lexer.get_token() == Token(kind=TokenKind.operator, value=":")
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=2)
    assert lexer.get_token().kind == TokenKind.docstring
    assert lexer.get_token() == Token(kind=TokenKind.indent, value=2)
    assert lexer.get_token() == Token(kind=TokenKind.kw_return, value="return")


def test_get_tok_class_annotation_line() -> None:
    """
    title: Test tokenization for class annotation lines.
    """
    ArxIO.string_to_buffer(
        "@[public, static]\nclass Math:\n  value: int32 = 1\n"
    )
    lexer = Lexer()

    expected = [
        Token(TokenKind.operator, "@"),
        Token(TokenKind.operator, "["),
        Token(TokenKind.identifier, "public"),
        Token(TokenKind.operator, ","),
        Token(TokenKind.identifier, "static"),
        Token(TokenKind.operator, "]"),
        Token(TokenKind.kw_class, "class"),
        Token(TokenKind.identifier, "Math"),
        Token(TokenKind.operator, ":"),
        Token(TokenKind.indent, 2),
        Token(TokenKind.identifier, "value"),
    ]

    for token in expected:
        assert lexer.get_token() == token


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
    title: Test tokenization for string/char/bool/void and while keyword.
    """
    ArxIO.string_to_buffer(
        "while true:\n  x = void\n  y = \"hello\"\n  z = 'A'\n"
    )
    lexer = Lexer()

    assert lexer.get_token() == Token(TokenKind.kw_while, "while")
    assert lexer.get_token() == Token(TokenKind.bool_literal, True)
    assert lexer.get_token() == Token(TokenKind.operator, ":")
    assert lexer.get_token() == Token(TokenKind.indent, 2)
    assert lexer.get_token() == Token(TokenKind.identifier, "x")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.void_literal, None)
    assert lexer.get_token() == Token(TokenKind.indent, 2)
    assert lexer.get_token() == Token(TokenKind.identifier, "y")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.string_literal, "hello")
    assert lexer.get_token() == Token(TokenKind.indent, 2)
    assert lexer.get_token() == Token(TokenKind.identifier, "z")
    assert lexer.get_token() == Token(TokenKind.operator, "=")
    assert lexer.get_token() == Token(TokenKind.char_literal, "A")


def test_get_tok_assert_keyword() -> None:
    """
    title: Test tokenization of the assert keyword and string message.
    """
    ArxIO.string_to_buffer('assert x == 1, "ok"\n')
    lexer = Lexer()

    assert lexer.get_token() == Token(TokenKind.kw_assert, "assert")
    assert lexer.get_token() == Token(TokenKind.identifier, "x")
    assert lexer.get_token() == Token(TokenKind.operator, "==")
    assert lexer.get_token() == Token(TokenKind.int_literal, 1)
    assert lexer.get_token() == Token(TokenKind.operator, ",")
    assert lexer.get_token() == Token(TokenKind.string_literal, "ok")


def test_get_tok_multiline_grouped_import() -> None:
    """
    title: Test tokenization for multiline grouped import syntax.
    """
    ArxIO.string_to_buffer(
        "import (\n  sin,\n  cos as cosine,\n) from std.math\n"
    )
    lexer = Lexer()

    expected = [
        Token(TokenKind.kw_import, "import"),
        Token(TokenKind.operator, "("),
        Token(TokenKind.indent, 2),
        Token(TokenKind.identifier, "sin"),
        Token(TokenKind.operator, ","),
        Token(TokenKind.indent, 2),
        Token(TokenKind.identifier, "cos"),
        Token(TokenKind.identifier, "as"),
        Token(TokenKind.identifier, "cosine"),
        Token(TokenKind.operator, ","),
        Token(TokenKind.operator, ")"),
        Token(TokenKind.identifier, "from"),
        Token(TokenKind.identifier, "std"),
        Token(TokenKind.operator, "."),
        Token(TokenKind.identifier, "math"),
    ]

    for token in expected:
        assert lexer.get_token() == token


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


def test_token_hash_and_display_value() -> None:
    """
    title: Token is stable for hashing and get_display_value branches.
    """
    loc = SourceLocation(0, 0)
    int_tok = Token(TokenKind.int_literal, 7, location=loc)
    assert hash(int_tok) == hash(f"{TokenKind.int_literal}{7}")
    assert int_tok.get_display_value() == "(7)"

    ident = Token(TokenKind.identifier, "id", location=loc)
    assert ident.get_display_value() == "(id)"

    ind = Token(TokenKind.indent, 4, location=loc)
    assert ind.get_display_value() == "(4)"

    fl = Token(TokenKind.float_literal, 1.5, location=loc)
    assert fl.get_display_value() == "(1.5)"

    st = Token(TokenKind.string_literal, "x", location=loc)
    assert st.get_display_value() == "(...)"

    ch = Token(TokenKind.char_literal, "Z", location=loc)
    assert ch.get_display_value() == "(Z)"

    bl = Token(TokenKind.bool_literal, False, location=loc)
    assert bl.get_display_value() == "(False)"

    nl = Token(TokenKind.void_literal, None, location=loc)
    assert nl.get_display_value() == ""

    doc = Token(TokenKind.docstring, "d", location=loc)
    assert doc.get_display_value() == "(...)"

    op = Token(TokenKind.operator, "+", location=loc)
    assert op.get_display_value() == ""
    assert str(op) == "+"


def test_token_list_iteration() -> None:
    """
    title: TokenList supports iteration and StopIteration.
    """
    items = [
        Token(TokenKind.identifier, "a"),
        Token(TokenKind.eof, ""),
    ]
    token_list = TokenList(items)
    assert list(token_list) == items

    again = TokenList([Token(TokenKind.int_literal, 1)])
    it = iter(again)
    assert next(it) == Token(TokenKind.int_literal, 1)
    with pytest.raises(StopIteration):
        next(it)


def test_lexer_error_message_includes_location() -> None:
    """
    title: LexerError formats line and column into the message.
    """
    loc = SourceLocation(3, 12)
    err = LexerError("bad token", loc)
    assert "at line 3, col 12" in str(err)
    assert err.location.line == loc.line and err.location.col == loc.col


def test_lexer_boolean_false_and_logical_operators() -> None:
    """
    title: Lexer emits false literal and treats and/or as operators.
    """
    ArxIO.string_to_buffer("false and x or y\n")
    lexer = Lexer()
    assert lexer.get_token() == Token(TokenKind.bool_literal, False)
    assert lexer.get_token() == Token(TokenKind.operator, "and")
    assert lexer.get_token() == Token(TokenKind.identifier, "x")
    assert lexer.get_token() == Token(TokenKind.operator, "or")
    assert lexer.get_token() == Token(TokenKind.identifier, "y")


def test_lexer_dot_as_operator_alone() -> None:
    """
    title: A lone dot is an operator token, not a float.
    """
    ArxIO.string_to_buffer(". +\n")
    lexer = Lexer()
    assert lexer.get_token() == Token(TokenKind.operator, ".")
    assert lexer.get_token() == Token(TokenKind.operator, "+")


def test_lexer_rejects_multiple_decimal_points() -> None:
    """
    title: Multiple dots in one numeric lexeme raise LexerError.
    """
    ArxIO.string_to_buffer("3.14.15\n")
    lexer = Lexer()
    with pytest.raises(LexerError, match="multiple decimal points"):
        lexer.get_token()


def test_lexer_docstring_bad_opening_delimiter() -> None:
    """
    title: Docstring must open with triple backticks.
    """
    ArxIO.string_to_buffer("` \n")
    lexer = Lexer()
    with pytest.raises(LexerError, match="Invalid docstring delimiter"):
        lexer.get_token()


def test_lexer_docstring_only_two_ticks_before_content() -> None:
    """
    title: Opening fence requires three consecutive backticks.
    """
    ArxIO.string_to_buffer("``x\n")
    lexer = Lexer()
    with pytest.raises(LexerError, match="Invalid docstring delimiter"):
        lexer.get_token()


def test_lexer_float_literal_round_trip() -> None:
    """
    title: Decimal numeric lexemes become float tokens.
    """
    ArxIO.string_to_buffer("0.25\n")
    lexer = Lexer()
    assert lexer.get_token() == Token(TokenKind.float_literal, 0.25)


def test_lexer_docstring_unterminated() -> None:
    """
    title: Unterminated docstring raises LexerError.
    """
    ArxIO.string_to_buffer("```\nno closing fence\n")
    lexer = Lexer()
    with pytest.raises(LexerError, match="Unterminated docstring"):
        lexer.get_token()


def test_lexer_docstring_embedded_backticks_in_content() -> None:
    """
    title: Single and double backticks in body extend content correctly.
    """
    ArxIO.string_to_buffer("```\none` two`` tail\n```\n")
    lexer = Lexer()
    doc = lexer.get_token()
    assert doc.kind == TokenKind.docstring
    assert "`" in doc.value
    assert "``" in doc.value


def test_lexer_string_escape_sequences() -> None:
    """
    title: String literals honor common backslash escapes and pass-through.
    """
    ArxIO.string_to_buffer('"line\\n\\t\\\\\\"end"\n')
    lexer = Lexer()
    tok = lexer.get_token()
    assert tok == Token(TokenKind.string_literal, 'line\n\t\\"end')


def test_lexer_unknown_escape_passthrough_in_string() -> None:
    """
    title: Unknown escape sequences keep the escaped character.
    """
    ArxIO.string_to_buffer('"\\z"\n')
    lexer = Lexer()
    assert lexer.get_token() == Token(TokenKind.string_literal, "z")


def test_lexer_unterminated_double_quoted_string() -> None:
    """
    title: Missing closing quote before newline errors.
    """
    ArxIO.string_to_buffer('"hello\n')
    lexer = Lexer()
    with pytest.raises(LexerError, match="Unterminated quoted literal"):
        lexer.get_token()


def test_lexer_char_literal_empty_invalid() -> None:
    """
    title: Empty character literal is rejected.
    """
    ArxIO.string_to_buffer("''\n")
    lexer = Lexer()
    with pytest.raises(
        LexerError, match="Character literals must contain exactly one"
    ):
        lexer.get_token()


def test_lexer_none_is_plain_identifier_after_rename() -> None:
    """
    title: After the rename, ``none`` is tokenized as a regular identifier.
    """
    ArxIO.string_to_buffer("none\n")
    lexer = Lexer()
    tok = lexer.get_token()
    assert tok.kind == TokenKind.identifier
    assert tok.value == "none"


def test_lexer_void_is_void_literal() -> None:
    """
    title: The void keyword is tokenized as the void literal.
    """
    ArxIO.string_to_buffer("void\n")
    lexer = Lexer()
    tok = lexer.get_token()
    assert tok.kind == TokenKind.void_literal
    assert tok.value is None
