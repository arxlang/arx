"""parser module gather all functions and classes for parsing."""

from typing import cast

import astx

from astx import SourceLocation

from arx.exceptions import ParserException
from arx.lexer import Token, TokenKind, TokenList

INDENT_SIZE = 2


class Parser:
    """Parser class."""

    bin_op_precedence: dict[str, int] = {}
    indent_level: int = 0
    tokens: TokenList

    def __init__(self, tokens: TokenList = TokenList([])) -> None:
        """Instantiate the Parser object."""
        self.bin_op_precedence: dict[str, int] = {
            "=": 2,
            "<": 10,
            ">": 10,
            "+": 20,
            "-": 20,
            "*": 40,
        }
        self.indent_level: int = 0
        # note: it is useful to assign an initial token list here
        #       mainly for tests
        self.tokens: TokenList = tokens

    def clean(self) -> None:
        """Reset the Parser static variables."""
        self.indent_level = 0
        self.tokens: TokenList = TokenList([])

    def parse(
        self, tokens: TokenList, module_name: str = "main"
    ) -> astx.Block:
        """
        Parse the input code.

        Returns
        -------
        astx.Block
            The parsed abstract syntax tree (AST), or None if parsing fails.
        """
        self.clean()
        self.tokens = tokens

        tree: astx.Module = astx.Module(module_name)
        self.tokens.get_next_token()

        if self.tokens.cur_tok.kind == TokenKind.not_initialized:
            self.tokens.get_next_token()

        while True:
            if self.tokens.cur_tok.kind == TokenKind.eof:
                break
            elif self.tokens.cur_tok == Token(
                kind=TokenKind.operator, value=";"
            ):
                # ignore top-level semicolons.
                self.tokens.get_next_token()
            elif self.tokens.cur_tok.kind == TokenKind.kw_function:
                tree.nodes.append(self.parse_function())
            elif self.tokens.cur_tok.kind == TokenKind.kw_extern:
                tree.nodes.append(self.parse_extern())
            else:
                tree.nodes.append(self.parse_expression())

        return tree

    def get_tok_precedence(self) -> int:
        """
        Get the precedence of the pending binary operator token.

        Returns
        -------
        int
            The token precedence.
        """
        return self.bin_op_precedence.get(self.tokens.cur_tok.value, -1)

    def parse_function(self) -> astx.FunctionDef:
        """
        Parse the function definition expression.

        Returns
        -------
        astx.FunctionDef
            The parsed function definition, or None if parsing fails.
        """
        self.tokens.get_next_token()  # eat function.
        proto: astx.FunctionPrototype = self.parse_prototype()
        return astx.FunctionDef(proto, self.parse_block())

    def parse_extern(self) -> astx.FunctionPrototype:
        """
        Parse the extern expression.

        Returns
        -------
        astx.FunctionPrototype
            The parsed extern expression as a prototype, or None if parsing
            fails.
        """
        self.tokens.get_next_token()  # eat extern.
        return self.parse_extern_prototype()

    def parse_primary(self) -> astx.AST:
        """
        Parse the primary expression.

        Returns
        -------
        astx.Expr
            The parsed primary expression, or None if parsing fails.
        """
        if self.tokens.cur_tok.kind == TokenKind.identifier:
            return self.parse_identifier_expr()
        elif self.tokens.cur_tok.kind == TokenKind.float_literal:
            return self.parse_float_expr()
        elif self.tokens.cur_tok == Token(kind=TokenKind.operator, value="("):
            return self.parse_paren_expr()
        elif self.tokens.cur_tok.kind == TokenKind.kw_if:
            return self.parse_if_stmt()
        elif self.tokens.cur_tok.kind == TokenKind.kw_for:
            return self.parse_for_stmt()
        elif self.tokens.cur_tok.kind == TokenKind.kw_var:
            return self.parse_var_expr()
        elif self.tokens.cur_tok == Token(kind=TokenKind.operator, value=";"):
            # ignore top-level semicolons.
            self.tokens.get_next_token()  # eat `;`
            return self.parse_primary()
        elif self.tokens.cur_tok.kind == TokenKind.kw_return:
            return self.parse_return_function()
        elif self.tokens.cur_tok.kind == TokenKind.indent:
            return self.parse_block()
        else:
            msg: str = (
                "Parser: Unknown token when expecting an expression:"
                f"'{self.tokens.cur_tok.get_name()}'."
            )
            self.tokens.get_next_token()  # eat unknown token
            raise Exception(msg)

    def parse_block(self) -> astx.Block:
        """Parse a block of nodes."""
        cur_indent: int = self.tokens.cur_tok.value

        self.tokens.get_next_token()  # eat indentation

        block: astx.Block = astx.Block()

        if cur_indent == self.indent_level:
            raise ParserException("There is no new block to be parsed.")

        if cur_indent > self.indent_level:
            self.indent_level = cur_indent

            while expr := self.parse_expression():
                block.nodes.append(expr)
                # if isinstance(expr, astx.IfStmt):
                #     breakpoint()
                if self.tokens.cur_tok.kind != TokenKind.indent:
                    break

                new_indent = self.tokens.cur_tok.value

                if new_indent < cur_indent:
                    break

                if new_indent > cur_indent:
                    raise ParserException("Indentation not allowed here.")

                self.tokens.get_next_token()  # eat indentation

        self.indent_level -= INDENT_SIZE
        return block

    def parse_expression(self) -> astx.Expr:
        """
        Parse an expression.

        Returns
        -------
        astx.Expr
            The parsed expression, or None if parsing fails.
        """
        lhs: astx.Expr = self.parse_unary()
        return self.parse_bin_op_rhs(0, lhs)

    def parse_if_stmt(self) -> astx.IfStmt:
        """
        Parse the `if` expression.

        Returns
        -------
        astx.IfStmt
            The parsed `if` expression, or None if parsing fails.
        """
        if_loc: SourceLocation = self.tokens.cur_tok.location

        self.tokens.get_next_token()  # eat the if.

        cond: astx.Expr = self.parse_expression()

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=":"):
            msg = (
                "Parser: `if` statement expected ':', received: '"
                + str(self.tokens.cur_tok)
                + "'."
            )
            raise Exception(msg)

        self.tokens.get_next_token()  # eat the ':'

        then_block: astx.Block = astx.Block()
        else_block: astx.Block = astx.Block()

        then_block = self.parse_block()

        if self.tokens.cur_tok.kind == TokenKind.indent:
            self.tokens.get_next_token()  # eat the indentation

        if self.tokens.cur_tok.kind == TokenKind.kw_else:
            self.tokens.get_next_token()  # eat the else token

            if self.tokens.cur_tok != Token(
                kind=TokenKind.operator, value=":"
            ):
                msg = (
                    "Parser: `else` statement expected ':', received: '"
                    + str(self.tokens.cur_tok)
                    + "'."
                )
                raise Exception(msg)

            self.tokens.get_next_token()  # eat the ':'
            else_block = self.parse_block()

        return astx.IfStmt(cond, then_block, else_block, loc=if_loc)

    def parse_float_expr(self) -> astx.LiteralFloat32:
        """
        Parse the number expression.

        Returns
        -------
        astx.LiteralFloat32
            The parsed float expression.
        """
        result = astx.LiteralFloat32(self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # consume the number
        return result

    def parse_paren_expr(self) -> astx.Expr:
        """
        Parse the parenthesis expression.

        Returns
        -------
        astx.Expr
            The parsed expression.
        """
        self.tokens.get_next_token()  # eat (.
        expr = self.parse_expression()

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            raise Exception("Parser: Expected ')'")
        self.tokens.get_next_token()  # eat ).
        return expr

    def parse_identifier_expr(self) -> astx.Expr:
        """
        Parse the identifier expression.

        Returns
        -------
        astx.Expr
            The parsed expression, or None if parsing fails.
        """
        id_name: str = self.tokens.cur_tok.value

        id_loc: SourceLocation = self.tokens.cur_tok.location

        self.tokens.get_next_token()  # eat identifier.

        # TODO: var type should be dynamic
        var_type = astx.Float32()

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value="("):
            # Simple variable ref, not a function call
            # todo: we need to get the variable type from a specific scope
            return astx.Variable(id_name, var_type, loc=id_loc)

        # Call.
        self.tokens.get_next_token()  # eat (
        args: list[astx.DataType] = []

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            while True:
                args.append(cast(astx.DataType, self.parse_expression()))

                if self.tokens.cur_tok == Token(
                    kind=TokenKind.operator, value=")"
                ):
                    break

                if self.tokens.cur_tok != Token(
                    kind=TokenKind.operator, value=","
                ):
                    raise Exception(
                        "Parser: Expected ')' or ',' in argument list"
                    )
                self.tokens.get_next_token()

        # Eat the ')'.
        self.tokens.get_next_token()

        # todo: FunctionCall should accept FunctionPrototype or str
        proto_args = astx.Arguments()
        for idx in range(len(args)):
            proto_args.append(
                astx.Argument(name=f"arg_{idx}", type_=astx.Float32())
            )
        proto = astx.FunctionPrototype(
            id_name, args=proto_args, return_type=astx.Float32()
        )
        fn_def = astx.FunctionDef(proto, body=astx.Block())

        return astx.FunctionCall(fn_def, args, loc=id_loc)

    def parse_for_stmt(self) -> astx.ForRangeLoopStmt:
        """
        Parse the `for` expression.

        Returns
        -------
        astx.ForRangeLoopStmt
            The parsed `for` expression, or None if parsing fails.
        """
        self.tokens.get_next_token()  # eat the for.

        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise Exception("Parser: Expected identifier after for")

        id_name: str = self.tokens.cur_tok.value
        self.tokens.get_next_token()  # eat identifier.

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value="="):
            raise Exception("Parser: Expected '=' after for")
        self.tokens.get_next_token()  # eat '='.

        start: astx.Expr = self.parse_expression()
        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=","):
            raise Exception("Parser: Expected ',' after for start value")
        self.tokens.get_next_token()

        end: astx.Expr = self.parse_expression()

        # The step value is optional
        if self.tokens.cur_tok == Token(kind=TokenKind.operator, value=","):
            self.tokens.get_next_token()
            step = self.parse_expression()
        else:
            step = astx.LiteralFloat32(1.0)

        if self.tokens.cur_tok.kind != TokenKind.kw_in:  # type: ignore
            raise Exception("Parser: Expected 'in' after for")
        self.tokens.get_next_token()  # eat 'in'.

        body_block: astx.Block = astx.Block()
        body_block.nodes.append(self.parse_expression())
        return astx.ForRangeLoopStmt(id_name, start, end, step, body_block)

    def parse_var_expr(self) -> astx.VariableDeclaration:
        """
        Parse the `var` declaration expression.

        Returns
        -------
        astx.VariableDeclaration
            The parsed `var` expression, or None if parsing fails.
        """
        self.tokens.get_next_token()  # eat the var.

        var_names: list[tuple[str, astx.Expr]] = []

        # At least one variable name is required. #
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise Exception("Parser: Expected identifier after var")

        while True:
            name: str = self.tokens.cur_tok.value
            self.tokens.get_next_token()  # eat identifier.

            # Read the optional initializer. #
            Init: astx.Expr
            if self.tokens.cur_tok == Token(
                kind=TokenKind.operator, value="="
            ):
                self.tokens.get_next_token()  # eat the '='.

                Init = self.parse_expression()
            else:
                Init = astx.LiteralFloat32(0.0)

            var_names.append((name, Init))

            # end of var list, exit loop. #
            if self.tokens.cur_tok != Token(
                kind=TokenKind.operator, value=","
            ):
                break
            self.tokens.get_next_token()  # eat the ','.

            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise Exception("Parser: Expected identifier list after var")

        # At this point, we have to have 'in'. #
        if self.tokens.cur_tok.kind != TokenKind.kw_in:  # type: ignore
            raise Exception("Parser: Expected 'in' keyword after 'var'")
        self.tokens.get_next_token()  # eat 'in'.

        body: astx.Expr = self.parse_expression()
        return astx.VariableDeclaration(var_names, "float", body)

    def parse_unary(self) -> astx.UnaryOp:
        """
        Parse a unary expression.

        Returns
        -------
        astx.Expr
            The parsed unary expression, or None if parsing fails.
        """
        # If the current token is not an operator, it must be a primary expr.
        if (
            self.tokens.cur_tok.kind != TokenKind.operator
            or self.tokens.cur_tok.value in ("(", ",")
        ):
            return cast(astx.UnaryOp, self.parse_primary())

        # If this is a unary operator, read it.
        op_code: str = self.tokens.cur_tok.value
        self.tokens.get_next_token()
        operand = self.parse_unary()
        return astx.UnaryOp(op_code, operand)

    def parse_bin_op_rhs(
        self,
        expr_prec: int,
        lhs: astx.Expr,
    ) -> astx.Expr:
        """
        Parse a binary expression.

        Parameters
        ----------
        expr_prec : int
            Expression precedence (deprecated).
        lhs : astx.Expr
            Left-hand side expression.

        Returns
        -------
        astx.Expr
            The parsed binary expression, or None if parsing fails.
        """
        # If this is a binop, find its precedence. #
        while True:
            cur_prec: int = self.get_tok_precedence()

            # If this is a binop that binds at least as tightly as the current
            # binop, consume it, otherwise we are done.
            if cur_prec < expr_prec:
                return lhs

            # Okay, we know this is a binop.
            bin_op: str = self.tokens.cur_tok.value
            bin_loc: SourceLocation = self.tokens.cur_tok.location
            self.tokens.get_next_token()  # eat binop

            # Parse the unary expression after the binary operator.
            rhs: astx.Expr = self.parse_unary()

            # If BinOp binds less tightly with rhs than the operator after
            # rhs, let the pending operator take rhs as its lhs
            next_prec: int = self.get_tok_precedence()
            if cur_prec < next_prec:
                rhs = self.parse_bin_op_rhs(cur_prec + 1, rhs)

            # Merge lhs/rhs.
            lhs = astx.BinaryOp(
                bin_op,
                cast(astx.DataType, lhs),
                cast(astx.DataType, rhs),
                loc=bin_loc,
            )

    def parse_prototype(self) -> astx.FunctionPrototype:
        """
        Parse the prototype expression.

        Returns
        -------
        astx.FunctionPrototype
            The parsed prototype, or None if parsing fails.
        """
        fn_name: str
        var_typing: astx.DataType
        ret_typing: astx.DataType
        identifier_name: str

        cur_loc: SourceLocation
        fn_loc: SourceLocation = self.tokens.cur_tok.location

        if self.tokens.cur_tok.kind == TokenKind.identifier:
            fn_name = self.tokens.cur_tok.value
            self.tokens.get_next_token()
        else:
            raise Exception("Parser: Expected function name in prototype")

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value="("):
            raise Exception("Parser: Expected '(' in the function definition.")

        args = astx.Arguments()
        while self.tokens.get_next_token().kind == TokenKind.identifier:
            # note: this is a workaround
            identifier_name = self.tokens.cur_tok.value
            cur_loc = self.tokens.cur_tok.location

            # TODO: type should be dynamic
            var_typing = astx.Float32()

            args.append(
                astx.Argument(identifier_name, var_typing, loc=cur_loc)
            )

            if self.tokens.get_next_token() != Token(
                kind=TokenKind.operator, value=","
            ):
                break

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            raise Exception("Parser: Expected ')' in the function definition.")

        # success. #
        self.tokens.get_next_token()  # eat ')'.

        # TODO: type should be dynamic
        ret_typing = astx.Float32()

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=":"):
            raise Exception("Parser: Expected ':' in the function definition")

        self.tokens.get_next_token()  # eat ':'.

        return astx.FunctionPrototype(fn_name, args, ret_typing, loc=fn_loc)

    def parse_extern_prototype(self) -> astx.FunctionPrototype:
        """
        Parse an extern prototype expression.

        Returns
        -------
        astx.FunctionPrototype
            The parsed extern prototype, or None if parsing fails.
        """
        fn_name: str
        var_typing: astx.DataType
        ret_typing: astx.DataType
        identifier_name: str

        cur_loc: SourceLocation
        fn_loc = self.tokens.cur_tok.location

        if self.tokens.cur_tok.kind == TokenKind.identifier:
            fn_name = self.tokens.cur_tok.value
            self.tokens.get_next_token()
        else:
            raise Exception("Parser: Expected function name in prototype")

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value="("):
            raise Exception("Parser: Expected '(' in the function definition.")

        args = astx.Arguments()
        while self.tokens.get_next_token().kind == TokenKind.identifier:
            # note: this is a workaround
            identifier_name = self.tokens.cur_tok.value
            cur_loc = self.tokens.cur_tok.location

            # TODO: type should be defined dynamic
            var_typing = astx.Float32()

            args.append(
                astx.Argument(identifier_name, var_typing, loc=cur_loc)
            )

            if self.tokens.get_next_token() != Token(
                kind=TokenKind.operator, value=","
            ):
                break

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            raise Exception("Parser: Expected ')' in the function definition.")

        # success. #
        self.tokens.get_next_token()  # eat ')'.

        ret_typing = astx.Float32()

        return astx.FunctionPrototype(fn_name, args, ret_typing, loc=fn_loc)

    def parse_return_function(self) -> astx.FunctionReturn:
        """
        Parse the return expression.

        Returns
        -------
        astx.FunctionReturn
            The parsed return expression, or None if parsing fails.
        """
        self.tokens.get_next_token()  # eat return
        return astx.FunctionReturn(
            cast(astx.DataType, self.parse_expression())
        )
