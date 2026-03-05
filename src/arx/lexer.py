"""Module for handling the lexer analysis."""

from __future__ import annotations

import copy

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, cast

from astx import SourceLocation

from arx.io import ArxIO

EOF = ""


class TokenKind(Enum):
    """TokenKind enumeration for known variables returned by the lexer."""

    eof = -1

    # function
    kw_function = -2
    kw_extern = -3
    kw_return = -4

    # data types
    identifier = -10
    float_literal = -11

    # control flow
    kw_if = -20
    kw_then = -21
    kw_else = -22
    kw_for = -23
    kw_in = -24

    # operators
    binary_op = -30
    unary_op = -31
    operator = -32

    # variables
    kw_var = -40
    kw_const = -41

    # flow and structure control
    indent = -50
    dedent = -51

    # generic control
    not_initialized = -9999


MAP_NAME_TO_KW_TOKEN = {
    "fn": TokenKind.kw_function,
    "return": TokenKind.kw_return,
    "extern": TokenKind.kw_extern,
    "if": TokenKind.kw_if,
    "else": TokenKind.kw_else,
    "for": TokenKind.kw_for,
    "in": TokenKind.kw_in,
    "binary": TokenKind.binary_op,
    "unary": TokenKind.unary_op,
    "var": TokenKind.kw_var,
    "operator": TokenKind.operator,
}


MAP_KW_TOKEN_TO_NAME: Dict[TokenKind, str] = {
    TokenKind.eof: "eof",
    TokenKind.kw_function: "function",
    TokenKind.kw_return: "return",
    TokenKind.kw_extern: "extern",
    TokenKind.identifier: "identifier",
    TokenKind.indent: "indent",
    TokenKind.float_literal: "float",
    TokenKind.kw_if: "if",
    TokenKind.kw_then: "then",
    TokenKind.kw_else: "else",
    TokenKind.kw_for: "for",
    TokenKind.kw_in: "in",
    # TokenKind.kw_binary_op: "binary",
    # TokenKind.kw_unary_op: "unary",
    TokenKind.kw_var: "var",
    TokenKind.kw_const: "const",
}


@dataclass
class Token:
    """Token class store the kind and the value of the token."""

    kind: TokenKind
    value: Any
    location: SourceLocation

    def __init__(
        self,
        kind: TokenKind,
        value: Any,
        location: SourceLocation = SourceLocation(0, 0),
    ) -> None:
        self.kind = kind
        self.value = value
        self.location = copy.deepcopy(location)

    def __hash__(self) -> int:
        """Implement hash method for Token."""
        return hash(f"{self.kind}{self.value}")

    def get_name(self) -> str:
        """
        Get the name of the specified token.

        Parameters
        ----------
        tok : int
            TokenKind value.

        Returns
        -------
        str
            Name of the token.
        """
        return MAP_KW_TOKEN_TO_NAME.get(self.kind, str(self.value))

    def get_display_value(self) -> str:
        """
        Return the string representation of a token value.

        Returns
        -------
            str: The string representation of the token value.
        """
        if self.kind == TokenKind.identifier:
            return "(" + str(self.value) + ")"
        if self.kind == TokenKind.indent:
            return "(" + str(self.value) + ")"
        elif self.kind == TokenKind.float_literal:
            return "(" + str(self.value) + ")"
        return ""

    def __eq__(self, other: object) -> bool:
        """Overload __eq__ operator."""
        tok_other = cast(Token, other)
        return (self.kind, self.value) == (tok_other.kind, tok_other.value)

    def __str__(self) -> str:
        """Display the token in a readable way."""
        return f"{self.get_name()}{self.get_display_value()}"


class TokenList:
    """Class for handle a List of tokens."""

    tokens: List[Token]
    position: int = 0
    cur_tok: Token

    def __init__(self, tokens: List[Token]) -> None:
        """Instantiate a TokenList object."""
        self.tokens = tokens
        self.position = 0
        self.cur_tok: Token = Token(kind=TokenKind.not_initialized, value="")

    def __iter__(self) -> TokenList:
        """Overload the iterator operation."""
        self.position = 0
        return self

    def __next__(self) -> Token:
        """Overload the next method used by the iteration."""
        if self.position == len(self.tokens):
            raise StopIteration
        return self.get_token()

    def get_token(self) -> Token:
        """
        Get the next token.

        Returns
        -------
        int
            The next token from standard input.
        """
        tok = self.tokens[self.position]
        self.position += 1
        return tok

    def get_next_token(self) -> Token:
        """
        Provide a simple token buffer.

        Returns
        -------
        int
            The current token the parser is looking at.
            Reads another token from the lexer and updates
            cur_tok with its results.
        """
        self.cur_tok = self.get_token()
        return self.cur_tok


class LexerError(Exception):
    """Custom exception for lexer errors."""

    def __init__(self, message: str, location: SourceLocation):
        super().__init__(
            f"{message} at line {location.line}, col {location.col}"
        )
        self.location = location


class Lexer:
    """
    Lexer class for tokenizing known variables.

    Attributes
    ----------
    cur_loc : SourceLocation
        Current source location.
    lex_loc : SourceLocation
        Source location for lexer.
    """

    lex_loc: SourceLocation = SourceLocation(0, 0)
    last_char: str = ""
    new_line: bool = True

    _keyword_map: Dict[str, TokenKind] = {
        "fn": TokenKind.kw_function,
        "extern": TokenKind.kw_extern,
        "return": TokenKind.kw_return,
        "if": TokenKind.kw_if,
        "then": TokenKind.kw_then,
        "else": TokenKind.kw_else,
        "for": TokenKind.kw_for,
        "in": TokenKind.kw_in,
        "var": TokenKind.kw_var,
        "const": TokenKind.kw_const,
    }

    def __init__(self) -> None:
        # self.cur_loc: SourceLocation = SourceLocation(0, 0)
        self.lex_loc: SourceLocation = SourceLocation(0, 0)
        self.last_char: str = ""
        self.new_line: bool = True

        self._keyword_map: Dict[str, TokenKind] = copy.deepcopy(
            self._keyword_map
        )

    def clean(self) -> None:
        """Reset the Lexer attributes."""
        # self.cur_loc = SourceLocation(0, 0)
        self.lex_loc = SourceLocation(0, 0)
        self.last_char = ""
        self.new_line = True

    def get_token(self) -> Token:
        """
        Get the next token.

        Returns
        -------
        int
            The next token from standard input.
        """
        if self.last_char == "":
            self.new_line = True
            self.last_char = self.advance()

        # Skip any whitespace.
        indent = 0
        while self.last_char.isspace():
            if self.new_line:
                indent += 1

            if self.last_char == "\n":
                # note: if it is an empty line it is not necessary to keep
                #       the record about the indentation
                self.new_line = True
                indent = 0

            self.last_char = self.advance()

        self.new_line = False

        if indent:
            return Token(
                kind=TokenKind.indent, value=indent, location=self.lex_loc
            )

        # self.cur_loc = self.lex_loc

        if self.last_char.isalpha() or self.last_char == "_":
            # Identifier
            identifier = self.last_char
            self.last_char = self.advance()

            while self.last_char.isalnum() or self.last_char == "_":
                identifier += self.last_char
                self.last_char = self.advance()

            if identifier in self._keyword_map:
                return Token(
                    kind=self._keyword_map[identifier],
                    value=identifier,
                    location=self.lex_loc,
                )

            return Token(
                kind=TokenKind.identifier,
                value=identifier,
                location=self.lex_loc,
            )

        # Number: [0-9.]+
        if self.last_char.isdigit() or self.last_char == ".":
            num_str = ""
            dot_count = 0

            while self.last_char.isdigit() or self.last_char == ".":
                if self.last_char == ".":
                    dot_count += 1
                    if dot_count > 1:
                        raise LexerError(
                            "Invalid number format: multiple decimal points",
                            self.lex_loc,
                        )
                num_str += self.last_char
                self.last_char = self.advance()

            return Token(
                kind=TokenKind.float_literal,
                value=float(num_str),
                location=self.lex_loc,
            )

        # Comment until end of line.
        if self.last_char == "#":
            while self.last_char not in (EOF, "\n", "\r"):
                self.last_char = self.advance()

            if self.last_char != EOF:
                return self.get_token()

        # Check for end of file. Don't eat the EOF.
        if self.last_char:
            this_char = self.last_char
            self.last_char = self.advance()
            return Token(
                kind=TokenKind.operator, value=this_char, location=self.lex_loc
            )
        return Token(kind=TokenKind.eof, value="", location=self.lex_loc)

    def advance(self) -> str:
        """
        Advance the token from the buffer.

        Returns
        -------
        int
            TokenKind in integer form.
        """
        last_char = ArxIO.get_char()

        if last_char in ("\n", "\r"):
            self.lex_loc.line += 1
            self.lex_loc.col = 0
        else:
            self.lex_loc.col += 1

        return last_char

    def lex(self) -> TokenList:
        """Create a list of tokens from input source."""
        self.clean()
        cur_tok = Token(kind=TokenKind.not_initialized, value="")
        tokens: List[Token] = []
        while cur_tok.kind != TokenKind.eof:
            cur_tok = self.get_token()
            tokens.append(cur_tok)
        return TokenList(tokens)

    def _parse_operator(self) -> Token:
        """Parse multi-character operators."""
        location = copy.deepcopy(self.lex_loc)
        op = self.last_char
        self.last_char = self.advance()

        two_char_ops = {
            "==": "eq",
            "!=": "ne",
            ">=": "ge",
            "<=": "le",
            "->": "arrow",
            "//": "comment",
        }

        if op + self.last_char in two_char_ops:
            full_op = op + self.last_char
            self.last_char = self.advance()
            return Token(
                kind=TokenKind.operator, value=full_op, location=location
            )

        return Token(kind=TokenKind.operator, value=op, location=location)
