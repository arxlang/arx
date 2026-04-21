"""
title: parser module gather all functions and classes for parsing.
"""

from __future__ import annotations

from irx import astx

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
      template_type_scopes:
        type: list[dict[str, astx.DataType]]
      value_scopes:
        type: list[set[str]]
      tokens:
        type: TokenList
    """

    bin_op_precedence: dict[str, int] = {}
    indent_level: int = 0
    known_class_names: set[str]
    template_type_scopes: list[dict[str, astx.DataType]]
    value_scopes: list[set[str]]
    tokens: TokenList


__all__ = [
    "INDENT_SIZE",
    "ParsedAnnotation",
    "ParsedDeclarationPrefixes",
    "Parser",
]
