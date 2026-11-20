# ruff: noqa: RUF001
"""
title: AIX Unicode lexer.
attributes:
  EOF_VALUE: Eof value.
  PRIMITIVE_TYPES: Primitive types.
  _RESERVED_OPERATORS: Reserved operators.
  _SYMBOL_TOKENS: Symbol tokens.
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
      kind: Kind of value or operation.
      value: Stored value.
      location: Source location attached to this record.
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
        returns: Hash of this instance.
        """
        return hash((self.kind, self.value))

    def get_name(self) -> str:
        """
        title: Return one user-facing token name.
        returns: One user-facing token name.
        """
        return self.kind.name.removesuffix("_")

    def get_display_value(self) -> str:
        """
        title: Return a compact display value for token printing.
        returns: A compact display value for token printing.
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
          other: Other value participating in the operation.
        returns: Whether the values are equal.
        """
        if not isinstance(other, Token):
            return False
        return (self.kind, self.value) == (other.kind, other.value)

    def __str__(self) -> str:
        """
        title: Return one human-readable token representation.
        returns: String representation of this instance.
        """
        return f"{self.get_name()}{self.get_display_value()}"


class TokenList:
    """
    title: Simple token stream consumed by the parser.
    attributes:
      tokens: Tokens in source order.
      position: Position.
      cur_tok: Cur tok.
    """

    tokens: list[Token]
    position: int
    cur_tok: Token

    def __init__(self, tokens: list[Token]) -> None:
        """
        title: Initialize the token stream.
        parameters:
          tokens: Tokens in source order.
        """
        self.tokens = tokens
        self.position = 0
        self.cur_tok = Token(TokenKind.not_initialized, "")

    def __iter__(self) -> TokenList:
        """
        title: Reset iteration and return this stream.
        returns: Iterator over the contained items.
        """
        self.position = 0
        return self

    def __next__(self) -> Token:
        """
        title: Return the next token for iteration.
        returns: Next item from the iterator.
        """
        if self.position == len(self.tokens):
            raise StopIteration
        return self.get_token()

    def get_token(self) -> Token:
        """
        title: Return the next token and advance.
        returns: The next token and advance.
        """
        token = self.tokens[self.position]
        self.position += 1
        return token

    def get_next_token(self) -> Token:
        """
        title: Advance parser cursor and return the current token.
        returns: 'Result of this operation: advance parser cursor and return
          the current token.'
        """
        self.cur_tok = self.get_token()
        return self.cur_tok


class LexerError(Exception):
    """
    title: AIX-specific lexer error with source location.
    attributes:
      location: Source location attached to this record.
    """

    location: SourceLocation

    def __init__(self, message: str, location: SourceLocation) -> None:
        """
        title: Initialize a lexer error.
        parameters:
          message: Diagnostic or output message.
          location: Source coordinates associated with the operation.
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
      source: Source input to process.
    """

    source: str | None

    def __init__(self, source: str | None = None) -> None:
        """
        title: Initialize the lexer.
        parameters:
          source: Source input to process.
        """
        self.source = source

    def clean(self) -> None:
        """
        title: Keep API compatibility with the Arx-derived lexer.
        """

    def lex(self) -> TokenList:
        """
        title: Tokenize configured source and return a token stream.
        returns: 'Result of this operation: tokenize configured source and
          return a token stream.'
        """
        source = (
            self.source if self.source is not None else AixIO.buffer.buffer
        )
        return self._tokenize_source(unicodedata.normalize("NFC", source))

    def tokenize(self) -> TokenList:
        """
        title: Alias for lex used by tests and callers.
        returns: 'Result of this operation: alias for lex used by tests and
          callers.'
        """
        return self.lex()

    def _tokenize_source(self, source: str) -> TokenList:
        """
        title: Tokenize the complete source buffer.
        visibility: internal
        parameters:
          source: Source input to process.
        returns: 'Result of this operation: tokenize the complete source
          buffer.'
        """
        tokens: list[Token] = []
        index = 0
        line = 1
        col = 1

        def location() -> SourceLocation:
            """
            title: Return the current source coordinates.
            visibility: internal
            returns: The current source coordinates.
            """
            return SourceLocation(line, col)

        def advance() -> str:
            """
            title: Advance source coordinates across consumed text.
            visibility: internal
            returns: 'Result of this operation: advance source coordinates
              across consumed text.'
            """
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
        """
        title: Match a reserved symbol at the current source offset.
        visibility: internal
        parameters:
          source: Source input to process.
          index: Index selecting the item.
        returns: 'Result of this operation: match a reserved symbol at the
          current source offset.'
        """
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
        """
        title: Read a numeric literal from the source buffer.
        visibility: internal
        parameters:
          source: Source input to process.
          start: Starting position.
        returns: Read a numeric literal from the source buffer.
        """
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
        """
        title: Read a quoted string and reject unterminated input.
        visibility: internal
        parameters:
          source: Source input to process.
          start: Starting position.
          loc: Source coordinates associated with the node.
        returns: Read a quoted string and reject unterminated input.
        """
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
        """
        title: Check whether a character can start an identifier.
        visibility: internal
        parameters:
          char: Char.
        returns: Whether a character can start an identifier.
        """
        return char == "_" or char.isalpha()

    def _is_identifier_part(self, char: str) -> bool:
        """
        title: Check whether a character can continue an identifier.
        visibility: internal
        parameters:
          char: Char.
        returns: Whether a character can continue an identifier.
        """
        return char == "_" or char.isalpha() or char.isdigit()
