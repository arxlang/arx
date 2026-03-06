"""
title: parser module gather all functions and classes for parsing.
"""

from __future__ import annotations

from typing import cast

import astx

from astx import SourceLocation
from astx.types import AnyType

from arx import builtins
from arx.docstrings import validate_docstring
from arx.exceptions import ParserException
from arx.lexer import Token, TokenKind, TokenList

INDENT_SIZE = 2


class Parser:
    """
    title: Parser class.
    attributes:
      bin_op_precedence:
        type: dict[str, int]
      indent_level:
        type: int
      tokens:
        type: TokenList
    """

    bin_op_precedence: dict[str, int] = {}
    indent_level: int = 0
    tokens: TokenList

    def __init__(self, tokens: TokenList = TokenList([])) -> None:
        """
        title: Instantiate the Parser object.
        parameters:
          tokens:
            type: TokenList
        """
        self.bin_op_precedence = {
            "=": 2,
            "||": 5,
            "or": 5,
            "&&": 6,
            "and": 6,
            "==": 10,
            "!=": 10,
            "<": 10,
            ">": 10,
            "<=": 10,
            ">=": 10,
            "+": 20,
            "-": 20,
            "*": 40,
            "/": 40,
        }
        self.indent_level = 0
        self.tokens = tokens

    def clean(self) -> None:
        """
        title: Reset the Parser static variables.
        """
        self.indent_level = 0
        self.tokens = TokenList([])

    def parse(
        self, tokens: TokenList, module_name: str = "main"
    ) -> astx.Block:
        """
        title: Parse the input code.
        parameters:
          tokens:
            type: TokenList
          module_name:
            type: str
        returns:
          type: astx.Block
        """
        self.clean()
        self.tokens = tokens

        tree: astx.Module = astx.Module(module_name)
        self.tokens.get_next_token()

        if self.tokens.cur_tok.kind == TokenKind.not_initialized:
            self.tokens.get_next_token()

        allow_module_docstring = True
        while True:
            if self.tokens.cur_tok.kind == TokenKind.eof:
                break
            if self.tokens.cur_tok.kind == TokenKind.docstring:
                if (
                    allow_module_docstring
                    and self.tokens.cur_tok.location.line == 0
                    and self.tokens.cur_tok.location.col == 1
                ):
                    try:
                        validate_docstring(self.tokens.cur_tok.value)
                    except ValueError as err:
                        raise ParserException(
                            f"Invalid module docstring: {err}"
                        ) from err
                    self.tokens.get_next_token()
                    allow_module_docstring = False
                    continue
                raise ParserException(
                    "Module docstrings are only allowed as the first "
                    "statement starting at line 1, column 1."
                )

            if self._is_operator(";"):
                self.tokens.get_next_token()
                allow_module_docstring = False
                continue

            if self.tokens.cur_tok.kind == TokenKind.kw_function:
                tree.nodes.append(self.parse_function())
                allow_module_docstring = False
                continue

            if self.tokens.cur_tok.kind == TokenKind.kw_extern:
                tree.nodes.append(self.parse_extern())
                allow_module_docstring = False
                continue

            tree.nodes.append(self.parse_expression())
            allow_module_docstring = False

        return tree

    def _is_operator(self, value: str) -> bool:
        return self.tokens.cur_tok == Token(
            kind=TokenKind.operator, value=value
        )

    def _consume_operator(self, value: str) -> None:
        if not self._is_operator(value):
            raise ParserException(
                f"Expected operator '{value}', got '{self.tokens.cur_tok}'."
            )
        self.tokens.get_next_token()

    def get_tok_precedence(self) -> int:
        """
        title: Get the precedence of the pending binary operator token.
        returns:
          type: int
        """
        return self.bin_op_precedence.get(self.tokens.cur_tok.value, -1)

    def parse_function(self) -> astx.FunctionDef:
        """
        title: Parse the function definition expression.
        returns:
          type: astx.FunctionDef
        """
        self.tokens.get_next_token()  # eat fn
        proto = self.parse_prototype(expect_colon=True)
        body = self.parse_block(allow_docstring=True)
        return astx.FunctionDef(proto, body)

    def parse_extern(self) -> astx.FunctionPrototype:
        """
        title: Parse the extern expression.
        returns:
          type: astx.FunctionPrototype
        """
        self.tokens.get_next_token()  # eat extern
        return self.parse_prototype(expect_colon=False)

    def parse_primary(self) -> astx.AST:
        """
        title: Parse the primary expression.
        returns:
          type: astx.AST
        """
        if self.tokens.cur_tok.kind == TokenKind.identifier:
            return self.parse_identifier_expr()
        if self.tokens.cur_tok.kind == TokenKind.int_literal:
            return self.parse_int_expr()
        if self.tokens.cur_tok.kind == TokenKind.float_literal:
            return self.parse_float_expr()
        if self.tokens.cur_tok.kind == TokenKind.string_literal:
            return self.parse_string_expr()
        if self.tokens.cur_tok.kind == TokenKind.char_literal:
            return self.parse_char_expr()
        if self.tokens.cur_tok.kind == TokenKind.bool_literal:
            return self.parse_bool_expr()
        if self.tokens.cur_tok.kind == TokenKind.none_literal:
            return self.parse_none_expr()
        if self._is_operator("("):
            return self.parse_paren_expr()
        if self._is_operator("["):
            return self.parse_list_expr()
        if self.tokens.cur_tok.kind == TokenKind.kw_if:
            return self.parse_if_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_while:
            return self.parse_while_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_for:
            return self.parse_for_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_var:
            return self.parse_var_expr()
        if self._is_operator(";"):
            self.tokens.get_next_token()
            return self.parse_primary()
        if self.tokens.cur_tok.kind == TokenKind.kw_return:
            return self.parse_return_function()
        if self.tokens.cur_tok.kind == TokenKind.indent:
            return self.parse_block()
        if self.tokens.cur_tok.kind == TokenKind.docstring:
            raise ParserException(
                "Docstrings are only allowed at module start or as the "
                "first statement inside a function body."
            )

        msg = (
            "Parser: Unknown token when expecting an expression: "
            f"'{self.tokens.cur_tok.get_name()}'."
        )
        self.tokens.get_next_token()
        raise ParserException(msg)

    def parse_block(self, allow_docstring: bool = False) -> astx.Block:
        """
        title: Parse a block of nodes.
        parameters:
          allow_docstring:
            type: bool
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

        block = astx.Block()
        docstring_allowed_here = allow_docstring

        while True:
            # Indentation tokens are line markers. Consume same-level markers
            # (including comment/blank lines), stop on dedent, and reject
            # unexpected over-indentation at this parsing level.
            if self.tokens.cur_tok.kind == TokenKind.indent:
                new_indent = self.tokens.cur_tok.value
                if new_indent < cur_indent:
                    break
                if new_indent > cur_indent:
                    raise ParserException("Indentation not allowed here.")
                self.tokens.get_next_token()  # eat same-level indentation
                continue

            if self.tokens.cur_tok.kind == TokenKind.docstring:
                if not docstring_allowed_here:
                    raise ParserException(
                        "Docstrings are only allowed as the first statement "
                        "inside a function body."
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

            next_kind: TokenKind = self.tokens.cur_tok.kind
            if next_kind not in {
                TokenKind.indent,
                TokenKind.docstring,
            }:
                break

        self.indent_level = prev_indent
        return block

    def parse_expression(self) -> astx.AST:
        """
        title: Parse an expression.
        returns:
          type: astx.AST
        """
        lhs = self.parse_unary()
        return self.parse_bin_op_rhs(0, lhs)

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

    def parse_int_expr(self) -> astx.LiteralInt32:
        """
        title: Parse the integer expression.
        returns:
          type: astx.LiteralInt32
        """
        result = astx.LiteralInt32(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_float_expr(self) -> astx.LiteralFloat32:
        """
        title: Parse the float expression.
        returns:
          type: astx.LiteralFloat32
        """
        result = astx.LiteralFloat32(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_string_expr(self) -> astx.LiteralString:
        """
        title: Parse the string expression.
        returns:
          type: astx.LiteralString
        """
        result = astx.LiteralString(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_char_expr(self) -> astx.LiteralUTF8Char:
        """
        title: Parse the char expression.
        returns:
          type: astx.LiteralUTF8Char
        """
        result = astx.LiteralUTF8Char(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_bool_expr(self) -> astx.LiteralBoolean:
        """
        title: Parse the bool expression.
        returns:
          type: astx.LiteralBoolean
        """
        result = astx.LiteralBoolean(self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        return result

    def parse_none_expr(self) -> astx.LiteralNone:
        """
        title: Parse the none expression.
        returns:
          type: astx.LiteralNone
        """
        result = astx.LiteralNone()
        self.tokens.get_next_token()
        return result

    def parse_paren_expr(self) -> astx.AST:
        """
        title: Parse the parenthesis expression.
        returns:
          type: astx.AST
        """
        self._consume_operator("(")
        expr = self.parse_expression()
        self._consume_operator(")")
        return expr

    def parse_list_expr(self) -> astx.LiteralList:
        """
        title: Parse list literals.
        returns:
          type: astx.LiteralList
        """
        self._consume_operator("[")

        elements: list[astx.Literal] = []
        if not self._is_operator("]"):
            while True:
                elem = self.parse_expression()
                if not isinstance(elem, astx.Literal):
                    raise ParserException(
                        "List literals currently support only literal "
                        "elements."
                    )
                elements.append(elem)

                if self._is_operator("]"):
                    break

                self._consume_operator(",")

        self._consume_operator("]")
        return astx.LiteralList(elements)

    def parse_identifier_expr(self) -> astx.AST:
        """
        title: Parse the identifier expression.
        returns:
          type: astx.AST
        """
        id_name = cast(str, self.tokens.cur_tok.value)
        id_loc = self.tokens.cur_tok.location

        self.tokens.get_next_token()  # eat identifier

        if not self._is_operator("("):
            return astx.Identifier(id_name, loc=id_loc)

        self._consume_operator("(")

        if id_name == builtins.BUILTIN_CAST:
            value_expr = self.parse_expression()
            self._consume_operator(",")
            target_type = self.parse_type()
            self._consume_operator(")")
            return builtins.build_cast(value_expr, target_type)

        if id_name == builtins.BUILTIN_PRINT:
            message = self.parse_expression()
            self._consume_operator(")")
            return builtins.build_print(cast(astx.Expr, message))

        if id_name in {"datetime", "timestamp"}:
            arg = self.parse_expression()
            self._consume_operator(")")
            if not isinstance(arg, astx.LiteralString):
                raise ParserException(
                    f"Builtin '{id_name}' expects a string literal argument."
                )
            if id_name == "datetime":
                return astx.LiteralDateTime(arg.value, loc=id_loc)
            return astx.LiteralTimestamp(arg.value, loc=id_loc)

        args: list[astx.DataType] = []
        if not self._is_operator(")"):
            while True:
                args.append(cast(astx.DataType, self.parse_expression()))

                if self._is_operator(")"):
                    break

                self._consume_operator(",")

        self._consume_operator(")")
        return astx.FunctionCall(id_name, args, loc=id_loc)

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
        body = self.parse_block()

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

        condition = self.parse_expression()
        self._consume_operator(";")

        update = self.parse_expression()
        self._consume_operator(":")

        body = self.parse_block()
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

        var_type: astx.DataType = astx.Float32()
        if self._is_operator(":"):
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

        var_type: astx.DataType = astx.Float32()
        if self._is_operator(":"):
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

        return astx.VariableDeclaration(
            name=name,
            type_=var_type,
            value=value,
            loc=var_loc,
        )

    def _default_value_for_type(self, data_type: astx.DataType) -> astx.Expr:
        """
        title: Build a default initializer for typed declarations.
        parameters:
          data_type:
            type: astx.DataType
        returns:
          type: astx.Expr
        """
        if isinstance(data_type, astx.Float16):
            return astx.LiteralFloat16(0.0)
        if isinstance(data_type, astx.Float32):
            return astx.LiteralFloat32(0.0)
        if isinstance(
            data_type, (astx.Int8, astx.Int16, astx.Int32, astx.Int64)
        ):
            return astx.LiteralInt32(0)
        if isinstance(data_type, astx.Boolean):
            return astx.LiteralBoolean(False)
        if isinstance(data_type, astx.String):
            return astx.LiteralString("")
        if isinstance(data_type, astx.NoneType):
            return astx.LiteralNone()
        return astx.LiteralInt32(0)

    def parse_type(self) -> astx.DataType:
        """
        title: Parse a type annotation.
        returns:
          type: astx.DataType
        """
        if self.tokens.cur_tok.kind == TokenKind.none_literal:
            self.tokens.get_next_token()  # eat none
            return astx.NoneType()

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected a type name")

        type_name = cast(str, self.tokens.cur_tok.value)

        if type_name == "list":
            self.tokens.get_next_token()  # eat list
            self._consume_operator("[")
            elem_type = self.parse_type()
            self._consume_operator("]")
            return astx.ListType([cast(astx.ExprType, elem_type)])

        type_map: dict[str, astx.DataType] = {
            "i8": astx.Int8(),
            "i16": astx.Int16(),
            "i32": astx.Int32(),
            "i64": astx.Int64(),
            "f16": astx.Float16(),
            "f32": astx.Float32(),
            "bool": astx.Boolean(),
            "none": astx.NoneType(),
            "str": astx.String(),
            "char": astx.Int8(),
            "datetime": astx.DateTime(),
            "timestamp": astx.Timestamp(),
        }

        if type_name not in type_map:
            raise ParserException(f"Parser: Unknown type '{type_name}'.")

        self.tokens.get_next_token()  # eat type identifier
        return type_map[type_name]

    def parse_unary(self) -> astx.AST:
        """
        title: Parse a unary expression.
        returns:
          type: astx.AST
        """
        if (
            self.tokens.cur_tok.kind != TokenKind.operator
            or self.tokens.cur_tok.value in ("(", "[", ",", ":", ")", "]", ";")
        ):
            return self.parse_primary()

        op_code = cast(str, self.tokens.cur_tok.value)
        self.tokens.get_next_token()
        operand = self.parse_unary()
        unary = astx.UnaryOp(op_code, cast(astx.DataType, operand))
        unary.type_ = cast(
            astx.ExprType,
            getattr(operand, "type_", astx.ExprType()),
        )
        return unary

    def parse_bin_op_rhs(self, expr_prec: int, lhs: astx.AST) -> astx.AST:
        """
        title: Parse a binary expression rhs.
        parameters:
          expr_prec:
            type: int
          lhs:
            type: astx.AST
        returns:
          type: astx.AST
        """
        while True:
            cur_prec = self.get_tok_precedence()
            if cur_prec < expr_prec:
                return lhs

            bin_op = cast(str, self.tokens.cur_tok.value)
            bin_loc = self.tokens.cur_tok.location
            self.tokens.get_next_token()  # eat operator

            rhs = self.parse_unary()

            next_prec = self.get_tok_precedence()
            if cur_prec < next_prec:
                rhs = self.parse_bin_op_rhs(cur_prec + 1, rhs)

            lhs = astx.BinaryOp(
                bin_op,
                cast(astx.DataType, lhs),
                cast(astx.DataType, rhs),
                loc=bin_loc,
            )

    def parse_prototype(self, expect_colon: bool) -> astx.FunctionPrototype:
        """
        title: Parse function/extern prototypes.
        parameters:
          expect_colon:
            type: bool
        returns:
          type: astx.FunctionPrototype
        """
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException(
                "Parser: Expected function name in prototype"
            )

        fn_name = cast(str, self.tokens.cur_tok.value)
        fn_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat function name

        self._consume_operator("(")

        args = astx.Arguments()
        if not self._is_operator(")"):
            while True:
                if self.tokens.cur_tok.kind != TokenKind.identifier:
                    raise ParserException("Parser: Expected argument name")

                arg_name = cast(str, self.tokens.cur_tok.value)
                arg_loc = self.tokens.cur_tok.location
                self.tokens.get_next_token()  # eat arg name

                if not self._is_operator(":"):
                    raise ParserException(
                        "Parser: Expected type annotation for argument "
                        f"'{arg_name}'."
                    )

                self._consume_operator(":")
                arg_type = self.parse_type()

                args.append(astx.Argument(arg_name, arg_type, loc=arg_loc))

                if self._is_operator(","):
                    self._consume_operator(",")
                    continue

                break

        self._consume_operator(")")

        ret_type: astx.DataType = astx.Float32()
        if self._is_operator("->"):
            self._consume_operator("->")
            ret_type = self.parse_type()

        if expect_colon:
            self._consume_operator(":")

        return astx.FunctionPrototype(
            fn_name, args, cast(AnyType, ret_type), loc=fn_loc
        )

    def parse_return_function(self) -> astx.FunctionReturn:
        """
        title: Parse the return expression.
        returns:
          type: astx.FunctionReturn
        """
        return_loc = self.tokens.cur_tok.location
        self.tokens.get_next_token()  # eat return
        value = self.parse_expression()
        return astx.FunctionReturn(cast(astx.DataType, value), loc=return_loc)
