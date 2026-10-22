"""
title: >-
  Validate constant rich DataFrame cells and serialize their Arrow storage.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

import astx
import pyarrow as pa

from public import private

from irx.analysis.validation import (
    validate_literal_datetime,
    validate_literal_time,
    validate_literal_timestamp,
)
from irx.builtins.collections.column_types import dataframe_schema_ipc
from irx.typecheck import typechecked

PAIR_SIZE = 2


@private
@typechecked
def literal_cell(node: astx.AST, field: pa.Field, path: str) -> object:
    """
    title: Interpret a literal with exact storage parameters and nullability.
    parameters:
      node:
        type: astx.AST
      field:
        type: pa.Field
      path:
        type: str
    returns:
      type: object
    """
    if isinstance(node, astx.LiteralNone):
        if not field.nullable:
            raise ValueError(f"{path}: none requires a nullable field")
        return None
    type_ = field.type
    if pa.types.is_dictionary(type_):
        return literal_cell(node, field.with_type(type_.value_type), path)
    if isinstance(node, (astx.LiteralList, astx.LiteralTuple)):
        elements = node.elements
        if pa.types.is_struct(type_):
            if len(elements) != type_.num_fields:
                raise ValueError(
                    f"{path}: struct literal must match field count"
                )
            return {
                child.name: literal_cell(value, child, f"{path}.{child.name}")
                for child, value in zip(type_, elements)
            }
        if pa.types.is_map(type_):
            pairs: list[tuple[object, object]] = []
            for element in elements:
                if (
                    not isinstance(
                        element, (astx.LiteralList, astx.LiteralTuple)
                    )
                    or len(element.elements) != PAIR_SIZE
                ):
                    raise ValueError(
                        f"{path}: map entries require [key, value] pairs"
                    )
                key, item = element.elements
                pairs.append(
                    (
                        literal_cell(key, type_.key_field, path + ".key"),
                        literal_cell(item, type_.item_field, path + ".value"),
                    )
                )
            return pairs
        if (
            pa.types.is_list(type_)
            or pa.types.is_large_list(type_)
            or pa.types.is_fixed_size_list(type_)
        ):
            if (
                pa.types.is_fixed_size_list(type_)
                and len(elements) != type_.list_size
            ):
                raise ValueError(
                    f"{path}: fixed_list literal has incorrect length"
                )
            return [
                literal_cell(value, type_.value_field, path + "[]")
                for value in elements
            ]
        raise ValueError(f"{path}: nested literal does not match {type_}")
    value = getattr(node, "value", None)
    if pa.types.is_decimal(type_):
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise ValueError(
                f"{path}: decimal literals require exact strings or integers"
            )
        try:
            return Decimal(value)
        except InvalidOperation as error:
            raise ValueError(f"{path}: invalid decimal literal") from error
    if (
        pa.types.is_binary(type_)
        or pa.types.is_large_binary(type_)
        or pa.types.is_fixed_size_binary(type_)
    ):
        if not isinstance(value, str):
            raise ValueError(f"{path}: binary literals require UTF-8 strings")
        return value.encode("utf-8")
    if pa.types.is_temporal(type_):
        if isinstance(node, astx.LiteralDate) and pa.types.is_date32(type_):
            if (
                len(node.value) != len("YYYY-MM-DD")
                or node.value[4::3] != "--"
            ):
                raise ValueError(f"{path}: date literals require YYYY-MM-DD")
            return date.fromisoformat(node.value)
        if isinstance(node, astx.LiteralTime) and pa.types.is_time(type_):
            return validate_literal_time(node.value)
        if pa.types.is_timestamp(type_) and type_.tz is None:
            if isinstance(node, astx.LiteralTimestamp):
                return validate_literal_timestamp(node.value)
            if isinstance(node, astx.LiteralDateTime):
                return validate_literal_datetime(node.value)
        if type(value) is not int:
            raise ValueError(
                f"{path}: parameterized temporal literals require "
                "integer storage units"
            )
        return value
    if pa.types.is_boolean(type_):
        if type(value) is not bool:
            raise ValueError(f"{path}: bool literal required")
    elif pa.types.is_integer(type_):
        if type(value) is not int:
            raise ValueError(f"{path}: integer literal required")
    elif pa.types.is_floating(type_):
        if type(value) not in (int, float):
            raise ValueError(f"{path}: numeric literal required")
    elif pa.types.is_string(type_) or pa.types.is_large_string(type_):
        if not isinstance(value, str):
            raise ValueError(f"{path}: string literal required")
    else:
        raise ValueError(f"{path}: unsupported literal storage {type_}")
    return value


@private
@typechecked
def dataframe_literal_ipc(node: astx.DataFrameLiteral) -> bytes:
    """
    title: >-
      Produce one schema-bearing batch after validating every reachable cell.
    parameters:
      node:
        type: astx.DataFrameLiteral
    returns:
      type: bytes
    """
    schema = pa.ipc.read_schema(
        pa.BufferReader(dataframe_schema_ipc(node.type_))
    )
    columns = {column.name: column.values for column in node.columns}
    if len(columns) != len(node.columns) or set(columns) != set(schema.names):
        raise ValueError(
            "DataFrame literal columns must exactly match its schema"
        )
    if len({len(values) for values in columns.values()}) > 1:
        raise ValueError("DataFrame literal columns must have the same length")
    arrays = []
    for field in schema:
        values = [
            literal_cell(value, field, field.name)
            for value in columns[field.name]
        ]
        try:
            if pa.types.is_dictionary(field.type):
                array = (
                    pa.array(values, type=field.type.value_type)
                    .dictionary_encode()
                    .cast(field.type, safe=True)
                )
            else:
                array = pa.array(values, type=field.type, safe=True)
        except (pa.ArrowException, ValueError, OverflowError) as error:
            raise ValueError(
                f"DataFrame column '{field.name}': {error}"
            ) from error
        arrays.append(array)
    batch = pa.RecordBatch.from_arrays(arrays, schema=schema)
    batch.validate(full=True)
    sink = pa.BufferOutputStream()
    with pa.ipc.new_stream(sink, schema) as writer:
        writer.write_batch(batch)
    return cast(bytes, sink.getvalue().to_pybytes())
