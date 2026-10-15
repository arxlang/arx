"""
title: First-class tabular type and literal syntax.
"""

from __future__ import annotations

from typing import cast

import astx

from arx.parser.base import ParserMixinBase
from arx.parser.descriptors import DescriptorParser


class TabularParser:
    """
    title: Parse tabular structure while leaving schema validity to IRx.
    attributes:
      parser:
        type: ParserMixinBase
    """

    parser: ParserMixinBase

    def __init__(self, parser: ParserMixinBase) -> None:
        """
        title: Share the parser token stream without semantic binding state.
        parameters:
          parser:
            type: ParserMixinBase
        """
        self.parser = parser

    def type(
        self, name: str = "table"
    ) -> astx.RecordBatchType | astx.TableType:
        """
        title: Parse a static schema or a bare runtime-schema type.
        parameters:
          name:
            type: str
        returns:
          type: astx.RecordBatchType | astx.TableType
        """
        parser = self.parser
        constructor = (
            astx.TableType if name == "table" else astx.RecordBatchType
        )
        if not parser._is_operator("["):
            return constructor()
        descriptors = DescriptorParser(parser)
        fields = descriptors.fields()
        return constructor(
            astx.Schema(fields, metadata=descriptors.metadata())
        )

    def literal(
        self, loc: astx.SourceLocation, name: str = "table"
    ) -> astx.TabularLiteral:
        """
        title: Parse an explicit row count followed by column owners.
        parameters:
          loc:
            type: astx.SourceLocation
          name:
            type: str
        returns:
          type: astx.TabularLiteral
        """
        type_ = self.type(name)
        parser = self.parser
        parser._consume_operator("(")
        values: list[astx.Expr] = []
        while not parser._is_operator(")"):
            values.append(cast(astx.Expr, parser.parse_expression()))
            if parser._is_operator(")"):
                break
            parser._consume_operator(",")
        parser._consume_operator(")")
        return astx.TabularLiteral(type_, tuple(values), loc=loc)
