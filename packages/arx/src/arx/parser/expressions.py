"""
title: Expression parser mixin.
summary: >-
  Parse primary, postfix, unary, and binary expressions plus literal and call
  syntax.
"""

from __future__ import annotations

from typing import cast

import astx

from astx.operators import OpCodeAugAssign

from arx import builtins
from arx.dataframe import (
    attach_binding as attach_dataframe_binding,
)
from arx.dataframe import (
    column_type as dataframe_column_type,
)
from arx.exceptions import ParserException
from arx.lexer import TokenKind
from arx.parser.base import ParserMixinBase
from arx.parser.state import TypeUseContext
from arx.tensor import attach_binding

NOT_PRECEDENCE = 7
PREFIX_PRECEDENCE = 50
COMPOUND_OPERATORS = {"+=", "-=", "*=", "/=", "%="}


class ExpressionParserMixin(ParserMixinBase):
    """
    title: Expression parser mixin.
    """

    def parse_primary(self) -> astx.AST:
        """
        title: Parse the primary expression.
        returns:
          type: astx.AST
        """
        if self._is_operator("@"):
            raise ParserException(
                "Declaration prefixes are only allowed before declarations."
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_class:
            raise ParserException(
                "Class declarations are only allowed at module scope."
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_import:
            raise ParserException(
                "Import statements are only allowed at module scope."
            )
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
            return self.parse_array_expr()
        if self.tokens.cur_tok.kind == TokenKind.kw_if:
            return self.parse_if_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_elif:
            raise ParserException(
                "'elif' requires a preceding 'if' or 'elif' "
                "at the same indentation.",
                self.tokens.cur_tok.location,
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_else:
            raise ParserException(
                "'else' requires a matching 'if' or 'try' "
                "at the same indentation.",
                self.tokens.cur_tok.location,
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_while:
            return self.parse_while_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_for:
            return self.parse_for_stmt()
        if self.tokens.cur_tok.kind in {
            TokenKind.kw_break,
            TokenKind.kw_continue,
        }:
            raise ParserException(
                "Loop transfers are statements, not expression operands.",
                self.tokens.cur_tok.location,
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_function:
            raise ParserException(
                "Nested functions and closures are not supported.",
                self.tokens.cur_tok.location,
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_extern:
            raise ParserException(
                "Extern declarations are only allowed at module scope.",
                self.tokens.cur_tok.location,
            )
        if self.tokens.cur_tok.kind in {TokenKind.kw_var, TokenKind.kw_const}:
            raise ParserException(
                "Leading variable declaration keywords were removed; "
                "use 'name: [var|const ::] type'.",
                self.tokens.cur_tok.location,
            )
        if self.tokens.cur_tok.kind == TokenKind.kw_assert:
            return self.parse_assert_stmt()
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
                "first statement inside a function body.",
                code="ARX-PARSE-DOCSTRING-001",
            )

        msg = (
            "Parser: Unknown token when expecting an expression: "
            f"'{self.tokens.cur_tok.get_name()}'."
        )
        if self.tokens.cur_tok.kind != TokenKind.eof:
            self.tokens.get_next_token()
        raise ParserException(msg)

    def parse_call_arguments(
        self,
        *,
        allow_trailing: bool = False,
    ) -> tuple[list[astx.DataType], list[astx.KeywordArgument]]:
        """
        title: Preserve source-ordered operands after an opening parenthesis.
        parameters:
          allow_trailing:
            type: bool
        returns:
          type: tuple[list[astx.DataType], list[astx.KeywordArgument]]
        """
        args: list[astx.DataType] = []
        keywords: list[astx.KeywordArgument] = []
        while not self._is_operator(")"):
            if (
                self.tokens.cur_tok.kind == TokenKind.identifier
                and self._peek_token().value == "="
            ):
                token = self.tokens.cur_tok
                self.tokens.get_next_token()
                self._consume_operator("=")
                keywords.append(
                    astx.KeywordArgument(
                        cast(str, token.value),
                        cast(astx.DataType, self.parse_expression()),
                        loc=token.location,
                    )
                )
            else:
                if keywords:
                    raise ParserException(
                        "Positional arguments cannot follow keywords."
                    )
                args.append(cast(astx.DataType, self.parse_expression()))
            if self._is_operator(")"):
                break
            self._consume_operator(",")
            if self._is_operator(")") and not keywords and not allow_trailing:
                raise ParserException("Expected an argument after comma.")
        self._consume_operator(")")
        return args, keywords

    def parse_postfix(self) -> astx.AST:
        """
        title: Parse member access, method calls, and subscripts.
        summary: >-
          Reject same-line postfix increment and decrement at their operator
          token; prefix mutation in a following statement remains valid.
          DataFrame metadata calls retain ordinary method-call arguments and
          locations; receiver-type and signature validation belong to IRx.
        returns:
          type: astx.AST
        """
        expr = self.parse_primary()

        while self._is_operator("[") or self._is_operator("."):
            if self._is_operator("["):
                expr = self.parse_subscript_expr(expr)
                continue

            self._consume_operator(".")

            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException(
                    "Parser: Expected member name after '.'."
                )

            member_loc = self.tokens.cur_tok.location
            member_name = cast(str, self.tokens.cur_tok.value)
            self.tokens.get_next_token()

            template_args = self._parse_template_args_for_call()

            if self._is_operator("("):
                self._consume_operator("(")
                args, keywords = self.parse_call_arguments()
                if (
                    member_name == "append"
                    and isinstance(expr, astx.Identifier)
                    and self._is_list_name(expr.name)
                ):
                    if template_args is not None:
                        raise ParserException(
                            "List append does not accept template arguments."
                        )
                    if keywords:
                        raise ParserException(
                            "List append does not accept keywords."
                        )
                    if len(args) != 1:
                        raise ParserException(
                            "List append expects exactly one argument."
                        )
                    expr = astx.ListAppend(expr, args[0])
                    continue
                class_name = self._class_name_from_expr(expr)
                if class_name is not None:
                    expr = astx.StaticMethodCall(
                        class_name,
                        member_name,
                        args,
                        keywords=tuple(keywords),
                    )
                else:
                    expr = astx.MethodCall(
                        expr,
                        member_name,
                        args,
                        keywords=tuple(keywords),
                    )
                expr.loc = member_loc
                if template_args is not None:
                    astx.set_template_args(expr, template_args)
                continue

            class_name = self._class_name_from_expr(expr)
            if class_name is not None:
                expr = astx.StaticFieldAccess(class_name, member_name)
            elif self._is_dataframe_expr(expr):
                expr = self._parse_dataframe_field_access(expr, member_name)
            else:
                expr = astx.FieldAccess(expr, member_name)

        token = self.tokens.cur_tok
        if (
            isinstance(expr, astx.Expr)
            and token.kind == TokenKind.operator
            and token.value in {"++", "--"}
        ):
            # Position follows the current lookahead. Use the preceding token
            # rather than expr.loc, which may precede a multiline call.
            previous = self.tokens.tokens[self.tokens.position - 2]
            if token.location.line == previous.location.line:
                operator = cast(str, token.value)
                raise ParserException(
                    f"Postfix '{operator}' is not supported; use prefix "
                    f"mutation (e.g. '{operator}x') or assignment "
                    f"(e.g. 'x = x {operator[0]} 1').",
                    token.location,
                )

        return expr

    def parse_expression(self) -> astx.AST:
        """
        title: Parse an expression.
        returns:
          type: astx.AST
        """
        lhs = self.parse_unary()
        expression = self.parse_bin_op_rhs(0, lhs)
        if (
            self.tokens.cur_tok.kind == TokenKind.operator
            and self.tokens.cur_tok.value in COMPOUND_OPERATORS
        ):
            raise ParserException(
                "Compound assignment requires a standalone identifier target "
                "in a statement or count-loop update, not an expression.",
                self.tokens.cur_tok.location,
            )
        return expression

    def parse_assignment_or_expression(self) -> astx.AST:
        """
        title: Parse a scalar compound statement or an ordinary expression.
        summary: >-
          Only statement and count-loop dispatch may enter this path. Preserve
          target, operator, and RHS locations without duplicating evaluations;
          IRx validates mutability, numeric types, and loop binding identity.
        returns:
          type: astx.AST
        """
        target = self.tokens.cur_tok
        following = self._peek_token()
        if (
            target.kind != TokenKind.identifier
            or following.kind != TokenKind.operator
            or following.value not in COMPOUND_OPERATORS
            or following.location.line != target.location.line
        ):
            return self.parse_expression()
        self.tokens.get_next_token()
        operator = self.tokens.cur_tok
        self.tokens.get_next_token()
        value_token = self.tokens.cur_tok
        if (
            value_token.kind in {TokenKind.eof, TokenKind.indent}
            or value_token.location.line > operator.location.line
            or (
                value_token.kind == TokenKind.operator
                and value_token.value in {";", ":", ")", "]", ","}
            )
        ):
            raise ParserException(
                "Expected a value after compound assignment.",
                value_token.location,
            )
        value = self.parse_expression()
        if not isinstance(value, astx.DataType) or (
            isinstance(value, astx.BinaryOp) and value.op_code == "="
        ):
            raise ParserException(
                "Compound assignment requires a value, not a statement "
                "or chained assignment.",
                value_token.location,
            )
        return astx.AugAssign(
            astx.Identifier(cast(str, target.value), loc=target.location),
            cast(OpCodeAugAssign, operator.value),
            value,
            loc=operator.location,
        )

    def parse_int_expr(self) -> astx.LiteralInteger:
        """
        title: Parse the integer expression.
        returns:
          type: astx.LiteralInteger
        """
        result = astx.LiteralInteger(
            self.tokens.cur_tok.value, loc=self.tokens.cur_tok.location
        )
        self.tokens.get_next_token()
        return result

    def parse_float_expr(self) -> astx.LiteralFloat:
        """
        title: Parse the float expression.
        returns:
          type: astx.LiteralFloat
        """
        result = astx.LiteralFloat(
            self.tokens.cur_tok.source_text or str(self.tokens.cur_tok.value),
            loc=self.tokens.cur_tok.location,
        )
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

    def parse_array_expr(self) -> astx.ListExpr:
        """
        title: Parse ordered lists without selecting storage or types.
        returns:
          type: astx.ListExpr
        """
        location = self.tokens.cur_tok.location
        self._consume_operator("[")
        elements: list[astx.Expr] = []
        while not self._is_operator("]"):
            element = self.parse_expression()
            if not isinstance(element, astx.Expr):
                raise ParserException(
                    "List elements must be expressions.", location
                )
            elements.append(element)
            if self._is_operator("]"):
                break
            self._consume_operator(",")
        self._consume_operator("]")
        return astx.ListExpr(elements, loc=location)

    def parse_imported_namespace_name(self, name: str) -> str:
        """
        title: Match a dotted import's complete binding before member access.
        parameters:
          name:
            type: str
        returns:
          type: str
        """
        if self._name_is_shadowed(name):
            return name
        candidates = sorted(
            (
                item
                for item in self.namespace_roots
                if item.startswith(name + ".")
            ),
            key=len,
            reverse=True,
        )
        start = self.tokens.position - 1
        for candidate in candidates:
            expected = [
                value
                for part in candidate[len(name) + 1 :].split(".")
                for value in (".", part)
            ]
            actual = self.tokens.tokens[start : start + len(expected)]
            if len(actual) != len(expected) or not all(
                token.value == value
                and token.kind
                is (
                    TokenKind.operator
                    if value == "."
                    else TokenKind.identifier
                )
                for token, value in zip(actual, expected)
            ):
                continue
            for _ in expected:
                self.tokens.get_next_token()
            return candidate
        return name

    def parse_identifier_expr(self) -> astx.AST:
        """
        title: Parse the identifier expression.
        returns:
          type: astx.AST
        """
        id_name = cast(str, self.tokens.cur_tok.value)
        id_loc = self.tokens.cur_tok.location

        self.tokens.get_next_token()
        id_name = self.parse_imported_namespace_name(id_name)  # eat identifier

        template_args = self._parse_template_args_for_call()

        if not self._is_operator("("):
            identifier = astx.Identifier(id_name, loc=id_loc)
            binding = self._lookup_tensor_binding(id_name)
            if binding is not None:
                attach_binding(identifier, binding)
            dataframe_binding = self._lookup_dataframe_binding(id_name)
            if dataframe_binding is not None:
                attach_dataframe_binding(identifier, dataframe_binding)
            return identifier

        self._consume_operator("(")

        if id_name == builtins.BUILTIN_DATAFRAME:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            return self.parse_dataframe_constructor()

        if id_name in {
            "series_sum",
            "series_min",
            "series_max",
            "series_mean",
            "series_count",
            "series_any",
            "series_all",
        }:
            if template_args is not None:
                raise ParserException("Series reductions reject templates.")
            value = cast(astx.Expr, self.parse_expression())
            self._consume_operator(")")
            return astx.SeriesReduction(
                id_name.removeprefix("series_"), value, loc=id_loc
            )

        if id_name in {"is_null", "fill_null"}:
            if template_args is not None:
                raise ParserException(
                    "Null operations reject template arguments."
                )
            value = cast(astx.Expr, self.parse_expression())
            if id_name == "is_null":
                self._consume_operator(")")
                return astx.NullCheck(value, loc=id_loc)
            self._consume_operator(",")
            replacement = cast(astx.Expr, self.parse_expression())
            self._consume_operator(")")
            return astx.NullFill(value, replacement, loc=id_loc)

        if id_name in {"wrapping_add", "wrapping_sub", "wrapping_mul"}:
            lhs = cast(astx.DataType, self.parse_expression())
            self._consume_operator(",")
            rhs = cast(astx.DataType, self.parse_expression())
            self._consume_operator(")")
            operation = astx.BinaryOp(
                {
                    "wrapping_add": "+",
                    "wrapping_sub": "-",
                    "wrapping_mul": "*",
                }[id_name],
                lhs,
                rhs,
                loc=id_loc,
                mode=astx.NumericMode.WRAPPING,
            )
            if template_args is not None:
                astx.set_template_args(operation, template_args)
            return operation

        if id_name in {builtins.BUILTIN_CAST, "wrapping_cast"}:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            value_expr = self.parse_expression()
            self._consume_operator(",")
            target_type = self.parse_type(
                allow_union=True, type_context=TypeUseContext.EXPRESSION
            )
            if isinstance(target_type, astx.UnionType):
                raise ParserException(
                    "Builtin 'cast' does not support union target types yet."
                )
            self._consume_operator(")")
            result = astx.Cast(
                cast(astx.DataType, value_expr),
                target_type,
                mode=(
                    astx.NumericMode.WRAPPING
                    if id_name == "wrapping_cast"
                    else astx.NumericMode.CHECKED
                ),
            )
            result.loc = id_loc
            return result

        if id_name == builtins.BUILTIN_ISINSTANCE:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            value_expr = self.parse_expression()
            self._consume_operator(",")
            target_type = self.parse_type(
                allow_union=True,
                type_context=TypeUseContext.EXPRESSION,
            )
            self._consume_operator(")")
            return builtins.build_isinstance(
                cast(astx.Expr, value_expr),
                target_type,
            )

        if id_name == builtins.BUILTIN_PRINT:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            message = self.parse_expression()
            self._consume_operator(")")
            return builtins.build_print(cast(astx.Expr, message))

        if id_name == builtins.BUILTIN_TYPE:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            value_expr = self.parse_expression()
            self._consume_operator(")")
            return builtins.build_type_of(cast(astx.Expr, value_expr))

        if id_name in {"date", "time", "datetime", "timestamp"}:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            arg = self.parse_expression()
            self._consume_operator(")")
            if not isinstance(arg, astx.LiteralString):
                raise ParserException(
                    f"Builtin '{id_name}' expects a string literal argument."
                )
            if id_name == "datetime":
                return astx.LiteralDateTime(arg.value, loc=id_loc)
            if id_name == "date":
                return astx.LiteralDate(arg.value, loc=id_loc)
            if id_name == "time":
                return astx.LiteralTime(arg.value, loc=id_loc)
            return astx.LiteralTimestamp(arg.value, loc=id_loc)

        args, keywords = self.parse_call_arguments(
            allow_trailing=(
                id_name in self.known_class_names
                or id_name in self.imported_type_names
                or id_name in {builtins.BUILTIN_OPEN, builtins.BUILTIN_FILE}
            )
        )
        if id_name in self.known_class_names and not self._name_is_shadowed(
            id_name
        ):
            if template_args is not None:
                raise ParserException(
                    "class construction does not accept template arguments"
                )
            return astx.ClassConstruct(
                id_name, tuple(args), keywords=tuple(keywords), loc=id_loc
            )

        call = astx.FunctionCall(
            id_name, args, loc=id_loc, keywords=tuple(keywords)
        )
        if template_args is not None:
            astx.set_template_args(call, template_args)
        return call

    def parse_subscript_expr(self, base: astx.AST) -> astx.AST:
        """
        title: Parse one postfix subscript or tensor index expression.
        parameters:
          base:
            type: astx.AST
        returns:
          type: astx.AST
        """
        subscript_loc = self.tokens.cur_tok.location
        self._consume_operator("[")

        if self._is_operator("]"):
            raise ParserException("Expected one index inside '[' and ']'.")

        indices: list[astx.Expr] = []
        while True:
            first = (
                astx.LiteralNone()
                if (self._is_operator(":") or self._is_operator("::"))
                else cast(astx.Expr, self.parse_expression())
            )
            if self._is_operator(":") or self._is_operator("::"):
                if indices:
                    raise ParserException(
                        "Multidimensional slices are unsupported."
                    )
                if self._is_operator("::"):
                    self._consume_operator("::")
                    stride = (
                        astx.LiteralNone()
                        if self._is_operator("]")
                        else cast(astx.Expr, self.parse_expression())
                    )
                    self._consume_operator("]")
                    return astx.SubscriptExpr(
                        cast(astx.Expr, base),
                        lower=first,
                        upper=astx.LiteralNone(),
                        step=stride,
                        loc=subscript_loc,
                    )
                self._consume_operator(":")
                stop = (
                    astx.LiteralNone()
                    if self._is_operator(":") or self._is_operator("]")
                    else cast(astx.Expr, self.parse_expression())
                )
                step: astx.Expr = astx.LiteralNone()
                if self._is_operator(":"):
                    self._consume_operator(":")
                    if not self._is_operator("]"):
                        step = cast(astx.Expr, self.parse_expression())
                self._consume_operator("]")
                return astx.SubscriptExpr(
                    cast(astx.Expr, base),
                    lower=first,
                    upper=stop,
                    step=step,
                    loc=subscript_loc,
                )
            indices.append(first)
            if self._is_operator("]"):
                break
            self._consume_operator(",")

        self._consume_operator("]")

        dataframe_base = self._coerce_dataframe_base(base)
        if dataframe_base is not None:
            if len(indices) != 1 or not isinstance(
                indices[0],
                astx.LiteralString,
            ):
                raise ParserException(
                    "DataFrame string-key column access expects exactly one "
                    "string literal key."
                )
            return self._parse_dataframe_string_access(
                dataframe_base,
                indices[0].value,
            )

        tensor_base = self._coerce_tensor_base(base)
        if tensor_base is None and len(indices) == 1:
            return astx.SubscriptExpr(
                cast(astx.Expr, base),
                indices[0],
                loc=subscript_loc,
            )

        result = astx.TensorIndex(tensor_base or base, indices)
        result.loc = subscript_loc
        return result

    def parse_dataframe_constructor(self) -> astx.DataFrameLiteral:
        """
        title: Parse a builtin DataFrame constructor expression.
        returns:
          type: astx.DataFrameLiteral
        """
        self._skip_inline_indents()
        self._consume_operator("{")
        self._skip_inline_indents()

        columns: list[astx.DataFrameLiteralColumn] = []
        seen: set[str] = set()
        if self._is_operator("}"):
            raise ParserException(
                "DataFrame constructor requires at least one column."
            )

        while True:
            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException(
                    "DataFrame constructor column names must be identifiers."
                )
            column_name = cast(str, self.tokens.cur_tok.value)
            if column_name in seen:
                raise ParserException(
                    f"duplicate dataframe column '{column_name}'"
                )
            seen.add(column_name)
            self.tokens.get_next_token()

            self._consume_operator(":")
            value = self.parse_expression()
            if not isinstance(value, astx.ListExpr):
                raise ParserException(
                    "DataFrame constructor column values must be list "
                    "literals."
                )
            columns.append(
                astx.DataFrameLiteralColumn(
                    column_name,
                    tuple(value.elements),
                )
            )
            self._skip_inline_indents()

            if self._is_operator("}"):
                break

            self._consume_operator(",")
            self._skip_inline_indents()
            if self._is_operator("}"):
                break

        self._consume_operator("}")
        self._skip_inline_indents()
        self._consume_operator(")")
        return astx.DataFrameLiteral(columns)

    def _skip_inline_indents(self) -> None:
        """
        title: Skip indentation markers inside grouped expressions.
        """
        while self.tokens.cur_tok.kind == TokenKind.indent:
            self.tokens.get_next_token()

    def _is_dataframe_expr(self, expr: astx.AST) -> bool:
        """
        title: Return whether one expression is known as a DataFrame.
        parameters:
          expr:
            type: astx.AST
        returns:
          type: bool
        """
        if isinstance(expr, astx.DataFrameLiteral):
            return True
        if isinstance(expr, astx.Identifier):
            return self._is_dataframe_name(expr.name)
        return False

    def _coerce_dataframe_base(self, base: astx.AST) -> astx.AST | None:
        """
        title: Return one DataFrame-aware access base when available.
        parameters:
          base:
            type: astx.AST
        returns:
          type: astx.AST | None
        """
        if isinstance(base, astx.DataFrameLiteral):
            return base
        if not isinstance(base, astx.Identifier):
            return None
        binding = self._lookup_dataframe_binding(base.name)
        if binding is not None:
            attach_dataframe_binding(base, binding)
            return base
        if self._is_dataframe_name(base.name):
            raise ParserException(
                "Runtime-schema dataframe column access is not supported yet."
            )
        return None

    def _parse_dataframe_field_access(
        self,
        base: astx.AST,
        column_name: str,
    ) -> astx.DataFrameColumnAccess:
        """
        title: Build and validate one DataFrame field-style column access.
        parameters:
          base:
            type: astx.AST
          column_name:
            type: str
        returns:
          type: astx.DataFrameColumnAccess
        """
        dataframe_base = self._coerce_dataframe_base(base)
        if dataframe_base is None:
            raise ParserException("Expected a DataFrame value.")
        if isinstance(base, astx.Identifier):
            binding = self._lookup_dataframe_binding(base.name)
            if (
                binding is not None
                and dataframe_column_type(
                    binding,
                    column_name,
                )
                is None
            ):
                raise ParserException(
                    f"DataFrame has no column '{column_name}'."
                )
        return astx.DataFrameColumnAccess(dataframe_base, column_name)

    def _parse_dataframe_string_access(
        self,
        base: astx.AST,
        column_name: str,
    ) -> astx.DataFrameStringColumnAccess:
        """
        title: Build and validate one DataFrame string-key column access.
        parameters:
          base:
            type: astx.AST
          column_name:
            type: str
        returns:
          type: astx.DataFrameStringColumnAccess
        """
        if isinstance(base, astx.Identifier):
            binding = self._lookup_dataframe_binding(base.name)
            if (
                binding is not None
                and dataframe_column_type(
                    binding,
                    column_name,
                )
                is None
            ):
                raise ParserException(
                    f"DataFrame has no column '{column_name}'."
                )
        return astx.DataFrameStringColumnAccess(base, column_name)

    def _coerce_tensor_base(self, base: astx.AST) -> astx.AST | None:
        """
        title: Return one tensor-aware indexing base when available.
        parameters:
          base:
            type: astx.AST
        returns:
          type: astx.AST | None
        """
        if isinstance(base, astx.TensorLiteral):
            return base

        if isinstance(base, astx.Identifier):
            binding = self._lookup_tensor_binding(base.name)
            if binding is not None:
                attach_binding(base, binding)
                return base
            if self._is_tensor_name(base.name):
                return base
            return None

        return None

    def parse_unary(self, min_precedence: int = 0) -> astx.AST:
        """
        title: Parse prefix expressions with comparison-binding word negation.
        summary: >-
          Word not binds below comparisons but above and/or and emits the
          existing Boolean ! operation. Symbolic prefixes retain their higher
          precedence; parenthesize not when used in a tighter operand.
        parameters:
          min_precedence:
            type: int
        returns:
          type: astx.AST
        """
        if self._is_operator("@"):
            raise ParserException(
                "Declaration prefixes are only allowed before declarations."
            )

        if (
            self.tokens.cur_tok.kind != TokenKind.operator
            or self.tokens.cur_tok.value in ("(", "[", ",", ":", ")", "]", ";")
        ):
            return self.parse_postfix()

        op_code = cast(str, self.tokens.cur_tok.value)
        op_loc = self.tokens.cur_tok.location
        if op_code == "::":
            raise ParserException(
                "'::' is only valid in a declaration modifier group or slice.",
                op_loc,
            )
        if op_code in COMPOUND_OPERATORS:
            raise ParserException(
                "Compound assignment is not an expression; "
                "provide an identifier target in a statement or loop update.",
                op_loc,
            )
        if op_code == "%":
            raise ParserException(
                "Remainder '%' requires a left operand.", op_loc
            )
        if op_code == "not" and min_precedence > NOT_PRECEDENCE:
            raise ParserException(
                "Parenthesize 'not' in this operator's operand.", op_loc
            )
        self.tokens.get_next_token()
        operand = self.parse_unary(
            NOT_PRECEDENCE if op_code == "not" else PREFIX_PRECEDENCE
        )
        if op_code == "not":
            operand = self.parse_bin_op_rhs(NOT_PRECEDENCE, operand)
            op_code = "!"
        if not isinstance(operand, astx.DataType):
            raise ParserException(
                f"Unary operator '{op_code}' requires an expression operand.",
                op_loc,
            )
        if op_code in {"+", "-"} and isinstance(operand, astx.LiteralInteger):
            return astx.LiteralInteger(
                -operand.value if op_code == "-" else operand.value, loc=op_loc
            )
        if op_code in {"+", "-"} and isinstance(operand, astx.LiteralFloat):
            value = operand.value
            if op_code == "-":
                value = value.copy_negate()
            return astx.LiteralFloat(value, loc=op_loc)
        unary = astx.UnaryOp(op_code, operand, loc=op_loc)
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

            rhs = self.parse_unary(cur_prec + 1)

            next_prec = self.get_tok_precedence()
            if cur_prec < next_prec:
                rhs = self.parse_bin_op_rhs(cur_prec + 1, rhs)

            if not isinstance(lhs, astx.DataType) or not isinstance(
                rhs,
                astx.DataType,
            ):
                raise ParserException(
                    f"Binary operator '{bin_op}' requires expression "
                    "operands.",
                    bin_loc,
                )
            lhs = astx.BinaryOp(
                bin_op,
                lhs,
                rhs,
                loc=bin_loc,
            )
