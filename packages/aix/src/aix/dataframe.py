"""
title: DataFrame surface helpers for Arx.
summary: Adapt Arx surface dataframe syntax to IRx DataFrame nodes while
  keeping user- facing schema rules local to Arx.
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
      schema: Declared data schema.
    """

    schema: DataFrameSchema


def is_dataframe_type(data_type: astx.DataType | None) -> bool:
    """
    title: Return whether one type is a DataFrame type.
    parameters:
      data_type: Declared data type.
    returns: Whether one type is a DataFrame type.
    """
    return isinstance(data_type, astx.DataFrameType)


def is_series_type(data_type: astx.DataType | None) -> bool:
    """
    title: Return whether one type is a Series type.
    parameters:
      data_type: Declared data type.
    returns: Whether one type is a Series type.
    """
    return isinstance(data_type, astx.SeriesType)


def dataframe_type(
    columns: tuple[astx.DataFrameColumn, ...],
) -> astx.DataFrameType:
    """
    title: Build one static-schema DataFrame surface type.
    parameters:
      columns: Column declarations or values.
    returns: Constructed one static-schema DataFrame surface type.
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
    returns: Constructed one runtime-schema DataFrame surface type.
    """
    return astx.DataFrameType()


def series_type(element_type: astx.DataType) -> astx.SeriesType:
    """
    title: Build one Series surface type.
    parameters:
      element_type: Type of each element.
    returns: Constructed one Series surface type.
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
      data_type: Declared data type.
    returns: Constructed one static DataFrame binding from one declared type.
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
      node: Syntax node to process.
      binding: Resolved binding for the operation.
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
      expr: Expression to process.
      target_type: Destination type for the conversion.
      context: Context for the operation.
    returns: 'Result of this operation: coerce one parsed expression into
      one declared DataFrame type.'
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
      binding: Resolved binding for the operation.
      column_name: Name of column.
    returns: The type of one DataFrame column.
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
      literal: Literal.
      schema: Declared data schema.
    returns: Literal columns ordered by schema.
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
