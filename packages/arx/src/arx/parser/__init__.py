"""
title: parser module gather all functions and classes for parsing.
"""

from __future__ import annotations

import astx

from arx.exceptions import ParserException
from arx.lexer import TokenList
from arx.parser.control_flow import ControlFlowParserMixin
from arx.parser.core import ParserCore
from arx.parser.declarations import DeclarationParserMixin
from arx.parser.expressions import ExpressionParserMixin
from arx.parser.imports import ImportParserMixin
from arx.parser.state import (
    INDENT_SIZE,
    ParsedAnnotation,
    ParsedDeclarationPrefixes,
)
from arx.parser.types import TypeParserMixin
from arx.tensor import TensorBinding


class Parser(
    ImportParserMixin,
    DeclarationParserMixin,
    ExpressionParserMixin,
    ControlFlowParserMixin,
    TypeParserMixin,
    ParserCore,
):
    """
    title: Parser class.
    attributes:
      bin_op_precedence:
        type: dict[str, int]
      indent_level:
        type: int
      known_class_names:
        type: set[str]
      tensor_scopes:
        type: list[dict[str, TensorBinding | None]]
      return_type_scopes:
        type: list[astx.DataType]
      template_type_scopes:
        type: list[dict[str, astx.DataType]]
      type_aliases:
        type: dict[str, astx.DataType]
      value_scopes:
        type: list[set[str]]
      tokens:
        type: TokenList
    """

    bin_op_precedence: dict[str, int] = {}
    indent_level: int = 0
    known_class_names: set[str]
    tensor_scopes: list[dict[str, TensorBinding | None]]
    return_type_scopes: list[astx.DataType]
    template_type_scopes: list[dict[str, astx.DataType]]
    type_aliases: dict[str, astx.DataType]
    value_scopes: list[set[str]]
    tokens: TokenList

    def parse(
        self,
        tokens: TokenList,
        module_name: str = "main",
    ) -> astx.Module:
        """
        title: Parse tokens and attach the active token location to failures.
        parameters:
          tokens:
            type: TokenList
          module_name:
            type: str
        returns:
          type: astx.Module
        """
        try:
            return super().parse(tokens, module_name)
        except RecursionError:
            raise ParserException(
                "Source nesting exceeds the parser recursion limit",
                self.tokens.cur_tok.location,
                code="ARX-PARSE-DEPTH-001",
            ) from None
        except ParserException as err:
            raise err.attach_location(self.tokens.cur_tok.location) from None


__all__ = [
    "INDENT_SIZE",
    "ParsedAnnotation",
    "ParsedDeclarationPrefixes",
    "Parser",
]
