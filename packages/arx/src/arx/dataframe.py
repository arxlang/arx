"""
title: DataFrame surface helpers for Arx.
summary: >-
  Adapt Arx surface dataframe syntax to IRx DataFrame nodes while keeping user-
  facing schema rules local to Arx.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import astx

from irx.analysis.resolved_nodes import SemanticInfo
from irx.builtins.collections.dataframe import (
    DATAFRAME_SCHEMA_EXTRA,
    DataFrameSchema,
    dataframe_column_type_is_supported,
    schema_from_type,
)


@dataclass(frozen=True)
class DataFrameBinding:
    """
    title: Static DataFrame binding metadata.
    attributes:
      schema:
        type: DataFrameSchema
    """

    schema: DataFrameSchema


def is_dataframe_type(data_type: astx.DataType | None) -> bool:
    """
    title: Return whether one type is a DataFrame type.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: bool
    """
    return isinstance(data_type, astx.DataFrameType)


def is_series_type(data_type: astx.DataType | None) -> bool:
    """
    title: Return whether one type is a Series type.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: bool
    """
    return isinstance(data_type, astx.SeriesType)


def dataframe_type(
    columns: tuple[astx.DataFrameColumn, ...],
) -> astx.DataFrameType:
    """
    title: Build one static-schema DataFrame surface type.
    parameters:
      columns:
        type: tuple[astx.DataFrameColumn, Ellipsis]
    returns:
      type: astx.DataFrameType
    """
    if not columns:
        raise ValueError("dataframe types require at least one column")
    seen: set[str] = set()
    for column in columns:
        if column.name in seen:
            raise ValueError(f"duplicate dataframe column '{column.name}'")
        seen.add(column.name)
        if column.nullable:
            raise ValueError(
                "nullable dataframe columns are not supported yet"
            )
        if not dataframe_column_type_is_supported(column.type_):
            raise ValueError(
                "dataframe columns currently support only fixed-width "
                "numeric and bool types"
            )
    return astx.DataFrameType(columns)


def runtime_dataframe_type() -> astx.DataFrameType:
    """
    title: Build one runtime-schema DataFrame surface type.
    returns:
      type: astx.DataFrameType
    """
    return astx.DataFrameType()


def series_type(element_type: astx.DataType) -> astx.SeriesType:
    """
    title: Build one Series surface type.
    parameters:
      element_type:
        type: astx.DataType
    returns:
      type: astx.SeriesType
    """
    if not dataframe_column_type_is_supported(element_type):
        raise ValueError(
            "series element types currently support only fixed-width "
            "numeric and bool types"
        )
    return astx.SeriesType(element_type)


def binding_from_type(
    data_type: astx.DataType | None,
) -> DataFrameBinding | None:
    """
    title: Build one static DataFrame binding from one declared type.
    parameters:
      data_type:
        type: astx.DataType | None
    returns:
      type: DataFrameBinding | None
    """
    if not isinstance(data_type, astx.DataFrameType):
        return None
    schema = schema_from_type(data_type)
    if schema is None:
        return None
    return DataFrameBinding(schema)


def attach_binding(node: astx.AST, binding: DataFrameBinding) -> None:
    """
    title: Attach static DataFrame metadata to one AST node.
    parameters:
      node:
        type: astx.AST
      binding:
        type: DataFrameBinding
    """
    info = cast(SemanticInfo | None, getattr(node, "semantic", None))
    if info is None or not isinstance(info, SemanticInfo):
        info = SemanticInfo()
        setattr(node, "semantic", info)
    info.extras[DATAFRAME_SCHEMA_EXTRA] = binding.schema


def coerce_expression(
    expr: astx.Expr,
    target_type: astx.DataType,
    *,
    context: str,
) -> astx.Expr:
    """
    title: Coerce one parsed expression into one declared DataFrame type.
    parameters:
      expr:
        type: astx.Expr
      target_type:
        type: astx.DataType
      context:
        type: str
    returns:
      type: astx.Expr
    """
    del context
    if not isinstance(target_type, astx.DataFrameType):
        return expr
    if not isinstance(expr, astx.DataFrameLiteral):
        return expr
    binding = binding_from_type(target_type)
    if binding is None:
        raise ValueError(
            "dataframe literals require a static dataframe schema"
        )
    coerced = astx.DataFrameLiteral(
        _columns_in_schema_order(expr, binding.schema),
        type_=target_type,
    )
    attach_binding(coerced, binding)
    return coerced


def column_type(
    binding: DataFrameBinding,
    column_name: str,
) -> astx.DataType | None:
    """
    title: Return the type of one DataFrame column.
    parameters:
      binding:
        type: DataFrameBinding
      column_name:
        type: str
    returns:
      type: astx.DataType | None
    """
    column = binding.schema.column(column_name)
    return None if column is None else column.type_


def _columns_in_schema_order(
    literal: astx.DataFrameLiteral,
    schema: DataFrameSchema,
) -> tuple[astx.DataFrameLiteralColumn, ...]:
    """
    title: Return literal columns ordered by schema.
    parameters:
      literal:
        type: astx.DataFrameLiteral
      schema:
        type: DataFrameSchema
    returns:
      type: tuple[astx.DataFrameLiteralColumn, Ellipsis]
    """
    literal_columns = {column.name: column for column in literal.columns}
    ordered: list[astx.DataFrameLiteralColumn] = []
    for schema_column in schema.columns:
        column = literal_columns.get(schema_column.name)
        if column is None:
            raise ValueError(
                f"dataframe literal is missing column '{schema_column.name}'"
            )
        ordered.append(column)
    schema_column_names = {column.name for column in schema.columns}
    extra = sorted(set(literal_columns) - schema_column_names)
    if extra:
        raise ValueError(
            "dataframe literal has undeclared columns: " + ", ".join(extra)
        )
    return tuple(ordered)


__all__ = [
    "DataFrameBinding",
    "attach_binding",
    "binding_from_type",
    "coerce_expression",
    "column_type",
    "dataframe_type",
    "is_dataframe_type",
    "is_series_type",
    "runtime_dataframe_type",
    "series_type",
]
