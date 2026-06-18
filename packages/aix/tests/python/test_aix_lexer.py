# ruff: noqa: RUF001
"""
title: AIX lexer tests.
"""

from __future__ import annotations

import pytest

from aix.lexer import Lexer, LexerError, TokenKind


def kinds(source: str) -> list[TokenKind]:
    """
    title: Return token kinds excluding EOF.
    parameters:
      source:
        type: str
    returns:
      type: list[TokenKind]
    """
    return [token.kind for token in Lexer(source).tokenize().tokens[:-1]]


def test_lex_hello() -> None:
    source = '∴ main ⟦⟧ → ∅\n  ⟣ "hello"\n∎'
    assert kinds(source) == [
        TokenKind.define,
        TokenKind.identifier,
        TokenKind.semantic_lbracket,
        TokenKind.semantic_rbracket,
        TokenKind.arrow,
        TokenKind.unit,
        TokenKind.emit,
        TokenKind.string,
        TokenKind.end,
    ]


def test_lex_compact_fibonacci() -> None:
    source = "∴fib⟦n:ℕ⟧→ℕ{⊢n≤1⇒n;⊢fib⟦n-1⟧+fib⟦n-2⟧}"
    assert TokenKind.define in kinds(source)
    assert TokenKind.turnstile in kinds(source)
    assert TokenKind.implies in kinds(source)
    assert TokenKind.less_equal in kinds(source)


def test_lex_unicode_types_and_booleans() -> None:
    tokens = Lexer("ℕ ℤ ℝ ℂ 𝔹 ∅ ⊤ ⊥ true false").tokenize().tokens
    assert [token.kind for token in tokens[:-1]] == [
        TokenKind.primitive_type,
        TokenKind.primitive_type,
        TokenKind.primitive_type,
        TokenKind.primitive_type,
        TokenKind.primitive_type,
        TokenKind.unit,
        TokenKind.boolean,
        TokenKind.boolean,
        TokenKind.boolean,
        TokenKind.boolean,
    ]


def test_lex_comments_and_unicode_identifiers() -> None:
    tokens = Lexer("∴ μέain ⟦⟧ → ∅ ⍝ ignored\n∎").tokenize().tokens
    values = [token.value for token in tokens]
    assert "μέain" in values
    assert "ignored" not in values


def test_reject_unknown_glyph() -> None:
    with pytest.raises(LexerError, match="unknown symbol"):
        Lexer("☃").tokenize()
