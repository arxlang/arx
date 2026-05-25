# ruff: noqa: RUF001
"""
title: AIX Unicode lexer.
"""

from __future__ import annotations

import copy
import unicodedata

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Final

from astx import SourceLocation

from aix.io import AixIO

EOF_VALUE: Final[str] = ""


class TokenKind(Enum):
    """
    title: Token kinds emitted by the AIX lexer.
    """

    eof = auto()
    identifier = auto()

    integer = auto()
    float = auto()
    string = auto()
    boolean = auto()
    unit = auto()

    define = auto()
    metadata = auto()
    semantic_lbracket = auto()
    semantic_rbracket = auto()
    index_lbracket = auto()
    index_rbracket = auto()
    tuple_lbracket = auto()
    tuple_rbracket = auto()

    arrow = auto()
    turnstile = auto()
    implies = auto()
    bind = auto()
    assign = auto()
    emit = auto()
    end = auto()
    lambda_ = auto()

    colon = auto()
    comma = auto()
    semicolon = auto()
    dot = auto()
    range = auto()
    ellipsis = auto()

    lparen = auto()
    rparen = auto()
    lbrace = auto()
    rbrace = auto()

    plus = auto()
    minus = auto()
    star = auto()
    multiply = auto()
    slash = auto()
    percent = auto()
    power = auto()

    equal = auto()
    not_equal = auto()
    less = auto()
    greater = auto()
    less_equal = auto()
    greater_equal = auto()
    equivalent = auto()
    congruent = auto()

    and_ = auto()
    or_ = auto()
    not_ = auto()

    primitive_type = auto()
    symbolic_operator = auto()
    not_initialized = auto()


@dataclass
class Token:
    """
    title: Store one token kind, value, and source location.
    attributes:
      kind:
        type: TokenKind
      value:
        type: Any
      location:
        type: SourceLocation
    """

    kind: TokenKind
    value: Any
    location: SourceLocation = field(
        default_factory=lambda: SourceLocation(1, 1)
    )

    def __post_init__(self) -> None:
        """
        title: Copy location values away from mutable defaults.
        """
        self.location = copy.deepcopy(self.location)

    def __hash__(self) -> int:
        """
        title: Return a hash for this token.
        returns:
          type: int
        """
        return hash((self.kind, self.value))

    def get_name(self) -> str:
        """
        title: Return one user-facing token name.
        returns:
          type: str
        """
        return self.kind.name.removesuffix("_")

    def get_display_value(self) -> str:
        """
        title: Return a compact display value for token printing.
        returns:
          type: str
        """
        if self.kind in {
            TokenKind.identifier,
            TokenKind.integer,
            TokenKind.float,
            TokenKind.boolean,
            TokenKind.primitive_type,
            TokenKind.unit,
            TokenKind.symbolic_operator,
        }:
            return f"({self.value})"
        if self.kind == TokenKind.string:
            return "(...)"
        if self.value not in (None, "") and self.kind != TokenKind.eof:
            return f"({self.value})"
        return ""

    def __eq__(self, other: object) -> bool:
        """
        title: Compare tokens by kind and value.
        parameters:
          other:
            type: object
        returns:
          type: bool
        """
        if not isinstance(other, Token):
            return False
        return (self.kind, self.value) == (other.kind, other.value)

    def __str__(self) -> str:
        """
        title: Return one human-readable token representation.
        returns:
          type: str
        """
        return f"{self.get_name()}{self.get_display_value()}"


class TokenList:
    """
    title: Simple token stream consumed by the parser.
    attributes:
      tokens:
        type: list[Token]
      position:
        type: int
      cur_tok:
        type: Token
    """

    tokens: list[Token]
    position: int
    cur_tok: Token

    def __init__(self, tokens: list[Token]) -> None:
        """
        title: Initialize the token stream.
        parameters:
          tokens:
            type: list[Token]
        """
        self.tokens = tokens
        self.position = 0
        self.cur_tok = Token(TokenKind.not_initialized, "")

    def __iter__(self) -> TokenList:
        """
        title: Reset iteration and return this stream.
        returns:
          type: TokenList
        """
        self.position = 0
        return self

    def __next__(self) -> Token:
        """
        title: Return the next token for iteration.
        returns:
          type: Token
        """
        if self.position == len(self.tokens):
            raise StopIteration
        return self.get_token()

    def get_token(self) -> Token:
        """
        title: Return the next token and advance.
        returns:
          type: Token
        """
        token = self.tokens[self.position]
        self.position += 1
        return token

    def get_next_token(self) -> Token:
        """
        title: Advance parser cursor and return the current token.
        returns:
          type: Token
        """
        self.cur_tok = self.get_token()
        return self.cur_tok


class LexerError(Exception):
    """
    title: AIX-specific lexer error with source location.
    attributes:
      location:
        type: SourceLocation
    """

    location: SourceLocation

    def __init__(self, message: str, location: SourceLocation):
        """
        title: Initialize a lexer error.
        parameters:
          message:
            type: str
          location:
            type: SourceLocation
        """
        super().__init__(
            "AIX lexer error at line "
            f"{location.line}, column {location.col}: {message}"
        )
        self.location = location


PRIMITIVE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "ℕ",
        "ℤ",
        "ℝ",
        "ℂ",
        "𝔹",
        "i8",
        "i16",
        "i32",
        "i64",
        "u8",
        "u16",
        "u32",
        "u64",
        "f32",
        "f64",
    }
)

_RESERVED_OPERATORS: Final[frozenset[str]] = frozenset(
    {"⍴", "⍳", "¨", "∘", "↑", "↓", "⍋", "⍒", "∊", "∪", "∑", "∫", "∂"}
)

_SYMBOL_TOKENS: Final[dict[str, TokenKind]] = {
    "...": TokenKind.ellipsis,
    "..": TokenKind.range,
    "->": TokenKind.arrow,
    "<=": TokenKind.less_equal,
    ">=": TokenKind.greater_equal,
    "!=": TokenKind.not_equal,
    "==": TokenKind.equal,
    "∴": TokenKind.define,
    "κ": TokenKind.metadata,
    "⟦": TokenKind.semantic_lbracket,
    "⟧": TokenKind.semantic_rbracket,
    "⟬": TokenKind.index_lbracket,
    "⟭": TokenKind.index_rbracket,
    "⟨": TokenKind.tuple_lbracket,
    "⟩": TokenKind.tuple_rbracket,
    "→": TokenKind.arrow,
    "⊢": TokenKind.turnstile,
    "⇒": TokenKind.implies,
    "⌁": TokenKind.bind,
    "≔": TokenKind.assign,
    "⟣": TokenKind.emit,
    "∎": TokenKind.end,
    "λ": TokenKind.lambda_,
    ":": TokenKind.colon,
    ",": TokenKind.comma,
    ";": TokenKind.semicolon,
    ".": TokenKind.dot,
    "(": TokenKind.lparen,
    ")": TokenKind.rparen,
    "{": TokenKind.lbrace,
    "}": TokenKind.rbrace,
    "+": TokenKind.plus,
    "-": TokenKind.minus,
    "*": TokenKind.star,
    "×": TokenKind.multiply,
    "/": TokenKind.slash,
    "%": TokenKind.percent,
    "^": TokenKind.power,
    "=": TokenKind.equal,
    "≠": TokenKind.not_equal,
    "<": TokenKind.less,
    ">": TokenKind.greater,
    "≤": TokenKind.less_equal,
    "≥": TokenKind.greater_equal,
    "≡": TokenKind.equivalent,
    "≅": TokenKind.congruent,
    "∧": TokenKind.and_,
    "∨": TokenKind.or_,
    "¬": TokenKind.not_,
}


class Lexer:
    """
    title: Tokenize AIX source text.
    attributes:
      source:
        type: str | None
    """

    source: str | None

    def __init__(self, source: str | None = None) -> None:
        """
        title: Initialize the lexer.
        parameters:
          source:
            type: str | None
        """
        self.source = source

    def clean(self) -> None:
        """
        title: Keep API compatibility with the Arx-derived lexer.
        """

    def lex(self) -> TokenList:
        """
        title: Tokenize configured source and return a token stream.
        returns:
          type: TokenList
        """
        source = (
            self.source if self.source is not None else AixIO.buffer.buffer
        )
        return self._tokenize_source(unicodedata.normalize("NFC", source))

    def tokenize(self) -> TokenList:
        """
        title: Alias for lex used by tests and callers.
        returns:
          type: TokenList
        """
        return self.lex()

    def _tokenize_source(self, source: str) -> TokenList:
        tokens: list[Token] = []
        index = 0
        line = 1
        col = 1

        def location() -> SourceLocation:
            return SourceLocation(line, col)

        def advance() -> str:
            nonlocal index, line, col
            char = source[index]
            index += 1
            if char == "\n":
                line += 1
                col = 1
            else:
                col += 1
            return char

        while index < len(source):
            char = source[index]

            if char.isspace():
                advance()
                continue

            if char == "⍝":
                while index < len(source) and source[index] not in "\r\n":
                    advance()
                continue

            token_location = location()

            if char in {'"', "'"}:
                token, consumed = self._read_string(
                    source, index, token_location
                )
                tokens.append(token)
                for _ in range(consumed):
                    advance()
                continue

            if char.isdigit() or (
                char == "."
                and index + 1 < len(source)
                and source[index + 1].isdigit()
            ):
                number_value, kind, consumed = self._read_number(source, index)
                tokens.append(Token(kind, number_value, token_location))
                for _ in range(consumed):
                    advance()
                continue

            matched = self._match_symbol(source, index)
            if matched is not None:
                symbol, kind = matched
                symbol_value: Any = symbol
                if symbol == "⊤":
                    kind = TokenKind.boolean
                    symbol_value = True
                elif symbol == "⊥":
                    kind = TokenKind.boolean
                    symbol_value = False
                elif symbol == "∅":
                    kind = TokenKind.unit
                    symbol_value = None
                tokens.append(Token(kind, symbol_value, token_location))
                for _ in symbol:
                    advance()
                continue

            if self._is_identifier_start(char):
                identifier = char
                advance()
                while index < len(source) and self._is_identifier_part(
                    source[index]
                ):
                    identifier += source[index]
                    advance()

                if identifier in {"true", "false"}:
                    tokens.append(
                        Token(
                            TokenKind.boolean,
                            identifier == "true",
                            token_location,
                        )
                    )
                    continue
                if identifier in PRIMITIVE_TYPES:
                    tokens.append(
                        Token(
                            TokenKind.primitive_type,
                            identifier,
                            token_location,
                        )
                    )
                    continue
                tokens.append(
                    Token(TokenKind.identifier, identifier, token_location)
                )
                continue

            if char in _RESERVED_OPERATORS:
                tokens.append(
                    Token(TokenKind.symbolic_operator, char, token_location)
                )
                advance()
                continue

            raise LexerError(f"unknown symbol {char!r}", token_location)

        tokens.append(Token(TokenKind.eof, "", SourceLocation(line, col)))
        return TokenList(tokens)

    def _match_symbol(
        self, source: str, index: int
    ) -> tuple[str, TokenKind] | None:
        for symbol, kind in sorted(
            _SYMBOL_TOKENS.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if source.startswith(symbol, index):
                return symbol, kind
        if source.startswith("⊤", index):
            return "⊤", TokenKind.boolean
        if source.startswith("⊥", index):
            return "⊥", TokenKind.boolean
        if source.startswith("∅", index):
            return "∅", TokenKind.unit
        return None

    def _read_number(
        self, source: str, start: int
    ) -> tuple[int | float, TokenKind, int]:
        index = start
        dots = 0
        while index < len(source):
            char = source[index]
            if char == ".":
                dots += 1
                if dots > 1:
                    raise LexerError(
                        "invalid number format: multiple decimal points",
                        SourceLocation(1, start + 1),
                    )
                index += 1
                continue
            if not char.isdigit():
                break
            index += 1

        raw = source[start:index]
        if dots:
            return float(raw), TokenKind.float, len(raw)
        return int(raw), TokenKind.integer, len(raw)

    def _read_string(
        self, source: str, start: int, loc: SourceLocation
    ) -> tuple[Token, int]:
        quote = source[start]
        index = start + 1
        content = ""
        while index < len(source) and source[index] not in {quote, "\n", "\r"}:
            char = source[index]
            if char == "\\":
                index += 1
                if index >= len(source):
                    raise LexerError("unterminated string literal", loc)
                escapes = {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    "\\": "\\",
                    "'": "'",
                    '"': '"',
                }
                content += escapes.get(source[index], source[index])
                index += 1
                continue
            content += char
            index += 1

        if index >= len(source) or source[index] != quote:
            raise LexerError("unterminated string literal", loc)
        return Token(TokenKind.string, content, loc), index - start + 1

    def _is_identifier_start(self, char: str) -> bool:
        return char == "_" or char.isalpha()

    def _is_identifier_part(self, char: str) -> bool:
        return char == "_" or char.isalpha() or char.isdigit()
