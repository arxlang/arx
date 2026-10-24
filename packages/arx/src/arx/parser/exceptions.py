"""
title: Statement-only exception syntax.
summary: >-
  Preserve clause indentation and raise operand locations while constructing
  language-independent ASTx nodes. IRx decides exception identities and
  validity.
"""

from typing import cast

import astx

from arx.exceptions import ParserException
from arx.lexer import TokenKind
from arx.parser.base import ParserMixinBase


class ExceptionParserMixin(ParserMixinBase):
    """
    title: Parse raising and structured exception regions.
    """

    def parse_statement(self) -> astx.AST:
        """
        title: Keep exception statements out of expression operands.
        returns:
          type: astx.AST
        """
        kind = self.tokens.cur_tok.kind
        if kind == TokenKind.kw_raise:
            return self.parse_raise_stmt()
        if kind == TokenKind.kw_try:
            return self.parse_try_stmt()
        if kind in {TokenKind.kw_except, TokenKind.kw_finally}:
            raise ParserException(
                "Exception clause requires a matching try "
                "at this indentation.",
                self.tokens.cur_tok.location,
            )
        return self.parse_expression()

    def exception_expression(self) -> astx.Expr:
        """
        title: Require an expression rather than a statement-valued operand.
        returns:
          type: astx.Expr
        """
        expression = self.parse_expression()
        if not isinstance(expression, astx.Expr):
            raise ParserException(
                "Expected an exception expression.", expression.loc
            )
        return expression

    def parse_raise_stmt(self) -> astx.ThrowStmt:
        """
        title: Parse an optional exception and optional explicit cause.
        returns:
          type: astx.ThrowStmt
        """
        location = self.tokens.cur_tok.location
        self.tokens.get_next_token()
        token = self.tokens.cur_tok
        if (
            token.kind in {TokenKind.indent, TokenKind.eof}
            or token.location.line > location.line
            or self._is_operator(";")
        ):
            return astx.ThrowStmt(loc=location)
        if token.kind == TokenKind.identifier and token.value == "from":
            raise ParserException(
                "A raise cause requires an explicit exception.", token.location
            )
        exception = self.exception_expression()
        cause = None
        token = self.tokens.cur_tok
        if (
            token.kind == TokenKind.identifier
            and token.value == "from"
            and token.location.line == location.line
        ):
            self.tokens.get_next_token()
            if self.tokens.cur_tok.location.line > token.location.line:
                raise ParserException(
                    "Expected a cause after 'from'.", token.location
                )
            cause = self.exception_expression()
        token = self.tokens.cur_tok
        if (
            token.kind not in {TokenKind.indent, TokenKind.eof}
            and token.location.line == location.line
            and not self._is_operator(";")
        ):
            raise ParserException(
                "Unexpected input after raise statement.", token.location
            )
        return astx.ThrowStmt(exception, cause=cause, loc=location)

    def exception_clause(self, indentation: int) -> TokenKind | None:
        """
        title: Consume line markers only when a same-level clause follows.
        parameters:
          indentation:
            type: int
        returns:
          type: TokenKind | None
        """
        for kind in (
            TokenKind.kw_except,
            TokenKind.kw_else,
            TokenKind.kw_finally,
        ):
            if self.match_clause(kind, indentation):
                return kind
        return None

    def exception_type_reference(self) -> astx.Expr:
        """
        title: Parse a nominal or module-qualified handler type reference.
        returns:
          type: astx.Expr
        """
        token = self.tokens.cur_tok
        if token.kind != TokenKind.identifier or token.value == "as":
            raise ParserException(
                "Expected an exception type name.", token.location
            )
        reference: astx.Expr = astx.Identifier(
            cast(str, token.value), loc=token.location
        )
        self.tokens.get_next_token()
        while self._is_operator("."):
            self.tokens.get_next_token()
            token = self.tokens.cur_tok
            if token.kind != TokenKind.identifier:
                raise ParserException(
                    "Expected a name after '.'.", token.location
                )
            field = astx.FieldAccess(reference, cast(str, token.value))
            field.loc = reference.loc
            reference = field
            self.tokens.get_next_token()
        return reference

    def parse_except_clause(self) -> astx.CatchHandlerStmt:
        """
        title: Parse a handler with optional nominal types and local binding.
        returns:
          type: astx.CatchHandlerStmt
        """
        location = self.tokens.cur_tok.location
        self.tokens.get_next_token()
        if self._is_operator("*"):
            raise ParserException(
                "Exception groups and except* are not supported.", location
            )
        types: list[astx.Expr] | None = None
        name = None
        if not self._is_operator(":"):
            types = []
            if self._is_operator("("):
                self.tokens.get_next_token()
                types.append(self.exception_type_reference())
                while self._is_operator(","):
                    self.tokens.get_next_token()
                    if self._is_operator(")"):
                        break
                    types.append(self.exception_type_reference())
                self._consume_operator(")")
            else:
                types.append(self.exception_type_reference())
            token = self.tokens.cur_tok
            if token.kind == TokenKind.identifier and token.value == "as":
                self.tokens.get_next_token()
                token = self.tokens.cur_tok
                if token.kind != TokenKind.identifier:
                    raise ParserException(
                        "Expected a handler binding after 'as'.",
                        token.location,
                    )
                name = astx.Identifier(
                    cast(str, token.value), loc=token.location
                )
                self.tokens.get_next_token()
        self._consume_operator(":")
        body = self.parse_block(
            declared_names=(name.name,) if name is not None else ()
        )
        return astx.CatchHandlerStmt(body, name, types, loc=location)

    def parse_try_stmt(self) -> astx.ExceptionHandlerStmt:
        """
        title: Parse ordered handlers, optional else, and optional finally.
        returns:
          type: astx.ExceptionHandlerStmt
        """
        location = self.tokens.cur_tok.location
        indentation = location.col - 1
        self.tokens.get_next_token()
        self._consume_operator(":")
        body = self.parse_block()
        handlers: list[astx.CatchHandlerStmt] = []
        else_body = None
        finalizer = None
        kind = self.exception_clause(indentation)
        while kind == TokenKind.kw_except:
            if handlers and handlers[-1].types is None:
                raise ParserException(
                    "A bare except clause must be last.",
                    self.tokens.cur_tok.location,
                )
            handlers.append(self.parse_except_clause())
            kind = self.exception_clause(indentation)
        if kind == TokenKind.kw_else:
            if not handlers:
                raise ParserException(
                    "Try else requires at least one except clause.",
                    self.tokens.cur_tok.location,
                )
            self.tokens.get_next_token()
            self._consume_operator(":")
            else_body = self.parse_block()
            kind = self.exception_clause(indentation)
        if kind == TokenKind.kw_finally:
            final_location = self.tokens.cur_tok.location
            self.tokens.get_next_token()
            self._consume_operator(":")
            finalizer = astx.FinallyHandlerStmt(
                self.parse_block(), loc=final_location
            )
            kind = self.exception_clause(indentation)
        if kind is not None:
            raise ParserException(
                "Exception clauses must be ordered: except, else, finally.",
                self.tokens.cur_tok.location,
            )
        if not handlers and finalizer is None:
            raise ParserException(
                "Try requires an except or finally clause.", location
            )
        return astx.ExceptionHandlerStmt(
            body,
            handlers,
            finalizer,
            else_body=else_body,
            loc=location,
        )
