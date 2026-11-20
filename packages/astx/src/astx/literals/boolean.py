"""
title: ASTx Data Types module.
"""

from __future__ import annotations

from public import public

from astx.base import (
    NO_SOURCE_LOCATION,
    SourceLocation,
)
from astx.literals.base import Literal
from astx.tools.typing import typechecked
from astx.types.boolean import Boolean


@public
@typechecked
class LiteralBoolean(Literal):
    """
    title: LiteralBoolean data type class.
    attributes:
      type_: Type associated with this expression.
      loc: Source coordinates attached to this node.
      value: Stored value.
    """

    type_: Boolean
    loc: SourceLocation

    value: bool

    def __init__(
        self, value: bool, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Initialize LiteralBoolean.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc)
        self.value = value
        self.type_ = Boolean()
        self.loc = loc
