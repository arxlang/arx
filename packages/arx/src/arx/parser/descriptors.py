"""
title: Builtin immutable datatype, field and schema literal syntax.
summary: Semantic validity belongs to IRx; this module only parses structure.
"""

from __future__ import annotations

from typing import cast

import astx

from arx.exceptions import ParserException
from arx.lexer import TokenKind
from arx.parser.base import ParserMixinBase

DESCRIPTOR_LITERALS = frozenset({"datatype", "field", "schema"})
DESCRIPTOR_QUERIES = {item.value: item for item in astx.DescriptorOperation}
LOGICAL_ALIASES = {
    "i8": "int8",
    "i16": "int16",
    "i32": "int32",
    "i64": "int64",
    "u8": "uint8",
    "u16": "uint16",
    "u32": "uint32",
    "u64": "uint64",
    "f16": "float16",
    "f32": "float32",
    "f64": "float64",
    "str": "string",
    "boolean": "bool",
    "none": "null",
}
MAX_LITERAL_DEPTH = 64


class DescriptorParser:
    """
    title: Parse descriptor syntax without maintaining semantic binding tables.
    attributes:
      parser:
        type: ParserMixinBase
    """

    parser: ParserMixinBase

    def __init__(self, parser: ParserMixinBase) -> None:
        """
        title: Share the host's token stream and grammar utilities.
        parameters:
          parser:
            type: ParserMixinBase
        """
        self.parser = parser

    def text(self) -> str:
        """
        title: Consume a name or quoted UTF-8 field name.
        returns:
          type: str
        """
        token = self.parser.tokens.cur_tok
        if token.kind not in {TokenKind.identifier, TokenKind.string_literal}:
            raise ParserException("Expected a descriptor name or string.")
        self.parser.tokens.get_next_token()
        return cast(str, token.value)

    def metadata(self) -> tuple[tuple[bytes, bytes], ...]:
        """
        title: >-
          Parse optional UTF-8 metadata while preserving duplicates for
          analysis.
        returns:
          type: tuple[tuple[bytes, bytes], Ellipsis]
        """
        p = self.parser
        if not p._is_operator("{"):
            return ()
        p._consume_operator("{")
        result: list[tuple[bytes, bytes]] = []
        while not p._is_operator("}"):
            key = self.text().encode("utf8")
            p._consume_operator(":")
            value = self.text().encode("utf8")
            result.append((key, value))
            if p._is_operator("}"):
                break
            p._consume_operator(",")
        p._consume_operator("}")
        return tuple(result)

    def parameter_value(
        self, key: astx.ParameterKind
    ) -> astx.schema.ParameterValue:
        """
        title: Parse scalar and integer-vector logical parameters.
        parameters:
          key:
            type: astx.ParameterKind
        returns:
          type: astx.schema.ParameterValue
        """
        p = self.parser
        token = p.tokens.cur_tok
        if p._is_operator("["):
            p._consume_operator("[")
            values: list[int] = []
            while not p._is_operator("]"):
                values.append(self.integer())
                if p._is_operator("]"):
                    break
                p._consume_operator(",")
            p._consume_operator("]")
            return tuple(values)
        if token.kind == TokenKind.int_literal or p._is_operator("-"):
            return self.integer()
        if token.kind == TokenKind.bool_literal:
            p.tokens.get_next_token()
            return cast(bool, token.value)
        if token.kind == TokenKind.string_literal:
            p.tokens.get_next_token()
            value = cast(str, token.value)
            if key is astx.ParameterKind.TIME_UNIT:
                try:
                    return astx.TimeUnit(value)
                except ValueError:
                    return value  # IRx produces the parameter diagnostic.
            if key is astx.ParameterKind.EXTENSION_METADATA:
                return value.encode("utf8")
            return value
        raise ParserException("Expected a literal descriptor parameter value.")

    def integer(self) -> int:
        """
        title: Read signed descriptor integers without expression evaluation.
        returns:
          type: int
        """
        p = self.parser
        sign = -1 if p._is_operator("-") else 1
        if sign < 0:
            p._consume_operator("-")
        token = p.tokens.cur_tok
        if token.kind != TokenKind.int_literal:
            raise ParserException("Expected an integer descriptor parameter.")
        p.tokens.get_next_token()
        return sign * cast(int, token.value)

    def parameters(self) -> tuple[astx.LogicalParameter, ...]:
        """
        title: Parse named parameters without normalizing semantic constraints.
        returns:
          type: tuple[astx.LogicalParameter, Ellipsis]
        """
        p = self.parser
        if not p._is_operator("("):
            return ()
        p._consume_operator("(")
        result: list[astx.LogicalParameter] = []
        while not p._is_operator(")"):
            name = self.text()
            try:
                key = astx.ParameterKind(name)
            except ValueError:
                raise ParserException(
                    f"Unknown descriptor parameter '{name}'."
                ) from None
            p._consume_operator("=")
            result.append(
                astx.LogicalParameter(key, self.parameter_value(key))
            )
            if p._is_operator(")"):
                break
            p._consume_operator(",")
        p._consume_operator(")")
        return tuple(result)

    def logical_type(self, depth: int = 0) -> astx.LogicalType:
        """
        title: Parse one recursive logical type in a descriptor context.
        parameters:
          depth:
            type: int
        returns:
          type: astx.LogicalType
        """
        if depth > MAX_LITERAL_DEPTH:
            raise ParserException(
                "Descriptor literal exceeds maximum nesting depth."
            )
        p = self.parser
        if p.tokens.cur_tok.kind == TokenKind.none_literal:
            p.tokens.get_next_token()
            name = "null"
        elif p.tokens.cur_tok.kind == TokenKind.binary_op:
            p.tokens.get_next_token()
            name = "binary"
        else:
            name = self.text()
        try:
            kind = astx.LogicalKind(LOGICAL_ALIASES.get(name, name))
        except ValueError:
            raise ParserException(f"Unknown logical type '{name}'.") from None
        parameters = self.parameters()
        fields = self.fields(depth + 1) if p._is_operator("[") else ()
        return astx.LogicalType(kind, parameters=parameters, fields=fields)

    def field(self, depth: int = 0) -> astx.SchemaField:
        """
        title: Parse a field with independent nullability and metadata.
        parameters:
          depth:
            type: int
        returns:
          type: astx.SchemaField
        """
        p = self.parser
        name = self.text()
        p._consume_operator(":")
        logical = self.logical_type(depth)
        nullable = False
        if p._is_operator("|"):
            p._consume_operator("|")
            if p.tokens.cur_tok.kind != TokenKind.none_literal:
                raise ParserException(
                    "Descriptor fields support only '| none'."
                )
            p.tokens.get_next_token()
            nullable = True
        return astx.SchemaField(
            name, logical, nullable=nullable, metadata=self.metadata()
        )

    def fields(self, depth: int = 0) -> tuple[astx.SchemaField, ...]:
        """
        title: >-
          Parse an ordered bracketed field sequence, including empty schemas.
        parameters:
          depth:
            type: int
        returns:
          type: tuple[astx.SchemaField, Ellipsis]
        """
        p = self.parser
        p._consume_operator("[")
        fields: list[astx.SchemaField] = []
        while not p._is_operator("]"):
            fields.append(self.field(depth))
            if p._is_operator("]"):
                break
            p._consume_operator(",")
        p._consume_operator("]")
        return tuple(fields)

    def literal(self, name: str, loc: astx.SourceLocation) -> astx.DataType:
        """
        title: Construct focused ASTx descriptor nodes directly.
        parameters:
          name:
            type: str
          loc:
            type: astx.SourceLocation
        returns:
          type: astx.DataType
        """
        p = self.parser
        if name == "schema":
            fields = self.fields()
            return astx.SchemaLiteral(
                astx.Schema(fields, metadata=self.metadata()), loc=loc
            )
        p._consume_operator("[")
        if name == "field":
            field = self.field()
            p._consume_operator("]")
            return astx.FieldLiteral(field, loc=loc)
        if name != "datatype":
            raise ParserException(f"Unknown descriptor literal '{name}'.")
        value = self.logical_type()
        p._consume_operator("]")
        return astx.TypeDescriptorLiteral(value, loc=loc)
