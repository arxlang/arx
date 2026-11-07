"""
title: ASTx Data Types module.
"""

from __future__ import annotations

from public import public

from astx.base import (
    DataType,
)
from astx.tools.typing import typechecked


@public
@typechecked
class AnyType(DataType):
    """
    title: Generic data type expression.
    """


@public
@typechecked
class NoneType(AnyType):
    """
    title: NoneType data type expression.
    """


@public
@typechecked
class InferredType(DataType):
    """
    title: Request one concrete declaration type from its initializer.
    summary: >-
      This source annotation is not a dynamic value type or a wildcard.
      Semantic analysis must resolve it before publishing storage or layout;
      retaining the marker permits independent reanalysis of the source AST.
    """

    def __init__(self) -> None:
        """
        title: Initialize an initializer-based inference request.
        """
        super().__init__()
