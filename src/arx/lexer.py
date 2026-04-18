"""
title: Module for handling the lexer analysis.
"""

from __future__ import annotations

import copy

from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

from astx import SourceLocation

from arx.io import ArxIO

EOF = ""


class TokenKind(Enum):
    """
    title: TokenKind enumeration for known variables returned by the lexer.
    """

    eof = -1

    # function
    kw_function = -2
    kw_extern = -3
    kw_return = -4
    kw_class = -5
    kw_import = -6
    kw_assert = -7

    # data types
    identifier = -10
    float_literal = -11
    int_literal = -12
    string_literal = -13
    char_literal = -14
    bool_literal = -15
    none_literal = -16
    docstring = -17

    # control flow
    kw_if = -20
    kw_then = -21
    kw_else = -22
    kw_for = -23
    kw_in = -24
    kw_while = -25

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
    "class": TokenKind.kw_class,
    "import": TokenKind.kw_import,
    "if": TokenKind.kw_if,
    "else": TokenKind.kw_else,
    "for": TokenKind.kw_for,
    "in": TokenKind.kw_in,
    "while": TokenKind.kw_while,
    "assert": TokenKind.kw_assert,
    "binary": TokenKind.binary_op,
    "unary": TokenKind.unary_op,
    "var": TokenKind.kw_var,
    "operator": TokenKind.operator,
}


MAP_KW_TOKEN_TO_NAME: dict[TokenKind, str] = {
    TokenKind.eof: "eof",
    TokenKind.kw_function: "function",
    TokenKind.kw_return: "return",
    TokenKind.kw_class: "class",
    TokenKind.kw_extern: "extern",
    TokenKind.kw_import: "import",
    TokenKind.kw_assert: "assert",
    TokenKind.identifier: "identifier",
    TokenKind.indent: "indent",
    TokenKind.float_literal: "float",
    TokenKind.int_literal: "int",
    TokenKind.string_literal: "string",
    TokenKind.char_literal: "char",
    TokenKind.bool_literal: "bool",
    TokenKind.none_literal: "none",
    TokenKind.docstring: "docstring",
    TokenKind.kw_if: "if",
    TokenKind.kw_then: "then",
    TokenKind.kw_else: "else",
    TokenKind.kw_for: "for",
    TokenKind.kw_in: "in",
    TokenKind.kw_while: "while",
    # TokenKind.kw_binary_op: "binary",
    # TokenKind.kw_unary_op: "unary",
    TokenKind.kw_var: "var",
    TokenKind.kw_const: "const",
}


@dataclass
class Token:
    """
    title: Token class store the kind and the value of the token.
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
    location: SourceLocation

    def __init__(
        self,
        kind: TokenKind,
        value: Any,
        location: SourceLocation = SourceLocation(0, 0),
    ) -> None:
        """
        title: Initialize Token.
        parameters:
          kind:
            type: TokenKind
          value:
            type: Any
          location:
            type: SourceLocation
        """
        self.kind = kind
        self.value = value
        self.location = copy.deepcopy(location)

    def __hash__(self) -> int:
        """
        title: Implement hash method for Token.
        returns:
          type: int
        """
        return hash(f"{self.kind}{self.value}")

    def get_name(self) -> str:
        """
        title: Get the name of the specified token.
        returns:
          type: str
          description: Name of the token.
        """
        return MAP_KW_TOKEN_TO_NAME.get(self.kind, str(self.value))

    def get_display_value(self) -> str:
        """
        title: Return the string representation of a token value.
        returns:
          type: str
          description: The string representation of the token value.
        """
        if self.kind == TokenKind.identifier:
            return "(" + str(self.value) + ")"
        if self.kind == TokenKind.indent:
            return "(" + str(self.value) + ")"
        elif self.kind == TokenKind.float_literal:
            return "(" + str(self.value) + ")"
        elif self.kind == TokenKind.int_literal:
            return "(" + str(self.value) + ")"
        elif self.kind == TokenKind.string_literal:
            return "(...)"
        elif self.kind == TokenKind.char_literal:
            return "(" + str(self.value) + ")"
        elif self.kind == TokenKind.bool_literal:
            return "(" + str(self.value) + ")"
        elif self.kind == TokenKind.none_literal:
            return ""
        elif self.kind == TokenKind.docstring:
            return "(...)"
        return ""

    def __eq__(self, other: object) -> bool:
        """
        title: Overload __eq__ operator.
        parameters:
          other:
            type: object
        returns:
          type: bool
        """
        tok_other = cast(Token, other)
        return (self.kind, self.value) == (tok_other.kind, tok_other.value)

    def __str__(self) -> str:
        """
        title: Display the token in a readable way.
        returns:
          type: str
        """
        return f"{self.get_name()}{self.get_display_value()}"


class TokenList:
    """
    title: Class for handle a List of tokens.
    attributes:
      tokens:
        type: list[Token]
      position:
        type: int
      cur_tok:
        type: Token
    """

    tokens: list[Token]
    position: int = 0
    cur_tok: Token

    def __init__(self, tokens: list[Token]) -> None:
        """
        title: Instantiate a TokenList object.
        parameters:
          tokens:
            type: list[Token]
        """
        self.tokens = tokens
        self.position = 0
        self.cur_tok: Token = Token(kind=TokenKind.not_initialized, value="")

    def __iter__(self) -> TokenList:
        """
        title: Overload the iterator operation.
        returns:
          type: TokenList
        """
        self.position = 0
        return self

    def __next__(self) -> Token:
        """
        title: Overload the next method used by the iteration.
        returns:
          type: Token
        """
        if self.position == len(self.tokens):
            raise StopIteration
        return self.get_token()

    def get_token(self) -> Token:
        """
        title: Get the next token.
        returns:
          type: Token
          description: The next token from standard input.
        """
        tok = self.tokens[self.position]
        self.position += 1
        return tok

    def get_next_token(self) -> Token:
        """
        title: Provide a simple token buffer.
        returns:
          type: Token
          description: >-
            The current token the parser is looking at. Reads another token
            from the lexer and updates cur_tok with its results.
        """
        self.cur_tok = self.get_token()
        return self.cur_tok


class LexerError(Exception):
    """
    title: Custom exception for lexer errors.
    attributes:
      location:
        description: The source location where the error occurred.
    """

    def __init__(self, message: str, location: SourceLocation):
        """
        title: Initialize LexerError.
        parameters:
          message:
            type: str
          location:
            type: SourceLocation
        """
        super().__init__(
            f"{message} at line {location.line}, col {location.col}"
        )
        self.location = location


class Lexer:
    """
    title: Lexer class for tokenizing known variables.
    attributes:
      lex_loc:
        type: SourceLocation
        description: Source location for lexer.
      last_char:
        type: str
      new_line:
        type: bool
      _keyword_map:
        type: dict[str, TokenKind]
    """

    lex_loc: SourceLocation = SourceLocation(0, 0)
    last_char: str = ""
    new_line: bool = True

    _keyword_map: dict[str, TokenKind] = {
        "fn": TokenKind.kw_function,
        "extern": TokenKind.kw_extern,
        "class": TokenKind.kw_class,
        "import": TokenKind.kw_import,
        "return": TokenKind.kw_return,
        "if": TokenKind.kw_if,
        "then": TokenKind.kw_then,
        "else": TokenKind.kw_else,
        "for": TokenKind.kw_for,
        "in": TokenKind.kw_in,
        "while": TokenKind.kw_while,
        "assert": TokenKind.kw_assert,
        "var": TokenKind.kw_var,
        "const": TokenKind.kw_const,
    }

    def __init__(self) -> None:
        """
        title: Initialize Lexer.
        """
        # self.cur_loc: SourceLocation = SourceLocation(0, 0)
        self.lex_loc: SourceLocation = SourceLocation(0, 0)
        self.last_char: str = ""
        self.new_line: bool = True

        self._keyword_map: dict[str, TokenKind] = copy.deepcopy(
            self._keyword_map
        )

    def clean(self) -> None:
        """
        title: Reset the Lexer attributes.
        """
        # self.cur_loc = SourceLocation(0, 0)
        self.lex_loc = SourceLocation(0, 0)
        self.last_char = ""
        self.new_line = True

    def get_token(self) -> Token:
        """
        title: Get the next token.
        returns:
          type: Token
          description: The next token from standard input.
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

            if identifier in ("and", "or"):
                return Token(
                    kind=TokenKind.operator,
                    value=identifier,
                    location=self.lex_loc,
                )

            if identifier == "true":
                return Token(
                    kind=TokenKind.bool_literal,
                    value=True,
                    location=self.lex_loc,
                )

            if identifier == "false":
                return Token(
                    kind=TokenKind.bool_literal,
                    value=False,
                    location=self.lex_loc,
                )

            if identifier == "none":
                return Token(
                    kind=TokenKind.none_literal,
                    value=None,
                    location=self.lex_loc,
                )

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

            if num_str == ".":
                return Token(
                    kind=TokenKind.operator,
                    value=".",
                    location=self.lex_loc,
                )

            if dot_count == 0:
                return Token(
                    kind=TokenKind.int_literal,
                    value=int(num_str),
                    location=self.lex_loc,
                )

            return Token(
                kind=TokenKind.float_literal,
                value=float(num_str),
                location=self.lex_loc,
            )

        if self.last_char in ('"', "'"):
            return self._parse_quoted_literal()

        # Docstring: ```...```
        if self.last_char == "`":
            return self._parse_docstring()

        # Comment until end of line.
        if self.last_char == "#":
            while self.last_char not in (EOF, "\n", "\r"):
                self.last_char = self.advance()

            if self.last_char != EOF:
                return self.get_token()

        if self.last_char in ("=", "!", "<", ">", "-", "&", "|", "+"):
            return self._parse_operator()

        # Check for end of file. Don't eat the EOF.
        if self.last_char:
            this_char = self.last_char
            self.last_char = self.advance()
            return Token(
                kind=TokenKind.operator, value=this_char, location=self.lex_loc
            )
        return Token(kind=TokenKind.eof, value="", location=self.lex_loc)

    def _parse_docstring(self) -> Token:
        """
        title: Parse docstrings delimited by triple backticks.
        returns:
          type: Token
        """
        doc_loc = copy.deepcopy(self.lex_loc)

        # Consume opening delimiter.
        self.last_char = self.advance()
        if self.last_char != "`":
            raise LexerError(
                "Invalid docstring delimiter. Expected ```",
                doc_loc,
            )

        self.last_char = self.advance()
        if self.last_char != "`":
            raise LexerError(
                "Invalid docstring delimiter. Expected ```",
                doc_loc,
            )

        # Move after opening delimiter.
        self.last_char = self.advance()
        content = ""

        while True:
            if self.last_char == EOF:
                raise LexerError("Unterminated docstring block", doc_loc)

            if self.last_char != "`":
                content += self.last_char
                self.last_char = self.advance()
                continue

            # We found a backtick. Check whether it starts the closing ```.
            self.last_char = self.advance()
            if self.last_char != "`":
                content += "`"
                continue

            self.last_char = self.advance()
            if self.last_char != "`":
                content += "``"
                continue

            # Closing delimiter consumed. Move to next character.
            self.last_char = self.advance()
            return Token(
                kind=TokenKind.docstring,
                value=content,
                location=doc_loc,
            )

    def _parse_quoted_literal(self) -> Token:
        """
        title: Parse quoted string or character literals.
        returns:
          type: Token
        """
        literal_loc = copy.deepcopy(self.lex_loc)
        quote = self.last_char
        self.last_char = self.advance()
        content = ""

        while self.last_char not in (quote, EOF, "\n", "\r"):
            if self.last_char == "\\":
                self.last_char = self.advance()
                escapes = {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    "\\": "\\",
                    "'": "'",
                    '"': '"',
                }
                content += escapes.get(self.last_char, self.last_char)
                self.last_char = self.advance()
                continue

            content += self.last_char
            self.last_char = self.advance()

        if self.last_char != quote:
            raise LexerError("Unterminated quoted literal", literal_loc)

        self.last_char = self.advance()

        if quote == "'":
            if len(content) != 1:
                raise LexerError(
                    "Character literals must contain exactly one character",
                    literal_loc,
                )
            return Token(
                kind=TokenKind.char_literal,
                value=content,
                location=literal_loc,
            )

        return Token(
            kind=TokenKind.string_literal,
            value=content,
            location=literal_loc,
        )

    def advance(self) -> str:
        """
        title: Advance the token from the buffer.
        returns:
          type: str
          description: TokenKind in integer form.
        """
        last_char = ArxIO.get_char()

        if last_char in ("\n", "\r"):
            self.lex_loc.line += 1
            self.lex_loc.col = 0
        else:
            self.lex_loc.col += 1

        return last_char

    def lex(self) -> TokenList:
        """
        title: Create a list of tokens from input source.
        returns:
          type: TokenList
        """
        self.clean()
        cur_tok = Token(kind=TokenKind.not_initialized, value="")
        tokens: list[Token] = []
        while cur_tok.kind != TokenKind.eof:
            cur_tok = self.get_token()
            tokens.append(cur_tok)
        return TokenList(tokens)

    def _parse_operator(self) -> Token:
        """
        title: Parse multi-character operators.
        returns:
          type: Token
        """
        location = copy.deepcopy(self.lex_loc)
        op = self.last_char
        self.last_char = self.advance()

        two_char_ops = {
            "==": "==",
            "!=": "!=",
            ">=": ">=",
            "<=": "<=",
            "->": "->",
            "&&": "&&",
            "||": "||",
            "++": "++",
            "--": "--",
        }

        if op + self.last_char in two_char_ops:
            full_op = op + self.last_char
            self.last_char = self.advance()
            return Token(
                kind=TokenKind.operator, value=full_op, location=location
            )

        return Token(kind=TokenKind.operator, value=op, location=location)
