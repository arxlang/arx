"""
title: Expression parser mixin.
summary: >-
  Parse primary, postfix, unary, and binary expressions plus literal and call
  syntax.
"""

from __future__ import annotations

from typing import cast

import astx

from irx.builtins.collections.tensor import TENSOR_LAYOUT_EXTRA, TensorLayout

from arx import builtins
from arx.exceptions import ParserException
from arx.lexer import TokenKind
from arx.parser.base import ParserMixinBase
from arx.parser.state import TypeUseContext
from arx.tensor import attach_binding, infer_literal


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
        if self.tokens.cur_tok.kind == TokenKind.kw_while:
            return self.parse_while_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_for:
            return self.parse_for_stmt()
        if self.tokens.cur_tok.kind == TokenKind.kw_var:
            return self.parse_var_expr()
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
                "first statement inside a function body."
            )

        msg = (
            "Parser: Unknown token when expecting an expression: "
            f"'{self.tokens.cur_tok.get_name()}'."
        )
        if self.tokens.cur_tok.kind != TokenKind.eof:
            self.tokens.get_next_token()
        raise ParserException(msg)

    def parse_postfix(self) -> astx.AST:
        """
        title: Parse postfix member access and method calls.
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

            member_name = cast(str, self.tokens.cur_tok.value)
            self.tokens.get_next_token()

            template_args = self._parse_template_args_for_call()

            if self._is_operator("("):
                self._consume_operator("(")
                args: list[astx.DataType] = []
                if not self._is_operator(")"):
                    while True:
                        args.append(
                            cast(astx.DataType, self.parse_expression())
                        )

                        if self._is_operator(")"):
                            break

                        self._consume_operator(",")

                self._consume_operator(")")
                if (
                    member_name == "append"
                    and isinstance(expr, astx.Identifier)
                    and self._is_list_name(expr.name)
                ):
                    if template_args is not None:
                        raise ParserException(
                            "List append does not accept template arguments."
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
                    )
                else:
                    expr = astx.MethodCall(
                        expr,
                        member_name,
                        args,
                    )
                if template_args is not None:
                    astx.set_template_args(expr, template_args)
                continue

            class_name = self._class_name_from_expr(expr)
            if class_name is not None:
                expr = astx.StaticFieldAccess(class_name, member_name)
            else:
                expr = astx.FieldAccess(expr, member_name)

        return expr

    def parse_expression(self) -> astx.AST:
        """
        title: Parse an expression.
        returns:
          type: astx.AST
        """
        lhs = self.parse_unary()
        return self.parse_bin_op_rhs(0, lhs)

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

    def parse_array_expr(self) -> astx.Literal:
        """
        title: Parse list and tensor literals.
        returns:
          type: astx.Literal
        """
        self._consume_operator("[")

        elements: list[astx.Literal] = []
        if not self._is_operator("]"):
            while True:
                elem = self.parse_expression()
                if not isinstance(elem, astx.Literal):
                    raise ParserException(
                        "List and tensor literals currently support only "
                        "literal elements."
                    )
                elements.append(elem)

                if self._is_operator("]"):
                    break

                self._consume_operator(",")

        self._consume_operator("]")
        if any(
            isinstance(element, (astx.LiteralList, astx.LiteralTuple))
            for element in elements
        ):
            return astx.LiteralTuple(tuple(elements))
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

        template_args = self._parse_template_args_for_call()

        if not self._is_operator("("):
            identifier = astx.Identifier(id_name, loc=id_loc)
            binding = self._lookup_tensor_binding(id_name)
            if binding is not None:
                attach_binding(identifier, binding)
            return identifier

        self._consume_operator("(")

        if id_name == builtins.BUILTIN_CAST:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            value_expr = self.parse_expression()
            self._consume_operator(",")
            target_type = self.parse_type(
                type_context=TypeUseContext.EXPRESSION
            )
            self._consume_operator(")")
            return builtins.build_cast(
                cast(astx.DataType, value_expr), target_type
            )

        if id_name == builtins.BUILTIN_PRINT:
            if template_args is not None:
                raise ParserException(
                    f"Builtin '{id_name}' does not accept template arguments."
                )
            message = self.parse_expression()
            self._consume_operator(")")
            return builtins.build_print(cast(astx.Expr, message))

        if id_name in {"datetime", "timestamp"}:
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
            return astx.LiteralTimestamp(arg.value, loc=id_loc)

        args: list[astx.DataType] = []
        if not self._is_operator(")"):
            while True:
                args.append(cast(astx.DataType, self.parse_expression()))

                if self._is_operator(")"):
                    break

                self._consume_operator(",")

        self._consume_operator(")")
        if id_name in self.known_class_names and not self._name_is_shadowed(
            id_name
        ):
            if template_args is not None:
                raise ParserException(
                    "class construction does not accept template arguments"
                )
            if args:
                raise ParserException(
                    "class construction does not accept arguments"
                )
            return astx.ClassConstruct(id_name)

        call = astx.FunctionCall(id_name, args, loc=id_loc)
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
            indices.append(cast(astx.Expr, self.parse_expression()))
            if self._is_operator("]"):
                break
            self._consume_operator(",")

        self._consume_operator("]")

        tensor_base = self._coerce_tensor_base(base)
        if tensor_base is None:
            if len(indices) != 1:
                raise ParserException(
                    "Multidimensional indexing is only supported for "
                    "tensor values."
                )
            return astx.SubscriptExpr(
                cast(astx.Expr, base),
                indices[0],
                loc=subscript_loc,
            )

        self._validate_tensor_indices(tensor_base, indices)
        return astx.TensorIndex(tensor_base, indices)

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
                raise ParserException(
                    "Runtime-shaped tensor indexing is not supported yet; "
                    "pass tensor parameters through or use a static-shape "
                    "tensor annotation for indexed access."
                )
            return None

        if isinstance(base, (astx.LiteralList, astx.LiteralTuple)):
            try:
                return infer_literal(base)
            except ValueError:
                return None

        return None

    def _validate_tensor_indices(
        self,
        base: astx.AST,
        indices: list[astx.Expr],
    ) -> None:
        """
        title: Validate one tensor index arity and static bounds.
        parameters:
          base:
            type: astx.AST
          indices:
            type: list[astx.Expr]
        """
        layout = getattr(
            getattr(base, "semantic", None),
            "extras",
            {},
        ).get(TENSOR_LAYOUT_EXTRA)
        if not isinstance(layout, TensorLayout):
            if isinstance(base, astx.TensorLiteral):
                layout = TensorLayout(
                    shape=base.shape,
                    strides=base.strides or (),
                    offset_bytes=base.offset_bytes,
                )
            else:
                return

        if len(indices) != layout.ndim:
            raise ParserException(
                "Tensor indexing expects "
                f"{layout.ndim} indices for shape "
                f"{self._format_tensor_shape(layout.shape)}."
            )

        for axis, index in enumerate(indices):
            if not isinstance(index, astx.LiteralInt32):
                continue
            extent = layout.shape[axis]
            if index.value < 0 or index.value >= extent:
                raise ParserException(
                    "Tensor index "
                    f"{index.value} is out of bounds for dimension {axis} "
                    f"with extent {extent}."
                )

    def _format_tensor_shape(self, shape: tuple[int, ...]) -> str:
        """
        title: Render one tensor shape in parser diagnostics.
        parameters:
          shape:
            type: tuple[int, Ellipsis]
        returns:
          type: str
        """
        if not shape:
            return "()"
        return "(" + ", ".join(str(dim) for dim in shape) + ")"

    def parse_unary(self) -> astx.AST:
        """
        title: Parse a unary expression.
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
