"""
title: ASTx DataFrame AST nodes.
summary: >-
  Provide internal nodes for Arrow C++ backed DataFrame and Series runtime
  values.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import astx

from astx.tools.typing import typechecked
from astx.types import AnyType


@typechecked
@dataclass(frozen=True)
class DataFrameColumn:
    """
    title: Static DataFrame column schema entry.
    attributes:
      name:
        type: str
      type_:
        type: astx.DataType
      nullable:
        type: bool
    """

    name: str
    type_: astx.DataType
    nullable: bool = False

    def get_struct(self, simplified: bool = False) -> dict[str, object]:
        """
        title: Return the structured representation of the column schema.
        parameters:
          simplified:
            type: bool
        returns:
          type: dict[str, object]
        """
        return {
            "name": self.name,
            "type": self.type_.get_struct(simplified),
            "nullable": self.nullable,
        }


@typechecked
@dataclass(frozen=True)
class DataFrameLiteralColumn:
    """
    title: One DataFrame literal column payload.
    attributes:
      name:
        type: str
      values:
        type: tuple[astx.AST, Ellipsis]
    """

    name: str
    values: tuple[astx.AST, ...]

    def get_struct(self, simplified: bool = False) -> dict[str, object]:
        """
        title: Return the structured representation of the literal column.
        parameters:
          simplified:
            type: bool
        returns:
          type: dict[str, object]
        """
        return {
            "name": self.name,
            "values": [value.get_struct(simplified) for value in self.values],
        }


@typechecked
class SeriesType(AnyType):
    """
    title: Internal Series semantic type.
    summary: >-
      Represent a one-dimensional typed DataFrame column backed by Arrow
      ChunkedArray storage.
    attributes:
      element_type:
        type: astx.DataType | None
      nullable:
        type: bool
    """

    element_type: astx.DataType | None
    nullable: bool

    def __init__(
        self,
        element_type: astx.DataType | None = None,
        *,
        nullable: bool = False,
    ) -> None:
        """
        title: Initialize one Series type.
        parameters:
          element_type:
            type: astx.DataType | None
          nullable:
            type: bool
        """
        super().__init__()
        self.element_type = element_type
        self.nullable = nullable

    def __str__(self) -> str:
        """
        title: Render the Series type.
        returns:
          type: str
        """
        if self.element_type is None:
            return "SeriesType"
        return f"SeriesType[{self.element_type}]"


@typechecked
class DataFrameType(AnyType):
    """
    title: Internal DataFrame semantic type.
    summary: >-
      Represent a heterogeneous named-column table backed by Arrow Table
      storage.
    attributes:
      columns:
        type: tuple[DataFrameColumn, Ellipsis] | None
    """

    columns: tuple[DataFrameColumn, ...] | None

    def __init__(
        self,
        columns: Sequence[DataFrameColumn] | None = None,
    ) -> None:
        """
        title: Initialize one DataFrame type.
        parameters:
          columns:
            type: Sequence[DataFrameColumn] | None
        """
        super().__init__()
        self.columns = None if columns is None else tuple(columns)

    def __str__(self) -> str:
        """
        title: Render the DataFrame type.
        returns:
          type: str
        """
        if self.columns is None:
            return "DataFrameType"
        columns = ", ".join(
            f"{column.name}: {column.type_}" for column in self.columns
        )
        return f"DataFrameType[{columns}]"


@typechecked
class DataFrameLiteral(astx.base.DataType):
    """
    title: Internal Arrow C++ backed DataFrame literal node.
    summary: Build one Arrow C++ table from named column values.
    attributes:
      columns:
        type: tuple[DataFrameLiteralColumn, Ellipsis]
      type_:
        type: DataFrameType
    """

    columns: tuple[DataFrameLiteralColumn, ...]
    type_: DataFrameType

    def __init__(
        self,
        columns: Sequence[DataFrameLiteralColumn],
        *,
        type_: DataFrameType | None = None,
    ) -> None:
        """
        title: Initialize one DataFrame literal.
        parameters:
          columns:
            type: Sequence[DataFrameLiteralColumn]
          type_:
            type: DataFrameType | None
        """
        super().__init__()
        self.columns = tuple(columns)
        self.type_ = type_ or DataFrameType()

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Return the structured representation of the DataFrame literal.
        parameters:
          simplified:
            type: bool
        returns:
          type: astx.base.ReprStruct
        """
        value = {
            "columns": [
                column.get_struct(simplified) for column in self.columns
            ],
            "type": (
                None
                if self.type_.columns is None
                else [
                    column.get_struct(simplified)
                    for column in self.type_.columns
                ]
            ),
        }
        return self._prepare_struct(
            "DataFrameLiteral",
            cast(astx.base.ReprStruct, value),
            simplified,
        )


@typechecked
class DataFrameColumnAccess(astx.base.DataType):
    """
    title: Internal DataFrame column access by static column name.
    attributes:
      base:
        type: astx.AST
      column_name:
        type: str
      type_:
        type: SeriesType
    """

    base: astx.AST
    column_name: str
    type_: SeriesType

    def __init__(self, base: astx.AST, column_name: str) -> None:
        """
        title: Initialize one DataFrame column access.
        parameters:
          base:
            type: astx.AST
          column_name:
            type: str
        """
        super().__init__()
        self.base = base
        self.column_name = column_name
        self.type_ = SeriesType()

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Return the structured representation of the column access.
        parameters:
          simplified:
            type: bool
        returns:
          type: astx.base.ReprStruct
        """
        value = {
            "base": self.base.get_struct(simplified),
            "column_name": self.column_name,
        }
        return self._prepare_struct(
            "DataFrameColumnAccess",
            cast(astx.base.ReprStruct, value),
            simplified,
        )


@typechecked
class DataFrameStringColumnAccess(DataFrameColumnAccess):
    """
    title: Internal DataFrame column access by string key.
    attributes:
      base:
        type: astx.AST
      column_name:
        type: str
      type_:
        type: SeriesType
    """

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Return the structured representation of the string access.
        parameters:
          simplified:
            type: bool
        returns:
          type: astx.base.ReprStruct
        """
        value = {
            "base": self.base.get_struct(simplified),
            "column_name": self.column_name,
        }
        return self._prepare_struct(
            "DataFrameStringColumnAccess",
            cast(astx.base.ReprStruct, value),
            simplified,
        )


@typechecked
class DataFrameRowCount(astx.base.DataType):
    """
    title: Internal DataFrame row-count query.
    attributes:
      base:
        type: astx.AST
      type_:
        type: astx.Int64
    """

    base: astx.AST
    type_: astx.Int64

    def __init__(self, base: astx.AST) -> None:
        """
        title: Initialize one DataFrame row-count query.
        parameters:
          base:
            type: astx.AST
        """
        super().__init__()
        self.base = base
        self.type_ = astx.Int64()

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Return the structured representation of the row-count query.
        parameters:
          simplified:
            type: bool
        returns:
          type: astx.base.ReprStruct
        """
        return self._prepare_struct(
            "DataFrameRowCount",
            self.base.get_struct(simplified),
            simplified,
        )


@typechecked
class DataFrameColumnCount(astx.base.DataType):
    """
    title: Internal DataFrame column-count query.
    attributes:
      base:
        type: astx.AST
      type_:
        type: astx.Int64
    """

    base: astx.AST
    type_: astx.Int64

    def __init__(self, base: astx.AST) -> None:
        """
        title: Initialize one DataFrame column-count query.
        parameters:
          base:
            type: astx.AST
        """
        super().__init__()
        self.base = base
        self.type_ = astx.Int64()

    def get_struct(self, simplified: bool = False) -> astx.base.ReprStruct:
        """
        title: Return the structured representation of the column-count query.
        parameters:
          simplified:
            type: bool
        returns:
          type: astx.base.ReprStruct
        """
        return self._prepare_struct(
            "DataFrameColumnCount",
            self.base.get_struct(simplified),
            simplified,
        )


@typechecked
class DataFrameRetain(astx.base.DataType):
    """
    title: Internal explicit retain for DataFrame-backed storage.
    attributes:
      base:
        type: astx.AST
      type_:
        type: astx.Int32
    """

    base: astx.AST
    type_: astx.Int32

    def __init__(self, base: astx.AST) -> None:
        """
        title: Initialize one DataFrame retain helper.
        parameters:
          base:
            type: astx.AST
        """
        super().__init__()
        self.base = base
        self.type_ = astx.Int32()


@typechecked
class DataFrameRelease(astx.base.DataType):
    """
    title: Internal explicit release for DataFrame-backed storage.
    attributes:
      base:
        type: astx.AST
      type_:
        type: astx.Int32
    """

    base: astx.AST
    type_: astx.Int32

    def __init__(self, base: astx.AST) -> None:
        """
        title: Initialize one DataFrame release helper.
        parameters:
          base:
            type: astx.AST
        """
        super().__init__()
        self.base = base
        self.type_ = astx.Int32()


@typechecked
class SeriesRetain(astx.base.DataType):
    """
    title: Internal explicit retain for Series-backed storage.
    attributes:
      base:
        type: astx.AST
      type_:
        type: astx.Int32
    """

    base: astx.AST
    type_: astx.Int32

    def __init__(self, base: astx.AST) -> None:
        """
        title: Initialize one Series retain helper.
        parameters:
          base:
            type: astx.AST
        """
        super().__init__()
        self.base = base
        self.type_ = astx.Int32()


@typechecked
class SeriesRelease(astx.base.DataType):
    """
    title: Internal explicit release for Series-backed storage.
    attributes:
      base:
        type: astx.AST
      type_:
        type: astx.Int32
    """

    base: astx.AST
    type_: astx.Int32

    def __init__(self, base: astx.AST) -> None:
        """
        title: Initialize one Series release helper.
        parameters:
          base:
            type: astx.AST
        """
        super().__init__()
        self.base = base
        self.type_ = astx.Int32()


__all__ = [
    "DataFrameColumn",
    "DataFrameColumnAccess",
    "DataFrameColumnCount",
    "DataFrameLiteral",
    "DataFrameLiteralColumn",
    "DataFrameRelease",
    "DataFrameRetain",
    "DataFrameRowCount",
    "DataFrameStringColumnAccess",
    "DataFrameType",
    "SeriesRelease",
    "SeriesRetain",
    "SeriesType",
]
