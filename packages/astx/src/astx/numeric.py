"""
title: Numeric intent and context-dependent source literals.
summary: >-
  Concrete LiteralInt32 and related nodes remain explicitly typed. Source
  literals preserve their magnitude or original decimal spelling until a host
  supplies context and semantic analysis selects a concrete numeric type.
"""

from public import public

from astx.base import NO_SOURCE_LOCATION, DataType, SourceLocation
from astx.literals.base import Literal
from astx.tools.typing import typechecked


@public
@typechecked
class SourceInteger(Literal):
    """
    title: Exact source integer awaiting semantic contextualization.
    attributes:
      value:
        type: int
      type_:
        type: DataType
    """

    value: int
    type_: DataType

    def __init__(
        self, value: int, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Preserve the mathematical integer, without truncating its width.
        parameters:
          value:
            type: int
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.value = value
        self.type_ = DataType()


@public
@typechecked
class SourceFloat(Literal):
    """
    title: Decimal source floating literal retaining its original spelling.
    attributes:
      text:
        type: str
      value:
        type: float
      type_:
        type: DataType
    """

    text: str
    value: float
    type_: DataType

    def __init__(
        self, text: str, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Preserve decimal text until semantic type selection.
        parameters:
          text:
            type: str
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.text = text
        self.value = float(text)
        self.type_ = DataType()
