"""
title: Type parser mixin.
summary: >-
  Parse type annotations and synthesize default values for typed declarations.
"""

from __future__ import annotations

from typing import cast

from irx import astx

from arx.exceptions import ParserException
from arx.lexer import TokenKind
from arx.ndarray import (
    binding_from_type,
    default_value,
    is_ndarray_type,
    ndarray_type,
)
from arx.parser.base import ParserMixinBase


class TypeParserMixin(ParserMixinBase):
    """
    title: Type parser mixin.
    """

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
        if isinstance(data_type, astx.DateTime):
            return astx.LiteralDateTime("1970-01-01T00:00:00")
        if isinstance(data_type, astx.Timestamp):
            return astx.LiteralTimestamp("1970-01-01T00:00:00")
        if isinstance(data_type, astx.Date):
            return astx.LiteralDate("1970-01-01")
        if isinstance(data_type, astx.Time):
            return astx.LiteralTime("00:00:00")
        if is_ndarray_type(data_type):
            if binding_from_type(data_type) is None:
                raise ParserException(
                    "Parser: No default value defined for unsized ndarray "
                    "types. An explicit initializer is required."
                )
            try:
                return default_value(data_type)
            except ValueError as err:
                raise ParserException(str(err)) from err

        raise ParserException(
            f"Parser: No default value defined for type "
            f"'{type(data_type).__name__}'. "
            f"An explicit initializer is required."
        )

    def parse_type(
        self,
        *,
        allow_template_vars: bool = True,
        allow_union: bool = False,
    ) -> astx.DataType:
        """
        title: Parse a type annotation.
        parameters:
          allow_template_vars:
            type: bool
          allow_union:
            type: bool
        returns:
          type: astx.DataType
        """
        if self.tokens.cur_tok.kind == TokenKind.none_literal:
            self.tokens.get_next_token()  # eat none
            type_: astx.DataType = astx.NoneType()
        else:
            if self.tokens.cur_tok.kind != TokenKind.identifier:
                raise ParserException("Parser: Expected a type name")

            type_name = cast(str, self.tokens.cur_tok.value)
            template_bound = None
            if allow_template_vars:
                template_bound = self._lookup_template_bound(type_name)

            if type_name == "list":
                self.tokens.get_next_token()  # eat list
                self._consume_operator("[")
                elem_type = self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=allow_union,
                )
                if self._is_operator(","):
                    raise ParserException(
                        "List types accept exactly one element type."
                    )
                self._consume_operator("]")
                type_ = astx.ListType([cast(astx.ExprType, elem_type)])
            elif type_name == "ndarray":
                self.tokens.get_next_token()  # eat ndarray
                self._consume_operator("[")
                elem_type = self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=allow_union,
                )
                shape: list[int] = []
                while self._is_operator(","):
                    self._consume_operator(",")
                    dimension_token = self.tokens.cur_tok
                    if dimension_token.kind != TokenKind.int_literal:
                        raise ParserException(
                            "Ndarray dimensions must be integer literals."
                        )
                    shape.append(cast(int, dimension_token.value))
                    self.tokens.get_next_token()

                self._consume_operator("]")
                try:
                    type_ = ndarray_type(
                        elem_type,
                        tuple(shape) if shape else None,
                    )
                except ValueError as err:
                    raise ParserException(str(err)) from err
            else:
                type_map: dict[str, astx.DataType] = {
                    "i8": astx.Int8(),
                    "i16": astx.Int16(),
                    "i32": astx.Int32(),
                    "i64": astx.Int64(),
                    "int8": astx.Int8(),
                    "int16": astx.Int16(),
                    "int32": astx.Int32(),
                    "int64": astx.Int64(),
                    "f16": astx.Float16(),
                    "f32": astx.Float32(),
                    "f64": astx.Float64(),
                    "float16": astx.Float16(),
                    "float32": astx.Float32(),
                    "float64": astx.Float64(),
                    "bool": astx.Boolean(),
                    "boolean": astx.Boolean(),
                    "none": astx.NoneType(),
                    "str": astx.String(),
                    "string": astx.String(),
                    "char": astx.Int8(),
                    "datetime": astx.DateTime(),
                    "timestamp": astx.Timestamp(),
                    "date": astx.Date(),
                    "time": astx.Time(),
                }

                self.tokens.get_next_token()  # eat type identifier
                if type_name in type_map:
                    type_ = type_map[type_name]
                elif template_bound is not None:
                    type_ = astx.TemplateTypeVar(
                        type_name,
                        bound=template_bound,
                    )
                elif type_name in self.known_class_names:
                    type_ = astx.ClassType(type_name)
                else:
                    raise ParserException(
                        f"Parser: Unknown type '{type_name}'."
                    )

        if not allow_union or not self._is_operator("|"):
            return type_

        members = [type_]
        while self._is_operator("|"):
            self._consume_operator("|")
            members.append(
                self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=False,
                )
            )

        return astx.UnionType(members)
