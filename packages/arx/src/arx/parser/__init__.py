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
from arx.parser.exceptions import ExceptionParserMixin
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
    ExceptionParserMixin,
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
      bin_op_precedence: Bin op precedence.
      indent_level: Indent level.
      known_class_names: Known class names.
      imported_type_names: Imported type names.
      namespace_roots: Namespace roots.
      builtin_type_bindings: Builtin type bindings.
      tensor_scopes: Tensor scopes.
      return_type_scopes: Return type scopes.
      template_type_scopes: Template type scopes.
      type_aliases: Type aliases.
      value_scopes: Value scopes.
      tokens: Tokens in source order.
    """

    bin_op_precedence: dict[str, int] = {}
    indent_level: int = 0
    known_class_names: set[str]
    imported_type_names: set[str]
    namespace_roots: set[str]
    builtin_type_bindings: dict[str, astx.DataType]
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
        *,
        builtin_types: dict[str, astx.DataType] | None = None,
    ) -> astx.Module:
        """
        title: Parse tokens and attach the active token location
          to failures.
        parameters:
          tokens: Tokens in source order.
          module_name: Module name to resolve.
          builtin_types: Types of builtin.
        returns: Parsed tokens and attach the active token location
          to failures.
        """
        try:
            return super().parse(
                tokens, module_name, builtin_types=builtin_types
            )
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
