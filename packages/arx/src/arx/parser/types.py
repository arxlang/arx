"""
title: Type parser mixin.
summary: Parse type annotations and synthesize default values for
  typed declarations.
attributes:
  _BUILTIN_TYPE_MAP: Builtin type map.
"""

from __future__ import annotations

import copy

from typing import cast

import astx

from irx.builtins.collections.column_types import column_arrow_type

from arx import builtins
from arx.dataframe import (
    dataframe_type,
    is_dataframe_type,
    runtime_dataframe_type,
    series_type,
)
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

_BUILTIN_TYPE_MAP: dict[str, astx.DataType] = {
    "i8": astx.Int8(),
    "i16": astx.Int16(),
    "i32": astx.Int32(),
    "i64": astx.Int64(),
    "u8": astx.UInt8(),
    "u16": astx.UInt16(),
    "u32": astx.UInt32(),
    "u64": astx.UInt64(),
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
    "file": astx.ClassType("File", module_key=builtins.BUILTIN_FILE_MODULE),
    "bytes": astx.Bytes(),
    "range": astx.RangeType(),
    "str": astx.String(),
    "string": astx.String(),
    "char": astx.Int8(),
    "datetime": astx.DateTime(),
    "timestamp": astx.Timestamp(),
    "date": astx.Date(),
    "time": astx.Time(),
}

COLUMN_TYPE_NAMES = {
    "decimal128",
    "decimal256",
    "arrow_list",
    "large_list",
    "fixed_list",
    "dictionary",
    "binary",
    "large_binary",
    "large_string",
    "arrow_struct",
    "arrow_map",
}

_BUILTIN_TYPE_NAMES = (
    frozenset(_BUILTIN_TYPE_MAP)
    | frozenset(COLUMN_TYPE_NAMES)
    | frozenset(
        {
            "dataframe",
            "list",
            "sequence",
            "series",
            "tensor",
            "nullable",
            "auto",
        }
    )
)


class TypeParserMixin(ParserMixinBase):
    """
    title: Type parser mixin.
    """

    def validate_type_declaration_name(self, target: str) -> None:
        """
        title: Reject inference markers as names of declared types.
        summary: Auto remains a contextual value identifier, but cannot name
          a class, type alias, or template parameter because type positions
          interpret it as an inference request.
        parameters:
          target: Destination of the operation.
        """
        if self.tokens.cur_tok.value == "auto":
            raise ParserException(
                f"'auto' is reserved for type inference and cannot name "
                f"a {target}; choose another name.",
                self.tokens.cur_tok.location,
                code="ARX-PARSE-TYPE-NAME-001",
            )

    def is_type_alias_decl_start(self) -> bool:
        """
        title: Return whether the current token starts a type alias.
        returns: Whether the current token starts a type alias.
        """
        return (
            self._is_identifier_value(builtins.BUILTIN_TYPE)
            and self._peek_token().kind == TokenKind.identifier
        )

    def _clone_type_for_alias(self, alias_name: str) -> astx.DataType:
        """
        title: Return a cloned target type for one alias reference.
        parameters:
          alias_name: Name of alias.
        returns: A cloned target type for one alias reference.
        """
        type_ = copy.deepcopy(self.type_aliases[alias_name])
        if isinstance(type_, astx.UnionType):
            type_.alias_name = type_.alias_name or alias_name
            return type_
        setattr(type_, "alias_name", alias_name)
        return type_

    def _validate_type_alias_name(self, alias_name: str) -> None:
        """
        title: Validate one type alias declaration name.
        parameters:
          alias_name: Name of alias.
        """
        if alias_name in self.type_aliases:
            raise ParserException(
                f"Parser: Duplicate type alias '{alias_name}'."
            )
        if alias_name in _BUILTIN_TYPE_NAMES:
            raise ParserException(
                f"Parser: Type alias '{alias_name}' shadows a built-in type."
            )
        if builtins.is_builtin(alias_name):
            raise ParserException(
                f"Parser: Type alias '{alias_name}' shadows a built-in."
            )
        if alias_name in self.known_class_names:
            raise ParserException(
                f"Parser: Type alias '{alias_name}' shadows a class."
            )

    def parse_type_alias_decl(self) -> None:
        """
        title: Parse one top-level type alias declaration.
        """
        self._consume_identifier_value(builtins.BUILTIN_TYPE)
        if self.tokens.cur_tok.kind != TokenKind.identifier:
            raise ParserException("Parser: Expected type alias name.")

        self.validate_type_declaration_name("type alias")
        alias_name = cast(str, self.tokens.cur_tok.value)
        self._validate_type_alias_name(alias_name)
        self.tokens.get_next_token()  # eat alias name
        self._consume_operator("=")

        alias_type = self.parse_type(
            allow_template_vars=False,
            allow_union=True,
            type_context=TypeUseContext.TYPE_ALIAS,
        )
        if isinstance(alias_type, astx.UnionType):
            alias_type.alias_name = alias_name
        else:
            setattr(alias_type, "alias_name", alias_name)
        self.type_aliases[alias_name] = alias_type

    def _consume_runtime_shape_marker(self) -> None:
        """
        title: Consume one runtime-shape ellipsis marker.
        """
        for _ in range(3):
            if not self._is_operator("."):
                raise ParserException("Runtime-layout marker must be '...'.")
            self._consume_operator(".")

    def _ensure_runtime_layout_allowed(
        self,
        type_name: str,
        type_context: TypeUseContext,
    ) -> None:
        """
        title: Validate that one runtime-layout type is allowed here.
        parameters:
          type_name: Name of type.
          type_context: Type context.
        """
        if type_context.allows_runtime_layout or type_name == "dataframe":
            return
        raise ParserException(
            f"Runtime-layout {type_name} types using '...' are only "
            "supported in function parameter annotations."
        )

    def _default_value_for_type(self, data_type: astx.DataType) -> astx.Expr:
        """
        title: Build a default initializer for typed declarations.
        parameters:
          data_type: Declared data type.
        returns: Constructed a default initializer for typed declarations.
        """
        if isinstance(data_type, astx.NullableType):
            return astx.Cast(astx.LiteralNone(), data_type)
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
            return astx.ListCreate(
                cast(astx.DataType, data_type.element_types[0])
            )
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
        if is_dataframe_type(data_type):
            raise ParserException(
                "Parser: DataFrame declarations require an explicit "
                "initializer."
            )
        if isinstance(data_type, astx.SeriesType):
            raise ParserException(
                "Parser: Series declarations require an explicit initializer."
            )

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
        allow_nullable_union: bool = True,
        type_context: TypeUseContext = TypeUseContext.GENERAL,
    ) -> astx.DataType:
        """
        title: Parse a type annotation.
        summary: Parentheses group a complete type with multiline layout
          while preserving template-variable and type-use restrictions.
          They do not introduce tuple types or additional runtime union
          support.
        parameters:
          allow_template_vars: Whether to use allow template vars.
          allow_union: Whether to consume unparenthesized union members.
          allow_nullable_union: Whether to consume nullable shorthand.
          type_context: Type context.
        returns: Parsed a type annotation.
        """
        type_: astx.DataType
        if self._is_operator("("):
            previous_layout = self.tokens.ignore_indentation
            self.tokens.ignore_indentation = True
            try:
                self._consume_operator("(")
                type_ = self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=True,
                    type_context=type_context,
                )
                if not self._is_operator(")"):
                    raise ParserException(
                        "Expected ')' after parenthesized type",
                        self.tokens.cur_tok.location,
                        code="ARX-PARSE-TYPE-GROUP-001",
                    )
            finally:
                # The token after ')' may be a body's or sibling's indentation.
                self.tokens.ignore_indentation = previous_layout
            self._consume_operator(")")
        elif self.tokens.cur_tok.kind == TokenKind.none_literal:
            self.tokens.get_next_token()  # eat none
            type_ = astx.NoneType()
        else:
            if self.tokens.cur_tok.kind not in {
                TokenKind.identifier,
                TokenKind.binary_op,
            }:
                raise ParserException("Parser: Expected a type name")

            type_name = cast(str, self.tokens.cur_tok.value)
            type_location = self.tokens.cur_tok.location
            if type_name == "auto":
                if type_context not in {
                    TypeUseContext.VARIABLE,
                    TypeUseContext.INLINE_VARIABLE,
                    TypeUseContext.FIELD,
                }:
                    raise ParserException(
                        "'auto' is only allowed on initialized "
                        "variable or field declarations.",
                        self.tokens.cur_tok.location,
                    )
                self.tokens.get_next_token()
                return astx.InferredType()
            template_bound = None
            if allow_template_vars:
                template_bound = self._lookup_template_bound(type_name)

            if type_name in COLUMN_TYPE_NAMES or (
                type_name in {"timestamp", "time"}
                and self._peek_token().value == "["
            ):
                self.tokens.get_next_token()
                arguments: list[astx.DataType | int | str] = []
                if self._is_operator("["):
                    self._consume_operator("[")
                    while not self._is_operator("]"):
                        token = self.tokens.cur_tok
                        if type_name == "arrow_struct":
                            if token.kind != TokenKind.identifier:
                                raise ParserException(
                                    "Struct column fields require names"
                                )
                            arguments.append(cast(str, token.value))
                            self.tokens.get_next_token()
                            self._consume_operator(":")
                            arguments.append(
                                self.parse_type(
                                    type_context=TypeUseContext.NESTED
                                )
                            )
                        elif token.kind == TokenKind.string_literal:
                            arguments.append(cast(str, token.value))
                            self.tokens.get_next_token()
                        elif (
                            token.kind == TokenKind.int_literal
                            or self._is_operator("-")
                        ):
                            sign = 1
                            if self._is_operator("-"):
                                sign = -1
                                self._consume_operator("-")
                            if (
                                cast(TokenKind, self.tokens.cur_tok.kind)
                                != TokenKind.int_literal
                            ):
                                raise ParserException(
                                    "Expected an integer column parameter"
                                )
                            arguments.append(
                                sign * cast(int, self.tokens.cur_tok.value)
                            )
                            self.tokens.get_next_token()
                        else:
                            arguments.append(
                                self.parse_type(
                                    type_context=TypeUseContext.NESTED
                                )
                            )
                        if not self._is_operator(","):
                            break
                        self._consume_operator(",")
                    self._consume_operator("]")
                type_ = astx.ColumnType(type_name, tuple(arguments))
                try:
                    column_arrow_type(type_)
                except (ValueError, TypeError) as error:
                    raise ParserException(str(error)) from error
            elif type_name == "nullable":
                self.tokens.get_next_token()
                self._consume_operator("[")
                inner = self.parse_type(type_context=TypeUseContext.NESTED)
                self._consume_operator("]")
                type_ = astx.NullableType(inner)
            elif type_name in {"list", "sequence"}:
                self.tokens.get_next_token()  # eat list
                self._consume_operator("[")
                elem_type = self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=allow_union,
                    type_context=TypeUseContext.NESTED,
                )
                if self._is_operator(","):
                    raise ParserException(
                        f"{type_name} types accept exactly one element type."
                    )
                self._consume_operator("]")
                type_ = (
                    astx.SequenceType(elem_type)
                    if type_name == "sequence"
                    else astx.ListType([cast(astx.ExprType, elem_type)])
                )
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
            elif type_name == "series":
                self.tokens.get_next_token()  # eat series
                self._consume_operator("[")
                elem_type = self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=True,
                    type_context=TypeUseContext.NESTED,
                )
                if self._is_operator(","):
                    raise ParserException(
                        "Series types accept exactly one element type."
                    )
                self._consume_operator("]")
                try:
                    type_ = series_type(elem_type)
                except ValueError as err:
                    raise ParserException(str(err)) from err
            elif type_name == "dataframe":
                self.tokens.get_next_token()  # eat dataframe
                self._consume_operator("[")
                if self._is_operator("."):
                    self._consume_runtime_shape_marker()
                    self._consume_operator("]")
                    self._ensure_runtime_layout_allowed(
                        "dataframe",
                        type_context,
                    )
                    type_ = runtime_dataframe_type()
                else:
                    columns: list[astx.DataFrameColumn] = []
                    while True:
                        if self.tokens.cur_tok.kind != TokenKind.identifier:
                            raise ParserException(
                                "DataFrame column names must be identifiers."
                            )
                        column_name = cast(str, self.tokens.cur_tok.value)
                        self.tokens.get_next_token()
                        self._consume_operator(":")
                        column_type = self.parse_type(
                            allow_template_vars=allow_template_vars,
                            allow_union=True,
                            type_context=TypeUseContext.NESTED,
                        )
                        nullable = False
                        if isinstance(column_type, astx.UnionType):
                            nullable_members = column_type.members
                            non_null_types = [
                                t
                                for t in nullable_members
                                if not isinstance(t, astx.NoneType)
                            ]
                            if (
                                len(nullable_members) != 2
                                or len(non_null_types) != 1
                            ):
                                raise ParserException(
                                    "DataFrame nullability requires "
                                    "type | none."
                                )
                            column_type = non_null_types[0]
                            nullable = True
                        columns.append(
                            astx.DataFrameColumn(
                                column_name, column_type, nullable=nullable
                            )
                        )
                        if not self._is_operator(","):
                            break
                        self._consume_operator(",")
                    self._consume_operator("]")
                    try:
                        type_ = dataframe_type(tuple(columns))
                    except ValueError as err:
                        raise ParserException(str(err)) from err
            else:
                self.tokens.get_next_token()  # eat type identifier
                if type_name in self.builtin_type_bindings:
                    type_ = copy.deepcopy(
                        self.builtin_type_bindings[type_name]
                    )
                elif type_name in _BUILTIN_TYPE_MAP:
                    type_ = copy.deepcopy(_BUILTIN_TYPE_MAP[type_name])
                elif template_bound is not None:
                    type_ = astx.TemplateTypeVar(
                        type_name,
                        bound=template_bound,
                    )
                elif type_name in self.type_aliases:
                    type_ = self._clone_type_for_alias(type_name)
                elif (
                    type_name in self.known_class_names
                    or type_name in self.imported_type_names
                    or type_name == builtins.BUILTIN_FILE
                    or type_name in builtins.EXCEPTION_BUILTIN_NAMES
                ):
                    type_ = astx.ClassType(type_name)
                else:
                    raise ParserException(
                        f"Parser: Unknown type '{type_name}'.", type_location
                    )

        nullable_annotation = allow_nullable_union and type_context in {
            TypeUseContext.VARIABLE,
            TypeUseContext.INLINE_VARIABLE,
            TypeUseContext.FIELD,
            TypeUseContext.PARAMETER,
            TypeUseContext.RETURN,
        }
        if not (allow_union or nullable_annotation):
            return type_
        pipe = self.tokens.cur_tok
        # Unindented statements have no indentation marker of their own.
        has_pipe = self._is_operator("|") and (
            allow_union or pipe.location.col > 1
        )
        if has_pipe:
            members = (
                list(type_.members)
                if isinstance(type_, astx.UnionType)
                else [type_]
            )
            while self._is_operator("|") and (
                allow_union or self.tokens.cur_tok.location.col > 1
            ):
                self._consume_operator("|")
                member_type = self.parse_type(
                    allow_template_vars=allow_template_vars,
                    allow_union=False,
                    allow_nullable_union=False,
                    type_context=type_context,
                )
                if isinstance(member_type, astx.UnionType):
                    members.extend(member_type.members)
                else:
                    members.append(member_type)
            type_ = astx.UnionType(members)

        # Union aliases can also describe template bounds and column types.
        # Normalize their scalar uses here.
        if (
            nullable_annotation
            and isinstance(type_, astx.UnionType)
            and len(type_.members) == 2
        ):
            non_null = [
                member
                for member in type_.members
                if not isinstance(member, astx.NoneType)
            ]
            if len(non_null) == 1:
                nullable_type = astx.NullableType(non_null[0])
                if type_.alias_name is not None:
                    setattr(nullable_type, "alias_name", type_.alias_name)
                return nullable_type
        if has_pipe and not allow_union:
            raise ParserException(
                "Parenthesize a union type in this annotation.",
                pipe.location,
                code="ARX-PARSE-TYPE-UNION-001",
            )
        return type_
