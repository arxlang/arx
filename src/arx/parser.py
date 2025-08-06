"""parser module gather all functions and classes for parsing."""

from typing import Dict, List, Tuple

from arx import ast
from arx.exceptions import ParserException
from arx.lexer import SourceLocation, Token, TokenKind, TokenList

INDENT_SIZE = 2


class Parser:
    """Parser class."""

    bin_op_precedence: Dict[str, int] = {}
    indent_level: int = 0
    tokens: TokenList

    def __init__(self, tokens: TokenList = TokenList([])) -> None:
        """Instantiate the Parser object."""
        self.bin_op_precedence: Dict[str, int] = {
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
    ) -> ast.BlockAST:
        """
        Parse the input code.

        Returns
        -------
        ast.BlockAST
            The parsed abstract syntax tree (AST), or None if parsing fails.
        """
        self.clean()
        self.tokens = tokens

        tree: ast.ModuleAST = ast.ModuleAST(module_name)
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

    def parse_function(self) -> ast.FunctionAST:
        """
        Parse the function definition expression.

        Returns
        -------
        ast.FunctionAST
            The parsed function definition, or None if parsing fails.
        """
        self.tokens.get_next_token()  # eat function.
        proto: ast.PrototypeAST = self.parse_prototype()
        return ast.FunctionAST(proto, self.parse_block())

    def parse_extern(self) -> ast.PrototypeAST:
        """
        Parse the extern expression.

        Returns
        -------
        ast.PrototypeAST
            The parsed extern expression as a prototype, or None if parsing
            fails.
        """
        self.tokens.get_next_token()  # eat extern.
        return self.parse_extern_prototype()

    def parse_primary(self) -> ast.ExprAST:
        """
        Parse the primary expression.

        Returns
        -------
        ast.ExprAST
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

    def parse_block(self) -> ast.BlockAST:
        """Parse a block of nodes."""
        cur_indent: int = self.tokens.cur_tok.value

        self.tokens.get_next_token()  # eat indentation

        block: ast.BlockAST = ast.BlockAST()

        if cur_indent == self.indent_level:
            raise ParserException("There is no new block to be parsed.")

        if cur_indent > self.indent_level:
            self.indent_level = cur_indent

            while expr := self.parse_expression():
                block.nodes.append(expr)
                # if isinstance(expr, ast.IfStmtAST):
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

    def parse_expression(self) -> ast.ExprAST:
        """
        Parse an expression.

        Returns
        -------
        ast.ExprAST
            The parsed expression, or None if parsing fails.
        """
        lhs: ast.ExprAST = self.parse_unary()
        return self.parse_bin_op_rhs(0, lhs)

    def parse_if_stmt(self) -> ast.IfStmtAST:
        """
        Parse the `if` expression.

        Returns
        -------
        ast.IfStmtAST
            The parsed `if` expression, or None if parsing fails.
        """
        if_loc: SourceLocation = self.tokens.cur_tok.location

        self.tokens.get_next_token()  # eat the if.

        cond: ast.ExprAST = self.parse_expression()

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=":"):
            msg = (
                "Parser: `if` statement expected ':', received: '"
                + str(self.tokens.cur_tok)
                + "'."
            )
            raise Exception(msg)

        self.tokens.get_next_token()  # eat the ':'

        then_block: ast.BlockAST = ast.BlockAST()
        else_block: ast.BlockAST = ast.BlockAST()

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

        return ast.IfStmtAST(if_loc, cond, then_block, else_block)

    def parse_float_expr(self) -> ast.FloatExprAST:
        """
        Parse the number expression.

        Returns
        -------
        ast.FloatExprAST
            The parsed float expression.
        """
        result = ast.FloatExprAST(self.tokens.cur_tok.value)
        self.tokens.get_next_token()  # consume the number
        return result

    def parse_paren_expr(self) -> ast.ExprAST:
        """
        Parse the parenthesis expression.

        Returns
        -------
        ast.ExprAST
            The parsed expression.
        """
        self.tokens.get_next_token()  # eat (.
        expr = self.parse_expression()

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            raise Exception("Parser: Expected ')'")
        self.tokens.get_next_token()  # eat ).
        return expr

    def parse_identifier_expr(self) -> ast.ExprAST:
        """
        Parse the identifier expression.

        Returns
        -------
        ast.ExprAST
            The parsed expression, or None if parsing fails.
        """
        id_name: str = self.tokens.cur_tok.value

        id_loc: SourceLocation = self.tokens.cur_tok.location

        self.tokens.get_next_token()  # eat identifier.

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value="("):
            # Simple variable ref, not a function call
            # todo: we need to get the variable type from a specific scope
            return ast.VariableExprAST(id_loc, id_name, "float")

        # Call.
        self.tokens.get_next_token()  # eat (
        args: List[ast.ExprAST] = []
        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            while True:
                args.append(self.parse_expression())

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

        return ast.CallExprAST(id_loc, id_name, args)

    def parse_for_stmt(self) -> ast.ForStmtAST:
        """
        Parse the `for` expression.

        Returns
        -------
        ast.ForStmtAST
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

        start: ast.ExprAST = self.parse_expression()
        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=","):
            raise Exception("Parser: Expected ',' after for start value")
        self.tokens.get_next_token()

        end: ast.ExprAST = self.parse_expression()

        # The step value is optional
        if self.tokens.cur_tok == Token(kind=TokenKind.operator, value=","):
            self.tokens.get_next_token()
            step = self.parse_expression()
        else:
            step = ast.FloatExprAST(1.0)

        if self.tokens.cur_tok.kind != TokenKind.kw_in:  # type: ignore
            raise Exception("Parser: Expected 'in' after for")
        self.tokens.get_next_token()  # eat 'in'.

        body_block: ast.BlockAST = ast.BlockAST()
        body_block.nodes.append(self.parse_expression())
        return ast.ForStmtAST(id_name, start, end, step, body_block)

    def parse_var_expr(self) -> ast.VarExprAST:
        """
        Parse the `var` declaration expression.

        Returns
        -------
        ast.VarExprAST
            The parsed `var` expression, or None if parsing fails.
        """
        self.tokens.get_next_token()  # eat the var.

        var_names: List[Tuple[str, ast.ExprAST]] = []

        # At least one variable name is required. #
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise Exception("Parser: Expected identifier after var")

        while True:
            name: str = self.tokens.cur_tok.value
            self.tokens.get_next_token()  # eat identifier.

            # Read the optional initializer. #
            Init: ast.ExprAST
            if self.tokens.cur_tok == Token(
                kind=TokenKind.operator, value="="
            ):
                self.tokens.get_next_token()  # eat the '='.

                Init = self.parse_expression()
            else:
                Init = ast.FloatExprAST(0.0)

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

        body: ast.ExprAST = self.parse_expression()
        return ast.VarExprAST(var_names, "float", body)

    def parse_unary(self) -> ast.ExprAST:
        """
        Parse a unary expression.

        Returns
        -------
        ast.ExprAST
            The parsed unary expression, or None if parsing fails.
        """
        # If the current token is not an operator, it must be a primary expr.
        if (
            self.tokens.cur_tok.kind != TokenKind.operator
            or self.tokens.cur_tok.value in ("(", ",")
        ):
            return self.parse_primary()

        # If this is a unary operator, read it.
        op_code: str = self.tokens.cur_tok.value
        self.tokens.get_next_token()
        operand: ast.ExprAST = self.parse_unary()
        return ast.UnaryExprAST(op_code, operand)

    def parse_bin_op_rhs(
        self,
        expr_prec: int,
        lhs: ast.ExprAST,
    ) -> ast.ExprAST:
        """
        Parse a binary expression.

        Parameters
        ----------
        expr_prec : int
            Expression precedence (deprecated).
        lhs : ast.ExprAST
            Left-hand side expression.

        Returns
        -------
        ast.ExprAST
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
            rhs: ast.ExprAST = self.parse_unary()

            # If BinOp binds less tightly with rhs than the operator after
            # rhs, let the pending operator take rhs as its lhs
            next_prec: int = self.get_tok_precedence()
            if cur_prec < next_prec:
                rhs = self.parse_bin_op_rhs(cur_prec + 1, rhs)

            # Merge lhs/rhs.
            lhs = ast.BinaryExprAST(bin_loc, bin_op, lhs, rhs)

    def parse_prototype(self) -> ast.PrototypeAST:
        """
        Parse the prototype expression.

        Returns
        -------
        ast.PrototypeAST
            The parsed prototype, or None if parsing fails.
        """
        fn_name: str
        var_typing: str
        ret_typing: str
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

        args: List[ast.VariableExprAST] = []
        while self.tokens.get_next_token().kind == TokenKind.identifier:
            # note: this is a workaround
            identifier_name = self.tokens.cur_tok.value
            cur_loc = self.tokens.cur_tok.location

            var_typing = "float"

            args.append(
                ast.VariableExprAST(cur_loc, identifier_name, var_typing)
            )

            if self.tokens.get_next_token() != Token(
                kind=TokenKind.operator, value=","
            ):
                break

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            raise Exception("Parser: Expected ')' in the function definition.")

        # success. #
        self.tokens.get_next_token()  # eat ')'.

        ret_typing = "float"

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=":"):
            raise Exception("Parser: Expected ':' in the function definition")

        self.tokens.get_next_token()  # eat ':'.

        return ast.PrototypeAST(fn_loc, fn_name, ret_typing, args)

    def parse_extern_prototype(self) -> ast.PrototypeAST:
        """
        Parse an extern prototype expression.

        Returns
        -------
        ast.PrototypeAST
            The parsed extern prototype, or None if parsing fails.
        """
        fn_name: str
        var_typing: str
        ret_typing: str
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

        args: List[ast.VariableExprAST] = []
        while self.tokens.get_next_token().kind == TokenKind.identifier:
            # note: this is a workaround
            identifier_name = self.tokens.cur_tok.value
            cur_loc = self.tokens.cur_tok.location

            var_typing = "float"

            args.append(
                ast.VariableExprAST(cur_loc, identifier_name, var_typing)
            )

            if self.tokens.get_next_token() != Token(
                kind=TokenKind.operator, value=","
            ):
                break

        if self.tokens.cur_tok != Token(kind=TokenKind.operator, value=")"):
            raise Exception("Parser: Expected ')' in the function definition.")

        # success. #
        self.tokens.get_next_token()  # eat ')'.

        ret_typing = "float"

        return ast.PrototypeAST(fn_loc, fn_name, ret_typing, args)

    def parse_return_function(self) -> ast.ReturnStmtAST:
        """
        Parse the return expression.

        Returns
        -------
        ast.ReturnStmtAST
            The parsed return expression, or None if parsing fails.
        """
        self.tokens.get_next_token()  # eat return
        return ast.ReturnStmtAST(self.parse_expression())
