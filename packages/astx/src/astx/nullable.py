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
      value_type: Type of the stored value.
    """

    value_type: DataType

    def __init__(self, value_type: DataType) -> None:
        """
        title: Initialize a nullable scalar type.
        parameters:
          value_type: Type of the stored value.
        """
        super().__init__()
        self.value_type = value_type

    def __str__(self) -> str:
        """
        title: Render the nullable type.
        returns: String representation of this instance.
        """
        return f"nullable[{column_type_name(self.value_type)}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
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
      column_kind: Column kind.
      arguments: Arguments supplied to the call.
    """

    column_kind: str
    arguments: tuple[DataType | int | str, ...]

    def __init__(
        self, name: str, arguments: tuple[DataType | int | str, ...] = ()
    ) -> None:
        """
        title: Model storage parameters without a backend dependency.
        parameters:
          name: Name identifying the declaration or operation.
          arguments: Arguments supplied to the call.
        """
        super().__init__()
        self.column_kind = name
        self.arguments = arguments

    def __str__(self) -> str:
        """
        title: Render all storage parameters.
        returns: String representation of this instance.
        """
        parameters = ", ".join(column_type_name(a) for a in self.arguments)
        return f"{self.column_kind}[{parameters}]"

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
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
      value: Stored value.
      type_: Type associated with this expression.
    """

    value: Expr
    type_: DataType

    def __init__(
        self, value: Expr, loc: SourceLocation = NO_SOURCE_LOCATION
    ) -> None:
        """
        title: Initialize a null test.
        parameters:
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.type_ = AnyType()
        self.value = value

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
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
      value: Stored value.
      replacement: Replacement.
      type_: Type associated with this expression.
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
          value: Value to process.
          replacement: Replacement.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.type_ = AnyType()
        self.value = value
        self.replacement = replacement

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Render the node with all typed children.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
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
      value: Value to process.
    returns: 'Result of this operation: render deterministic parameter
      names, independent of AST counters.'
    """
    if isinstance(value, (NullableType, ColumnType)):
        return str(value)
    return type(value).__name__ if isinstance(value, DataType) else repr(value)


@public
@typechecked
class SeriesReduction(DataType):
    """
    title: Reduce a column using an explicit null-skipping aggregate.
    attributes:
      operation: Operation to resolve or execute.
      value: Stored value.
      type_: Type associated with this expression.
    """

    operation: str
    value: Expr
    type_: DataType

    def __init__(
        self,
        operation: str,
        value: Expr,
        loc: SourceLocation = NO_SOURCE_LOCATION,
    ) -> None:
        """
        title: Model a reduction without choosing backend kernel types.
        parameters:
          operation: Operation to resolve or execute.
          value: Value to process.
          loc: Source coordinates associated with the node.
        """
        super().__init__(loc=loc)
        self.operation = operation
        self.value = value
        self.type_ = AnyType()

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Include the operation and operand in structural output.
        parameters:
          simplified: Whether to request the compact representation.
        returns: Structured representation of this node.
        """
        return self._prepare_struct(
            "SeriesReduction",
            cast(
                ReprStruct,
                {
                    "operation": self.operation,
                    "value": self.value.get_struct(simplified),
                },
            ),
            simplified,
        )
