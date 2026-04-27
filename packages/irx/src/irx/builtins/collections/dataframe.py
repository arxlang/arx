"""
title: DataFrame helpers layered on the builtin Arrow runtime.
summary: >-
  Define IRx's backend-neutral DataFrame metadata helpers on top of Arrow Table
  and ChunkedArray storage.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx

from public import public

from irx.builtins.collections.array_primitives import (
    ARRAY_PRIMITIVE_TYPE_SPECS,
)
from irx.builtins.collections.tensor import tensor_primitive_type_name
from irx.typecheck import typechecked

DATAFRAME_SCHEMA_EXTRA = "dataframe_schema"
DATAFRAME_COLUMN_INDEX_EXTRA = "dataframe_column_index"
SERIES_ELEMENT_TYPE_EXTRA = "series_element_type"
SERIES_NULLABLE_EXTRA = "series_nullable"


@public
@typechecked
@dataclass(frozen=True)
class DataFrameSchemaColumn:
    """
    title: Static DataFrame schema column metadata.
    attributes:
      name:
        type: str
      type_:
        type: astx.DataType
      nullable:
        type: bool
      index:
        type: int
    """

    name: str
    type_: astx.DataType
    nullable: bool
    index: int


@public
@typechecked
@dataclass(frozen=True)
class DataFrameSchema:
    """
    title: Static DataFrame schema metadata.
    attributes:
      columns:
        type: tuple[DataFrameSchemaColumn, Ellipsis]
    """

    columns: tuple[DataFrameSchemaColumn, ...]

    @property
    def column_count(self) -> int:
        """
        title: Return the number of columns in this schema.
        returns:
          type: int
        """
        return len(self.columns)

    def column(self, name: str) -> DataFrameSchemaColumn | None:
        """
        title: Return one schema column by name.
        parameters:
          name:
            type: str
        returns:
          type: DataFrameSchemaColumn | None
        """
        for column in self.columns:
            if column.name == name:
                return column
        return None


@public
@typechecked
def schema_from_type(
    type_: astx.DataFrameType,
) -> DataFrameSchema | None:
    """
    title: Return static schema metadata from one DataFrame type.
    parameters:
      type_:
        type: astx.DataFrameType
    returns:
      type: DataFrameSchema | None
    """
    if type_.columns is None:
        return None
    return DataFrameSchema(
        tuple(
            DataFrameSchemaColumn(
                name=column.name,
                type_=column.type_,
                nullable=column.nullable,
                index=index,
            )
            for index, column in enumerate(type_.columns)
        )
    )


@public
@typechecked
def dataframe_primitive_type_name(
    type_: astx.DataType | None,
) -> str | None:
    """
    title: Return the builtin primitive storage name for one column type.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: str | None
    """
    return tensor_primitive_type_name(type_)


@public
@typechecked
def dataframe_type_id(type_: astx.DataType | None) -> int | None:
    """
    title: Return the Arrow runtime type id for one supported column type.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: int | None
    """
    primitive_name = dataframe_primitive_type_name(type_)
    if primitive_name is None:
        return None
    spec = ARRAY_PRIMITIVE_TYPE_SPECS.get(primitive_name)
    return None if spec is None else spec.type_id


@public
@typechecked
def dataframe_column_type_is_supported(type_: astx.DataType | None) -> bool:
    """
    title: Return whether one type is supported for MVP DataFrame columns.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: bool
    """
    return dataframe_type_id(type_) is not None


__all__ = [
    "DATAFRAME_COLUMN_INDEX_EXTRA",
    "DATAFRAME_SCHEMA_EXTRA",
    "SERIES_ELEMENT_TYPE_EXTRA",
    "SERIES_NULLABLE_EXTRA",
    "DataFrameSchema",
    "DataFrameSchemaColumn",
    "dataframe_column_type_is_supported",
    "dataframe_primitive_type_name",
    "dataframe_type_id",
    "schema_from_type",
]
