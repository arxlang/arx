"""
title: Control-flow parser mixin.
summary: >-
  Parse blocks, statements, and control-flow constructs that operate on parsed
  expressions.
"""

from __future__ import annotations

from typing import cast

from astx import SourceLocation
from irx import astx

from arx.docstrings import validate_docstring
from arx.exceptions import ParserException
from arx.lexer import Token, TokenKind
from arx.parser.base import ParserMixinBase


class ControlFlowParserMixin(ParserMixinBase):
    """
    title: Control-flow parser mixin.
    """

    def parse_block(
        self,
        allow_docstring: bool = False,
        declared_names: tuple[str, ...] = (),
    ) -> astx.Block:
        """
        title: Parse a block of nodes.
        parameters:
          allow_docstring:
            type: bool
          declared_names:
            type: tuple[str, Ellipsis]
        returns:
          type: astx.Block
        """
        start_token = self.tokens.cur_tok
        if start_token.kind != TokenKind.indent:
            raise ParserException("Expected indentation to start a block.")

        cur_indent = start_token.value
        prev_indent = self.indent_level

        if cur_indent <= prev_indent:
            raise ParserException("There is no new block to be parsed.")

        self.indent_level = cur_indent
        self.tokens.get_next_token()  # eat indentation
        self._push_value_scope(declared_names)

        block = astx.Block()
        docstring_allowed_here = allow_docstring

        try:
            while True:
                # Indentation tokens are line markers. Consume same-level
                # markers (including comment/blank lines), stop on dedent,
                # and reject unexpected over-indentation at this parsing
                # level.
                if self.tokens.cur_tok.kind == TokenKind.indent:
                    new_indent = self.tokens.cur_tok.value
                    if new_indent < cur_indent:
                        break
                    if new_indent > cur_indent:
                        raise ParserException("Indentation not allowed here.")
                    self.tokens.get_next_token()
                    continue

                if self.tokens.cur_tok.kind == TokenKind.docstring:
                    if not docstring_allowed_here:
                        raise ParserException(
                            "Docstrings are only allowed as the first "
                            "statement inside a function body."
                        )
                    try:
                        validate_docstring(self.tokens.cur_tok.value)
                    except ValueError as err:
                        raise ParserException(
                            f"Invalid function docstring: {err}"
                        ) from err
                    self.tokens.get_next_token()
                    docstring_allowed_here = False
                else:
                    node = self.parse_expression()
                    block.nodes.append(node)
                    docstring_allowed_here = False

                while self._is_operator(";"):
                    self.tokens.get_next_token()

                next_kind: TokenKind = self.tokens.cur_tok.kind
                if next_kind not in {
                    TokenKind.indent,
                    TokenKind.docstring,
                }:
                    break
        finally:
            self._pop_value_scope()
            self.indent_level = prev_indent

        return block

    def parse_if_stmt(self) -> astx.IfStmt:
        """
        title: Parse the `if` expression.
        returns:
          type: astx.IfStmt
        """
        if_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat if

        cond = self.parse_expression()
        self._consume_operator(":")

        then_block = self.parse_block()

        if self.tokens.cur_tok.kind == TokenKind.indent:
            self.tokens.get_next_token()

        else_block = astx.Block()
        if self.tokens.cur_tok.kind == TokenKind.kw_else:
            self.tokens.get_next_token()  # eat else
            self._consume_operator(":")
            else_block = self.parse_block()

        return astx.IfStmt(
            cast(astx.Expr, cond), then_block, else_block, loc=if_loc
        )

    def parse_while_stmt(self) -> astx.WhileStmt:
        """
        title: Parse the `while` expression.
        returns:
          type: astx.WhileStmt
        """
        while_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat while

        condition = self.parse_expression()
        self._consume_operator(":")
        body = self.parse_block()

        return astx.WhileStmt(cast(astx.Expr, condition), body, loc=while_loc)

    def parse_for_stmt(self) -> astx.AST:
        """
        title: Parse for-loop expressions.
        returns:
          type: astx.AST
        """
        for_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat for

        if self.tokens.cur_tok.kind == TokenKind.kw_var:
            return self.parse_for_count_stmt(for_loc)

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected identifier after for")

        var_name = cast(str, self.tokens.cur_tok.value)
        var_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat identifier

        if self.tokens.cur_tok != Token(TokenKind.kw_in, "in"):
            raise ParserException("Parser: Expected 'in' after loop variable.")

        self.tokens.get_next_token()  # eat in
        self._consume_operator("(")

        # Slice-like range header: (start:end:step)
        start = self.parse_expression()
        self._consume_operator(":")
        end = self.parse_expression()

        step: astx.AST = astx.LiteralInt32(1)
        if self._is_operator(":"):
            self._consume_operator(":")
            step = self.parse_expression()

        self._consume_operator(")")
        self._consume_operator(":")
        body = self.parse_block(declared_names=(var_name,))

        variable = astx.InlineVariableDeclaration(
            name=var_name,
            type_=astx.Int32(),
            loc=var_loc,
        )
        return astx.ForRangeLoopStmt(
            variable,
            cast(astx.Expr, start),
            cast(astx.Expr, end),
            cast(astx.Expr, step),
            body,
            loc=for_loc,
        )

    def parse_for_count_stmt(
        self, for_loc: SourceLocation
    ) -> astx.ForCountLoopStmt:
        """
        title: Parse count-style for loop.
        parameters:
          for_loc:
            type: SourceLocation
        returns:
          type: astx.ForCountLoopStmt
        """
        initializer = self.parse_inline_var_declaration()
        self._consume_operator(";")

        self._push_value_scope((initializer.name,))
        try:
            condition = self.parse_expression()
            self._consume_operator(";")

            update = self.parse_expression()
            self._consume_operator(":")

            body = self.parse_block()
        finally:
            self._pop_value_scope()

        return astx.ForCountLoopStmt(
            initializer,
            cast(astx.Expr, condition),
            cast(astx.Expr, update),
            body,
            loc=for_loc,
        )

    def parse_inline_var_declaration(self) -> astx.InlineVariableDeclaration:
        """
        title: Parse inline variable declaration used by count-style for loops.
        returns:
          type: astx.InlineVariableDeclaration
        """
        if self.tokens.cur_tok.kind != TokenKind.kw_var:
            raise ParserException("Parser: Expected 'var' in for initializer")

        var_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat var

        cur_kind: TokenKind = self.tokens.cur_tok.kind
        if cur_kind != TokenKind.identifier:
            raise ParserException("Parser: Expected identifier after var")

        name = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # eat identifier

        if not self._is_operator(":"):
            raise ParserException(
                "Parser: Expected type annotation for inline variable "
                f"'{name}'."
            )

        self._consume_operator(":")
        var_type = self.parse_type()

        self._consume_operator("=")
        value = self.parse_expression()

        return astx.InlineVariableDeclaration(
            name=name,
            type_=var_type,
            value=cast(astx.Expr, value),
            loc=var_loc,
        )

    def parse_var_expr(self) -> astx.VariableDeclaration:
        """
        title: Parse typed variable declarations.
        returns:
          type: astx.VariableDeclaration
        """
        var_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat var

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected identifier after var")

        name = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # eat identifier

        if not self._is_operator(":"):
            raise ParserException(
                f"Parser: Expected type annotation for variable '{name}'."
            )

        self._consume_operator(":")
        var_type = self.parse_type()

        value: astx.Expr | None = None
        if self._is_operator("="):
            self._consume_operator("=")
            value = cast(astx.Expr, self.parse_expression())

        if self.tokens.cur_tok == Token(TokenKind.kw_in, "in"):
            raise ParserException(
                "Legacy 'var ... in ...' syntax is not "
                "supported in this parser."
            )

        if value is None:
            value = self._default_value_for_type(var_type)

        declaration = astx.VariableDeclaration(
            name=name,
            type_=var_type,
            value=value,
            loc=var_loc,
        )
        self._declare_value_name(name)
        return declaration

    def parse_assert_stmt(self) -> astx.AssertStmt:
        """
        title: Parse one fatal assertion statement.
        returns:
          type: astx.AssertStmt
        """
        assert_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat assert
        condition = cast(astx.Expr, self.parse_expression())

        message: astx.Expr | None = None
        if self._is_operator(","):
            self._consume_operator(",")
            if self.tokens.cur_tok.kind in {
                TokenKind.eof,
                TokenKind.indent,
            }:
                raise ParserException(
                    "Expected string literal after ',' in assert statement."
                )
            message = cast(astx.Expr, self.parse_expression())
            if not isinstance(message, astx.LiteralString):
                raise ParserException(
                    "Assertion messages must be string literals."
                )

        return astx.AssertStmt(
            condition=condition,
            message=message,
            loc=assert_loc,
        )

    def parse_return_function(self) -> astx.FunctionReturn:
        """
        title: Parse the return expression.
        returns:
          type: astx.FunctionReturn
        """
        return_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat return

        bare_return_terminators = {
            TokenKind.indent,
            TokenKind.eof,
            TokenKind.kw_function,
            TokenKind.kw_class,
            TokenKind.kw_extern,
            TokenKind.kw_import,
        }
        if (
            self.tokens.cur_tok.kind in bare_return_terminators
            or self._is_operator(";")
        ):
            return astx.FunctionReturn(astx.LiteralNone(), loc=return_loc)

        value = self.parse_expression()
        return astx.FunctionReturn(cast(astx.DataType, value), loc=return_loc)
