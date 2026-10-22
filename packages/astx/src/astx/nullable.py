"""
title: Nullable scalar and parameterized column modeling.
"""

from __future__ import annotations

from typing import cast

from public import private, public

from astx.base import (
    NO_SOURCE_LOCATION,
    DataType,
    Expr,
    ReprStruct,
    SourceLocation,
)
from astx.tools.typing import typechecked
from astx.types.base import AnyType


@public
@typechecked
class NullableType(AnyType):
    """
    title: A scalar value paired with an explicit validity bit.
    attributes:
      value_type:
        type: DataType
    """

    value_type: DataType

    def __init__(self, value_type: DataType) -> None:
        """
        title: Initialize a nullable scalar type.
        parameters:
          value_type:
            type: DataType
        """
        super().__init__()
        self.value_type = value_type

    def __str__(self) -> str:
        """
        title: Render the nullable type.
        returns:
          type: str
        """
        return f"nullable[{column_type_name(self.value_type)}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "NullableType",
            cast(
                ReprStruct,
                {"value_type": self.value_type.get_struct(simplified)},
            ),
            simplified,
        )


@public
@typechecked
class ColumnType(AnyType):
    """
    title: Parameterized column storage type, not a standalone scalar.
    attributes:
      column_kind:
        type: str
      arguments:
        type: tuple[DataType | int | str, Ellipsis]
    """

    column_kind: str
    arguments: tuple[DataType | int | str, ...]

    def __init__(
        self, name: str, arguments: tuple[DataType | int | str, ...] = ()
    ) -> None:
        """
        title: Model storage parameters without a backend dependency.
        parameters:
          name:
            type: str
          arguments:
            type: tuple[DataType | int | str, Ellipsis]
        """
        super().__init__()
        self.column_kind = name
        self.arguments = arguments

    def __str__(self) -> str:
        """
        title: Render all storage parameters.
        returns:
          type: str
        """
        parameters = ", ".join(column_type_name(a) for a in self.arguments)
        return f"{self.column_kind}[{parameters}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "ColumnType",
            cast(
                ReprStruct,
                {
                    "kind": self.column_kind,
                    "arguments": [
                        a.get_struct(simplified)
                        if isinstance(a, DataType)
                        else a
                        for a in self.arguments
                    ],
                },
            ),
            simplified,
        )


@public
@typechecked
class NullCheck(DataType):
    """
    title: Test a scalar validity bit or produce a Series null mask.
    attributes:
      value:
        type: Expr
      type_:
        type: DataType
    """

    value: Expr
    type_: DataType

    def __init__(
        self, value: Expr, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Initialize a null test.
        parameters:
          value:
            type: Expr
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.type_ = AnyType()
        self.value = value

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "NullCheck",
            cast(ReprStruct, {"value": self.value.get_struct(simplified)}),
            simplified,
        )


@public
@typechecked
class NullFill(DataType):
    """
    title: Replace nulls with an eagerly evaluated non-null scalar.
    attributes:
      value:
        type: Expr
      replacement:
        type: Expr
      type_:
        type: DataType
    """

    value: Expr
    replacement: Expr
    type_: DataType

    def __init__(
        self,
        value: Expr,
        replacement: Expr,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Initialize a null replacement.
        parameters:
          value:
            type: Expr
          replacement:
            type: Expr
          loc:
            type: SourceLocation
        """
        super().__init__(loc=loc)
        self.type_ = AnyType()
        self.value = value
        self.replacement = replacement

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return self._prepare_struct(
            "NullFill",
            cast(
                ReprStruct,
                {
                    "value": self.value.get_struct(simplified),
                    "replacement": self.replacement.get_struct(simplified),
                },
            ),
            simplified,
        )


@private
@typechecked
def column_type_name(value: DataType | str | int) -> str:
    """
    title: Render deterministic parameter names, independent of AST counters.
    parameters:
      value:
        type: DataType | str | int
    returns:
      type: str
    """
    if isinstance(value, (NullableType, ColumnType)):
        return str(value)
    return type(value).__name__ if isinstance(value, DataType) else repr(value)
