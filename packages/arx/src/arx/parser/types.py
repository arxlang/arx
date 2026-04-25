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
from arx.parser.base import ParserMixinBase
from arx.parser.state import TypeUseContext
from arx.tensor import (
    binding_from_type,
    default_value,
    is_tensor_type,
    runtime_tensor_type,
    tensor_type,
)


class TypeParserMixin(ParserMixinBase):
    """
    title: Type parser mixin.
    """

    def _consume_runtime_shape_marker(self) -> None:
        """
        title: Consume one runtime-shape ellipsis marker.
        """
        for _ in range(3):
            if not self._is_operator("."):
                raise ParserException(
                    "Runtime-shaped tensor marker must be '...'."
                )
            self._consume_operator(".")

    def _ensure_runtime_layout_allowed(
        self,
        type_name: str,
        type_context: TypeUseContext,
    ) -> None:
        """
        title: Validate that one runtime-layout type is allowed here.
        parameters:
          type_name:
            type: str
          type_context:
            type: TypeUseContext
        """
        if type_context.allows_runtime_layout:
            return
        raise ParserException(
            f"Runtime-shaped {type_name} types using '...' are only "
            "supported in function parameter annotations."
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
        if isinstance(data_type, astx.ListType):
            if len(data_type.element_types) != 1:
                raise ParserException(
                    "Parser: List types accept exactly one element type."
                )
            return astx.ListCreate(data_type.element_types[0])
        if isinstance(data_type, astx.DateTime):
            return astx.LiteralDateTime("1970-01-01T00:00:00")
        if isinstance(data_type, astx.Timestamp):
            return astx.LiteralTimestamp("1970-01-01T00:00:00")
        if isinstance(data_type, astx.Date):
            return astx.LiteralDate("1970-01-01")
        if isinstance(data_type, astx.Time):
            return astx.LiteralTime("00:00:00")
        if is_tensor_type(data_type):
            if binding_from_type(data_type) is None:
                raise ParserException(
                    "Parser: Tensor types require at least one static shape "
                    "dimension."
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
        type_context: TypeUseContext = TypeUseContext.GENERAL,
    ) -> astx.DataType:
        """
        title: Parse a type annotation.
        parameters:
          allow_template_vars:
            type: bool
          allow_union:
            type: bool
          type_context:
            type: TypeUseContext
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
                    type_context=TypeUseContext.NESTED,
                )
                if self._is_operator(","):
                    raise ParserException(
                        "List types accept exactly one element type."
                    )
                self._consume_operator("]")
                type_ = astx.ListType([cast(astx.ExprType, elem_type)])
            elif type_name == "tensor":
                self.tokens.get_next_token()  # eat tensor
                self._consume_operator("[")
                elem_type = self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=allow_union,
                    type_context=TypeUseContext.NESTED,
                )
                shape: list[int] = []
                runtime_shape = False
                if self._is_operator(","):
                    self._consume_operator(",")
                    if self._is_operator("."):
                        self._consume_runtime_shape_marker()
                        runtime_shape = True
                    else:
                        while True:
                            dimension_token = self.tokens.cur_tok
                            if dimension_token.kind != TokenKind.int_literal:
                                raise ParserException(
                                    "Tensor dimensions must be integer "
                                    "literals."
                                )
                            shape.append(cast(int, dimension_token.value))
                            self.tokens.get_next_token()
                            if not self._is_operator(","):
                                break
                            self._consume_operator(",")
                            if self._is_operator("."):
                                self._consume_runtime_shape_marker()
                                raise ParserException(
                                    "Runtime-shaped tensor ellipsis cannot "
                                    "be combined with static dimensions."
                                )

                if runtime_shape and self._is_operator(","):
                    raise ParserException(
                        "Runtime-shaped tensor ellipsis cannot be combined "
                        "with static dimensions."
                    )

                self._consume_operator("]")
                if runtime_shape:
                    self._ensure_runtime_layout_allowed(
                        "tensor",
                        type_context,
                    )
                    try:
                        type_ = runtime_tensor_type(elem_type)
                    except ValueError as err:
                        raise ParserException(str(err)) from err
                else:
                    if not shape:
                        raise ParserException(
                            "Tensor types require at least one static shape "
                            "dimension, for example tensor[i32, 4]. Use "
                            "tensor[i32, ...] for runtime-shaped tensor "
                            "parameters."
                        )
                    try:
                        type_ = tensor_type(elem_type, tuple(shape))
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
                    type_context=type_context,
                )
            )

        return astx.UnionType(members)
