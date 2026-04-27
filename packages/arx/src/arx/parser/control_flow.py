"""
title: Control-flow parser mixin.
summary: >-
  Parse blocks, statements, and control-flow constructs that operate on parsed
  expressions.
"""

from __future__ import annotations

from typing import cast

import astx

from astx import SourceLocation

from arx.dataframe import (
    DataFrameBinding,
    is_dataframe_type,
)
from arx.dataframe import (
    binding_from_type as dataframe_binding_from_type,
)
from arx.dataframe import (
    coerce_expression as coerce_dataframe_expression,
)
from arx.docstrings import validate_docstring
from arx.exceptions import ParserException
from arx.lexer import Token, TokenKind
from arx.parser.base import ParserMixinBase
from arx.parser.state import TypeUseContext
from arx.tensor import (
    TensorBinding,
    binding_from_type,
    is_tensor_type,
)
from arx.tensor import (
    coerce_expression as coerce_tensor_expression,
)


class ControlFlowParserMixin(ParserMixinBase):
    """
    title: Control-flow parser mixin.
    """

    def _looks_like_removed_for_range_header(self) -> bool:
        """
        title: Return whether the current token begins the removed colon range.
        returns:
          type: bool
        """
        if not self._is_operator("("):
            return False

        depth = 0
        current_index = self.tokens.position - 1
        for token in self.tokens.tokens[current_index:]:
            if token.kind != TokenKind.operator:
                continue
            if token.value == "(":
                depth += 1
                continue
            if token.value == ")":
                depth -= 1
                if depth == 0:
                    return False
                continue
            if token.value == ":" and depth == 1:
                return True
        return False

    def parse_block(
        self,
        allow_docstring: bool = False,
        declared_names: tuple[str, ...] = (),
        declared_lists: tuple[str, ...] = (),
        declared_tensors: dict[str, TensorBinding | None] | None = None,
        declared_dataframes: (
            dict[str, DataFrameBinding | None] | None
        ) = None,
    ) -> astx.Block:
        """
        title: Parse a block of nodes.
        parameters:
          allow_docstring:
            type: bool
          declared_names:
            type: tuple[str, Ellipsis]
          declared_lists:
            type: tuple[str, Ellipsis]
          declared_tensors:
            type: dict[str, TensorBinding | None] | None
          declared_dataframes:
            type: dict[str, DataFrameBinding | None] | None
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
        self._push_value_scope(
            declared_names,
            declared_lists,
            declared_tensors,
            declared_dataframes,
        )

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
        if self._looks_like_removed_for_range_header():
            raise ParserException(
                "Colon range syntax was removed; use "
                "'range(start, stop[, step])' after 'in'."
            )

        iterable = cast(astx.Expr, self.parse_expression())
        return self._parse_for_iterable_stmt(
            for_loc=for_loc,
            loop_var_name=var_name,
            loop_var_loc=var_loc,
            iterable=iterable,
        )

    def _parse_for_iterable_stmt(
        self,
        *,
        for_loc: SourceLocation,
        loop_var_name: str,
        loop_var_loc: SourceLocation,
        iterable: astx.Expr,
    ) -> astx.ForInLoopStmt:
        """
        title: Parse one generic for-in loop over a list-valued expression.
        parameters:
          for_loc:
            type: SourceLocation
          loop_var_name:
            type: str
          loop_var_loc:
            type: SourceLocation
          iterable:
            type: astx.Expr
        returns:
          type: astx.ForInLoopStmt
        """
        self._consume_operator(":")

        target = astx.Identifier(loop_var_name, loc=loop_var_loc)
        body = self.parse_block(declared_names=(loop_var_name,))
        return astx.ForInLoopStmt(
            target,
            iterable,
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

        declared_lists: tuple[str, ...] = ()
        if isinstance(initializer.type_, astx.ListType):
            declared_lists = (initializer.name,)

        declared_tensors: dict[str, TensorBinding | None] = {}
        if is_tensor_type(initializer.type_):
            binding = binding_from_type(initializer.type_)
            if binding is None:
                raise ParserException(
                    "Tensor loop initializers require a static shape."
                )
            declared_tensors[initializer.name] = binding
        declared_dataframes: dict[str, DataFrameBinding | None] = {}
        if is_dataframe_type(initializer.type_):
            declared_dataframes[initializer.name] = (
                dataframe_binding_from_type(initializer.type_)
            )

        self._push_value_scope(
            (initializer.name,),
            declared_lists,
            declared_tensors,
            declared_dataframes,
        )
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
        var_type = self.parse_type(type_context=TypeUseContext.INLINE_VARIABLE)

        self._consume_operator("=")
        try:
            raw_value = cast(astx.Expr, self.parse_expression())
            value = coerce_dataframe_expression(
                coerce_tensor_expression(
                    raw_value,
                    var_type,
                    context=f"inline variable '{name}'",
                ),
                var_type,
                context=f"inline variable '{name}'",
            )
        except ValueError as err:
            raise ParserException(str(err)) from err

        return astx.InlineVariableDeclaration(
            name=name,
            type_=var_type,
            value=value,
            mutability=astx.MutabilityKind.mutable,
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
        var_type = self.parse_type(type_context=TypeUseContext.VARIABLE)

        value: astx.Expr | None = None
        if self._is_operator("="):
            self._consume_operator("=")
            try:
                raw_value = cast(astx.Expr, self.parse_expression())
                value = coerce_dataframe_expression(
                    coerce_tensor_expression(
                        raw_value,
                        var_type,
                        context=f"variable '{name}'",
                    ),
                    var_type,
                    context=f"variable '{name}'",
                )
            except ValueError as err:
                raise ParserException(str(err)) from err

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
            mutability=astx.MutabilityKind.mutable,
            loc=var_loc,
        )
        self._declare_value_name(name)
        if is_tensor_type(var_type):
            binding = binding_from_type(var_type)
            if binding is None:
                raise ParserException(
                    "Tensor declarations require a static shape."
                )
            self._declare_tensor_name(name, binding)
        if is_dataframe_type(var_type):
            self._declare_dataframe_name(
                name,
                dataframe_binding_from_type(var_type),
            )
        if isinstance(var_type, astx.ListType):
            self._declare_list_name(name)
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
        return_type = self._current_return_type()
        if return_type is not None:
            try:
                value = coerce_dataframe_expression(
                    coerce_tensor_expression(
                        cast(astx.Expr, value),
                        return_type,
                        context="return value",
                    ),
                    return_type,
                    context="return value",
                )
            except ValueError as err:
                raise ParserException(str(err)) from err
        return astx.FunctionReturn(cast(astx.DataType, value), loc=return_loc)
