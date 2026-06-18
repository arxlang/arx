# ruff: noqa: RUF001
"""
title: AIX recursive-descent parser.
"""

from __future__ import annotations

from typing import Final, NoReturn, cast

import astx

from astx.types import AnyType

from aix import builtins
from aix.exceptions import ParserException
from aix.lexer import Token, TokenKind, TokenList

_TYPE_MAP: Final[dict[str, type[astx.DataType]]] = {
    "ℕ": astx.Int64,
    "ℤ": astx.Int64,
    "ℝ": astx.Float64,
    "𝔹": astx.Boolean,
    "i8": astx.Int8,
    "i16": astx.Int16,
    "i32": astx.Int32,
    "i64": astx.Int64,
    "u8": astx.UInt8,
    "u16": astx.UInt16,
    "u32": astx.UInt32,
    "u64": astx.UInt64,
    "f32": astx.Float32,
    "f64": astx.Float64,
    "bool": astx.Boolean,
    "boolean": astx.Boolean,
    "none": astx.NoneType,
    "str": astx.String,
    "string": astx.String,
}

_BINARY_OPERATORS: Final[dict[TokenKind, tuple[int, str, bool]]] = {
    TokenKind.or_: (10, "or", False),
    TokenKind.and_: (20, "and", False),
    TokenKind.equal: (30, "==", False),
    TokenKind.not_equal: (30, "!=", False),
    TokenKind.less: (30, "<", False),
    TokenKind.greater: (30, ">", False),
    TokenKind.less_equal: (30, "<=", False),
    TokenKind.greater_equal: (30, ">=", False),
    TokenKind.equivalent: (30, "==", False),
    TokenKind.congruent: (30, "==", False),
    TokenKind.plus: (40, "+", False),
    TokenKind.minus: (40, "-", False),
    TokenKind.star: (50, "*", False),
    TokenKind.multiply: (50, "*", False),
    TokenKind.slash: (50, "/", False),
    TokenKind.percent: (50, "%", False),
    TokenKind.power: (60, "^", True),
}

_EXPRESSION_TERMINATORS: Final[frozenset[TokenKind]] = frozenset(
    {
        TokenKind.eof,
        TokenKind.semantic_rbracket,
        TokenKind.index_rbracket,
        TokenKind.tuple_rbracket,
        TokenKind.rparen,
        TokenKind.rbrace,
        TokenKind.comma,
        TokenKind.semicolon,
        TokenKind.end,
        TokenKind.turnstile,
        TokenKind.implies,
        TokenKind.bind,
        TokenKind.emit,
        TokenKind.define,
    }
)

_STATEMENT_STARTERS: Final[frozenset[TokenKind]] = frozenset(
    {
        TokenKind.turnstile,
        TokenKind.bind,
        TokenKind.emit,
        TokenKind.identifier,
        TokenKind.integer,
        TokenKind.float,
        TokenKind.string,
        TokenKind.boolean,
        TokenKind.unit,
        TokenKind.lparen,
        TokenKind.minus,
        TokenKind.not_,
    }
)


class Parser:
    """
    title: Parse AIX tokens into IRx/ASTx-compatible AST nodes.
    attributes:
      tokens:
        type: TokenList
    """

    tokens: TokenList

    def __init__(self, tokens: TokenList | None = None) -> None:
        """
        title: Initialize parser state.
        parameters:
          tokens:
            type: TokenList | None
        """
        self.tokens = tokens or TokenList([])

    def clean(self) -> None:
        """
        title: Reset parser state.
        """
        self.tokens = TokenList([])

    def parse(
        self, tokens: TokenList, module_name: str = "main"
    ) -> astx.Module:
        """
        title: Parse a token stream into an AST module.
        parameters:
          tokens:
            type: TokenList
          module_name:
            type: str
        returns:
          type: astx.Module
        """
        self.tokens = tokens
        module = astx.Module(module_name)
        self.tokens.get_next_token()

        while not self._at(TokenKind.eof):
            self._skip_separators()
            if self._at(TokenKind.eof):
                break
            if self._at(TokenKind.metadata):
                self._parse_metadata_block()
                self._skip_separators()
                continue
            if not self._at(TokenKind.define):
                self._raise_here("expected definition marker '∴'")
            module.append(self._parse_definition())

        return module

    def _parse_metadata_block(self) -> None:
        self._consume(TokenKind.metadata, "κ")
        self._consume(TokenKind.semantic_lbracket, "⟦")
        depth = 1
        while depth:
            if self._at(TokenKind.eof):
                self._raise_here("unterminated metadata block, expected '⟧'")
            if self._at(TokenKind.semantic_lbracket):
                depth += 1
            elif self._at(TokenKind.semantic_rbracket):
                depth -= 1
            self.tokens.get_next_token()

    def _parse_definition(self) -> astx.AST:
        self._consume(TokenKind.define, "∴")
        name_token = self._expect(TokenKind.identifier, "definition name")
        name = cast(str, name_token.value)

        if self._at(TokenKind.semantic_lbracket):
            return self._parse_function_definition(name, name_token)
        if self._at(TokenKind.colon):
            return self._parse_constant_definition(name, name_token)

        self._raise_here(
            "expected parameter block '⟦...⟧' or type annotation ':' "
            f"after definition name '{name}'"
        )

    def _parse_function_definition(
        self, name: str, name_token: Token
    ) -> astx.FunctionDef:
        args = self._parse_parameter_block()
        return_type: astx.DataType = astx.NoneType()
        if self._at(TokenKind.arrow):
            self.tokens.get_next_token()
            return_type = self._parse_type_expression()

        body = self._parse_function_body()
        prototype = astx.FunctionPrototype(
            name,
            args,
            cast(AnyType, return_type),
            loc=name_token.location,
        )
        return astx.FunctionDef(prototype, body, loc=name_token.location)

    def _parse_constant_definition(
        self, name: str, name_token: Token
    ) -> astx.VariableDeclaration:
        self._consume(TokenKind.colon, ":")
        type_ = self._parse_type_expression()
        self._consume(TokenKind.assign, "≔")
        value = cast(astx.Expr, self.parse_expression())
        if self._at(TokenKind.end):
            self.tokens.get_next_token()
        return astx.VariableDeclaration(
            name=name,
            type_=type_,
            value=value,
            mutability=astx.MutabilityKind.constant,
            loc=name_token.location,
        )

    def _parse_parameter_block(self) -> astx.Arguments:
        self._consume(TokenKind.semantic_lbracket, "⟦")
        args = astx.Arguments()
        if self._at(TokenKind.semantic_rbracket):
            self.tokens.get_next_token()
            return args

        while True:
            param_token = self._expect(TokenKind.identifier, "parameter name")
            param_name = cast(str, param_token.value)
            self._consume(TokenKind.colon, ":")
            param_type = self._parse_type_expression()
            args.append(
                astx.Argument(param_name, param_type, loc=param_token.location)
            )

            if self._at(TokenKind.comma):
                self.tokens.get_next_token()
                if self._at(TokenKind.semantic_rbracket):
                    break
                continue
            break

        self._consume(TokenKind.semantic_rbracket, "⟧")
        return args

    def _parse_type_expression(self) -> astx.DataType:
        token = self.tokens.cur_tok
        if token.kind == TokenKind.unit:
            self.tokens.get_next_token()
            return astx.NoneType(loc=token.location)

        if token.kind not in {TokenKind.primitive_type, TokenKind.identifier}:
            self._raise_here("expected type expression")

        type_name = cast(str, token.value)
        self.tokens.get_next_token()

        if type_name == "ℂ":
            raise ParserException(
                self._message_at(
                    token,
                    "AIX parser recognized 'ℂ', but complex numbers are "
                    "not supported by the current IRx backend yet.",
                )
            )

        type_factory = _TYPE_MAP.get(type_name)
        if type_factory is None:
            raise ParserException(
                self._message_at(token, f"unknown AIX type '{type_name}'")
            )
        return type_factory(loc=token.location)

    def _parse_function_body(self) -> astx.Block:
        if self._at(TokenKind.lbrace):
            return self._parse_inline_block()
        return self._parse_block_until_end()

    def _parse_inline_block(self) -> astx.Block:
        self._consume(TokenKind.lbrace, "{")
        block = astx.Block()
        while not self._at(TokenKind.rbrace):
            if self._at(TokenKind.eof):
                self._raise_here("missing closing '}' for inline block")
            self._skip_separators()
            if self._at(TokenKind.rbrace):
                break
            block.append(self._parse_statement())
            self._skip_separators()
        self._consume(TokenKind.rbrace, "}")
        return block

    def _parse_block_until_end(self) -> astx.Block:
        block = astx.Block()
        while not self._at(TokenKind.end):
            if self._at(TokenKind.eof):
                self._raise_here("missing block terminator '∎'")
            self._skip_separators()
            if self._at(TokenKind.end):
                break
            if self.tokens.cur_tok.kind not in _STATEMENT_STARTERS:
                self._raise_here("expected statement or block terminator '∎'")
            block.append(self._parse_statement())
            self._skip_separators()
        self._consume(TokenKind.end, "∎")
        return block

    def _parse_statement(self) -> astx.AST:
        if self._at(TokenKind.turnstile):
            return self._parse_branch_statement()
        if self._at(TokenKind.bind):
            return self._parse_binding_statement()
        if self._at(TokenKind.emit):
            return self._parse_emit_statement()
        if (
            self.tokens.cur_tok.kind == TokenKind.identifier
            and self._peek().kind == TokenKind.assign
        ):
            return self._parse_assignment_statement()
        return self.parse_expression()

    def _parse_branch_statement(self) -> astx.AST:
        branch_token = self.tokens.cur_tok
        self._consume(TokenKind.turnstile, "⊢")
        first = cast(astx.Expr, self.parse_expression())
        if not self._at(TokenKind.implies):
            return astx.FunctionReturn(
                cast(astx.DataType, first),
                branch_token.location,
            )

        self._consume(TokenKind.implies, "⇒")
        value = cast(astx.Expr, self.parse_expression())
        then_block = astx.Block()
        then_block.append(
            astx.FunctionReturn(
                cast(astx.DataType, value),
                branch_token.location,
            )
        )
        return astx.IfStmt(
            first,
            then_block,
            astx.Block(),
            loc=branch_token.location,
        )

    def _parse_binding_statement(self) -> astx.VariableDeclaration:
        bind_token = self.tokens.cur_tok
        self._consume(TokenKind.bind, "⌁")
        name_token = self._expect(TokenKind.identifier, "binding name")
        name = cast(str, name_token.value)
        type_: astx.DataType | None = None
        if self._at(TokenKind.colon):
            self.tokens.get_next_token()
            type_ = self._parse_type_expression()
        self._consume(TokenKind.assign, "≔")
        value = cast(astx.Expr, self.parse_expression())
        return astx.VariableDeclaration(
            name=name,
            type_=type_ or self._infer_type(value),
            value=value,
            mutability=astx.MutabilityKind.mutable,
            loc=bind_token.location,
        )

    def _parse_assignment_statement(self) -> astx.VariableAssignment:
        name_token = self._expect(TokenKind.identifier, "assignment target")
        self._consume(TokenKind.assign, "≔")
        value = cast(astx.Expr, self.parse_expression())
        return astx.VariableAssignment(
            cast(str, name_token.value),
            value,
            loc=name_token.location,
        )

    def _parse_emit_statement(self) -> astx.AST:
        self._consume(TokenKind.emit, "⟣")
        expr = cast(astx.Expr, self.parse_expression())
        return cast(astx.AST, builtins.build_print(expr))

    def parse_expression(self, min_precedence: int = 0) -> astx.AST:
        """
        title: Parse an AIX expression.
        parameters:
          min_precedence:
            type: int
        returns:
          type: astx.AST
        """
        lhs = self._parse_unary()

        while True:
            op_info = _BINARY_OPERATORS.get(self.tokens.cur_tok.kind)
            if op_info is None:
                return lhs

            precedence, op_code, right_associative = op_info
            if precedence < min_precedence:
                return lhs

            op_token = self.tokens.cur_tok
            self.tokens.get_next_token()
            rhs = self.parse_expression(
                precedence if right_associative else precedence + 1
            )
            lhs = astx.BinaryOp(
                op_code,
                cast(astx.DataType, lhs),
                cast(astx.DataType, rhs),
                loc=op_token.location,
            )

    def _parse_unary(self) -> astx.AST:
        token = self.tokens.cur_tok
        if token.kind == TokenKind.minus:
            self.tokens.get_next_token()
            return astx.UnaryOp(
                "-",
                cast(astx.DataType, self._parse_unary()),
                loc=token.location,
            )
        if token.kind == TokenKind.not_:
            self.tokens.get_next_token()
            return astx.UnaryOp(
                "not",
                cast(astx.DataType, self._parse_unary()),
                loc=token.location,
            )
        if token.kind == TokenKind.symbolic_operator:
            self._raise_reserved_operator(token)
        return self._parse_postfix()

    def _parse_postfix(self) -> astx.AST:
        expr = self._parse_primary()
        while True:
            if self._at(TokenKind.semantic_lbracket):
                expr = self._parse_call_suffix(expr)
                continue
            if self._at(TokenKind.index_lbracket):
                self._raise_here(
                    "index expressions using '⟬...⟭' are reserved but "
                    "not implemented yet"
                )
            if self._at(TokenKind.dot):
                self._raise_here(
                    "field access is reserved for a future AIX version"
                )
            return expr

    def _parse_call_suffix(self, callee: astx.AST) -> astx.FunctionCall:
        if not isinstance(callee, astx.Identifier):
            self._raise_here("only identifier function calls are supported")
        call_loc = self.tokens.cur_tok.location
        self._consume(TokenKind.semantic_lbracket, "⟦")
        args: list[astx.DataType] = []
        if not self._at(TokenKind.semantic_rbracket):
            while True:
                args.append(cast(astx.DataType, self.parse_expression()))
                if self._at(TokenKind.comma):
                    self.tokens.get_next_token()
                    if self._at(TokenKind.semantic_rbracket):
                        break
                    continue
                break
        self._consume(TokenKind.semantic_rbracket, "⟧")
        return astx.FunctionCall(callee.name, args, loc=call_loc)

    def _parse_primary(self) -> astx.AST:
        token = self.tokens.cur_tok
        if token.kind in _EXPRESSION_TERMINATORS:
            self._raise_here("expected expression")
        if token.kind == TokenKind.integer:
            self.tokens.get_next_token()
            return astx.LiteralInt64(
                cast(int, token.value),
                loc=token.location,
            )
        if token.kind == TokenKind.float:
            self.tokens.get_next_token()
            return astx.LiteralFloat64(
                cast(float, token.value),
                loc=token.location,
            )
        if token.kind == TokenKind.string:
            self.tokens.get_next_token()
            return astx.LiteralString(
                cast(str, token.value),
                loc=token.location,
            )
        if token.kind == TokenKind.boolean:
            self.tokens.get_next_token()
            return astx.LiteralBoolean(
                cast(bool, token.value),
                loc=token.location,
            )
        if token.kind == TokenKind.unit:
            self.tokens.get_next_token()
            return astx.LiteralNone(loc=token.location)
        if token.kind == TokenKind.identifier:
            self.tokens.get_next_token()
            return astx.Identifier(cast(str, token.value), loc=token.location)
        if token.kind == TokenKind.lparen:
            self.tokens.get_next_token()
            expr = self.parse_expression()
            self._consume(TokenKind.rparen, ")")
            return expr
        if token.kind == TokenKind.lambda_:
            self._raise_here(
                "lambda expressions are parsed later in the AIX roadmap"
            )
        if token.kind == TokenKind.primitive_type:
            self._raise_here("type names are not valid expressions")
        if token.kind == TokenKind.symbolic_operator:
            self._raise_reserved_operator(token)
        self._raise_here(
            f"unexpected token '{token.get_name()}' in expression"
        )

    def _infer_type(self, value: astx.Expr) -> astx.DataType:
        if isinstance(value, astx.LiteralBoolean):
            return astx.Boolean()
        if isinstance(value, astx.LiteralFloat64):
            return astx.Float64()
        if isinstance(value, astx.LiteralInt64):
            return astx.Int64()
        if isinstance(value, astx.LiteralString):
            return astx.String()
        if isinstance(value, astx.LiteralNone):
            return astx.NoneType()
        return AnyType()

    def _skip_separators(self) -> None:
        while self.tokens.cur_tok.kind == TokenKind.semicolon:
            self.tokens.get_next_token()

    def _at(self, kind: TokenKind) -> bool:
        return self.tokens.cur_tok.kind == kind

    def _peek(self, offset: int = 0) -> Token:
        index = self.tokens.position + offset
        if index >= len(self.tokens.tokens):
            return Token(TokenKind.eof, "")
        return self.tokens.tokens[index]

    def _consume(self, kind: TokenKind, display: str) -> Token:
        token = self.tokens.cur_tok
        if token.kind != kind:
            self._raise_here(f"expected '{display}', got '{token.get_name()}'")
        self.tokens.get_next_token()
        return token

    def _expect(self, kind: TokenKind, description: str) -> Token:
        token = self.tokens.cur_tok
        if token.kind != kind:
            self._raise_here(f"expected {description}")
        self.tokens.get_next_token()
        return token

    def _raise_reserved_operator(self, token: Token) -> NoReturn:
        raise ParserException(
            self._message_at(
                token,
                "unsupported reserved operator "
                f"'{token.value}'. This symbol is reserved for a future "
                "AIX version.",
            )
        )

    def _raise_here(self, message: str) -> NoReturn:
        raise ParserException(self._message_at(self.tokens.cur_tok, message))

    def _message_at(self, token: Token, message: str) -> str:
        return (
            "AIX parser error at line "
            f"{token.location.line}, column {token.location.col}: {message}"
        )


__all__ = ["Parser"]
