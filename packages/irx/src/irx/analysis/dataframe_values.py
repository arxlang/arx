"""
title: Explicit compatibility between legacy and schema-first columnar values.
"""

from __future__ import annotations

import astx

from public import public

from irx.analysis.array_values import ARRAY_VALUE_TYPES, array_storage
from irx.analysis.nullability import normalize_nullable
from irx.analysis.schema import canonical_schema
from irx.typecheck import typechecked


@public
@typechecked
def dataframe_element(
    type_: astx.DataType, nullable: bool = False
) -> tuple[astx.LogicalType, bool]:
    """
    title: Resolve one legacy column to its exact Arrow logical storage.
    parameters:
      type_:
        type: astx.DataType
      nullable:
        type: bool
    returns:
      type: tuple[astx.LogicalType, bool]
    """
    type_ = normalize_nullable(type_) or type_
    if isinstance(type_, astx.NullableType):
        nullable, type_ = True, type_.payload_type
    if isinstance(type_, astx.ScalarType):
        if type_.nullable:
            raise ValueError("use scalar[T] | none for optional column values")
        logical = type_.element_type
    elif isinstance(type_, astx.String):
        logical = astx.LogicalType(astx.LogicalKind.STRING)
    else:
        kind = next(
            (
                kind
                for kind, cls in ARRAY_VALUE_TYPES.items()
                if type(type_) is cls
            ),
            None,
        )
        if kind is None:
            raise ValueError(
                "DataFrame/Series column requires an Arrow value type"
            )
        logical = astx.LogicalType(kind)
    if array_storage(astx.ArrayType(logical, nullable=nullable)) is None:
        raise ValueError("DataFrame/Series column storage is not implemented")
    return logical, nullable


@public
@typechecked
def dataframe_schema(type_: astx.DataFrameType) -> astx.Schema | None:
    """
    title: Validate a legacy schema without inventing erased metadata.
    parameters:
      type_:
        type: astx.DataFrameType
    returns:
      type: astx.Schema | None
    """
    if type_.columns is None:
        return None
    fields: list[astx.SchemaField] = []
    for column in type_.columns:
        logical, nullable = dataframe_element(column.type_, column.nullable)
        fields.append(
            astx.SchemaField(column.name, logical, nullable=nullable)
        )
    return canonical_schema(astx.Schema(tuple(fields)))


@public
@typechecked
def same_series_elements(lhs: astx.SeriesType, rhs: astx.SeriesType) -> bool:
    """
    title: Compare column storage and validity independent of annotation form.
    parameters:
      lhs:
        type: astx.SeriesType
      rhs:
        type: astx.SeriesType
    returns:
      type: bool
    """
    if lhs.element_type is None or rhs.element_type is None:
        return True
    try:
        return dataframe_element(
            lhs.element_type, lhs.nullable
        ) == dataframe_element(rhs.element_type, rhs.nullable)
    except ValueError:
        return False


@public
@typechecked
def dataframe_literal(node: astx.DataFrameLiteral) -> astx.TabularLiteral:
    """
    title: Normalize legacy literals into typed chunk columns during analysis.
    parameters:
      node:
        type: astx.DataFrameLiteral
    returns:
      type: astx.TabularLiteral
    """
    schema = dataframe_schema(node.type_)
    if schema is None:
        raise ValueError(
            "dataframe literals require an explicit static DataFrame type"
        )
    names = [column.name for column in node.columns]
    if len(set(names)) != len(names):
        raise ValueError("duplicate dataframe column")
    if set(names) != {field.name for field in schema.fields}:
        raise ValueError(
            "dataframe literal columns disagree with declared schema"
        )
    lengths = {len(column.values) for column in node.columns}
    if len(lengths) > 1:
        raise ValueError("dataframe literal columns must have the same length")
    count = next(iter(lengths), node.type_.row_count or 0)
    if node.type_.row_count is not None and node.type_.row_count != count:
        raise ValueError(
            "dataframe literal row count disagrees with declared size"
        )
    by_name = {column.name: column for column in node.columns}
    columns: list[astx.Expr] = []
    for field in schema.fields:
        values: list[astx.Expr] = []
        for value in by_name[field.name].values:
            if not isinstance(value, astx.Expr):
                raise ValueError(
                    "dataframe elements must be value expressions"
                )
            values.append(value)
        array = astx.ArrayLiteral(
            astx.ArrayType(field.type_, nullable=field.nullable), tuple(values)
        )
        columns.append(
            astx.ArrayLiteral(
                astx.ChunkedArrayType(field.type_, nullable=field.nullable),
                (array,),
            )
        )
    return astx.TabularLiteral(
        astx.TableType(schema), (astx.LiteralInt64(count), *columns)
    )


@public
@typechecked
def legacy_adapter(
    operation: astx.TabularOperation, owner: astx.DataType
) -> tuple[str, astx.DataType, str] | None:
    """
    title: Resolve retained compatibility owners without implicit aliases.
    parameters:
      operation:
        type: astx.TabularOperation
      owner:
        type: astx.DataType
    returns:
      type: tuple[str, astx.DataType, str] | None
    """
    if operation is astx.TabularOperation.TO_DATAFRAME:
        if not isinstance(owner, astx.TableType):
            raise ValueError("to_dataframe requires a table")
        # Legacy types cannot express field/schema metadata. Retain it in the
        # runtime value and require checked projection after converting back.
        return "irx_arrow_table_retain", astx.DataFrameType(), "dataframe"
    if operation is astx.TabularOperation.TO_TABLE and isinstance(
        owner, astx.DataFrameType
    ):
        return "irx_arrow_table_retain", astx.TableType(), "dataframe"
    if operation is astx.TabularOperation.TO_SERIES:
        if not isinstance(owner, astx.ChunkedArrayType):
            raise ValueError("to_series requires a chunked_array")
        scalar = ARRAY_VALUE_TYPES.get(owner.element_type.kind)
        element = scalar() if scalar else astx.ScalarType(owner.element_type)
        return (
            "irx_arrow_chunked_array_retain",
            astx.SeriesType(element, nullable=owner.nullable),
            "dataframe",
        )
    if operation is astx.TabularOperation.TO_CHUNKED:
        if (
            not isinstance(owner, astx.SeriesType)
            or owner.element_type is None
        ):
            raise ValueError("to_chunked requires a typed Series")
        logical, nullable = dataframe_element(
            owner.element_type, owner.nullable
        )
        return (
            "irx_arrow_chunked_array_retain",
            astx.ChunkedArrayType(logical, nullable=nullable),
            "dataframe",
        )
    return None
