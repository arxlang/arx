"""
title: Exact static column descriptors and nullable type compatibility.
"""

import astx
import pyarrow as pa
import pytest

from irx.analysis.types import clone_type, is_assignable, same_type
from irx.builtins.collections.column_types import (
    column_arrow_type,
    dataframe_schema_ipc,
)


@pytest.mark.parametrize(
    "type_,expected",
    [
        (astx.ColumnType("decimal128", (12, -2)), pa.decimal128(12, -2)),
        (astx.ColumnType("decimal256", (60, 4)), pa.decimal256(60, 4)),
        (
            astx.ColumnType("timestamp", ("ns", "UTC")),
            pa.timestamp("ns", "UTC"),
        ),
        (astx.ColumnType("time", ("ms",)), pa.time32("ms")),
        (astx.ColumnType("time", ("ns",)), pa.time64("ns")),
        (astx.ColumnType("binary", (4,)), pa.binary(4)),
        (astx.ColumnType("large_binary"), pa.large_binary()),
        (astx.ColumnType("large_string"), pa.large_string()),
        (
            astx.ColumnType("arrow_list", (astx.NullableType(astx.Int32()),)),
            pa.list_(pa.int32()),
        ),
        (
            astx.ColumnType("large_list", (astx.Int32(),)),
            pa.large_list(pa.field("item", pa.int32(), nullable=False)),
        ),
        (
            astx.ColumnType(
                "fixed_list", (astx.NullableType(astx.Int32()), 2)
            ),
            pa.list_(pa.int32(), 2),
        ),
        (
            astx.ColumnType("dictionary", (astx.Int8(), astx.String())),
            pa.dictionary(pa.int8(), pa.string()),
        ),
        (
            astx.ColumnType(
                "arrow_map", (astx.String(), astx.NullableType(astx.Int64()))
            ),
            pa.map_(pa.string(), pa.int64()),
        ),
        (
            astx.ColumnType(
                "arrow_struct", ("x", astx.NullableType(astx.Int32()))
            ),
            pa.struct([pa.field("x", pa.int32())]),
        ),
    ],
)
def test_column_types(type_: astx.ColumnType, expected: pa.DataType) -> None:
    """
    title: Resolve every parameter and nested nullable field exactly.
    parameters:
      type_:
        type: astx.ColumnType
      expected:
        type: pa.DataType
    """
    assert column_arrow_type(type_).equals(expected)
    cloned = clone_type(type_)
    assert cloned is not type_ and same_type(type_, cloned)
    schema = astx.DataFrameType([astx.DataFrameColumn("x", type_, True)])
    decoded = pa.ipc.read_schema(pa.BufferReader(dataframe_schema_ipc(schema)))
    assert decoded.equals(pa.schema([pa.field("x", expected)]))


@pytest.mark.parametrize(
    "type_",
    [
        astx.ColumnType("unknown"),
        astx.ColumnType("decimal128", (39, 0)),
        astx.ColumnType("decimal256", (77, 0)),
        astx.ColumnType("decimal128", (12, "3")),
        astx.ColumnType("timestamp", ("hours",)),
        astx.ColumnType("timestamp", ("ns", "")),
        astx.ColumnType("time", ("us", "UTC")),
        astx.ColumnType("fixed_list", (astx.Int32(), 0)),
        astx.ColumnType("arrow_list", (astx.Int32(), 2)),
        astx.ColumnType("dictionary", (astx.Float32(), astx.String())),
        astx.ColumnType(
            "arrow_struct", ("x", astx.Int32(), "x", astx.Int64())
        ),
        astx.ColumnType("binary", (-1,)),
        astx.ColumnType("large_string", (1,)),
        astx.ColumnType("decimal128", (2**40, 0)),
        astx.ColumnType("binary", (2**40,)),
        astx.ColumnType("fixed_list", (astx.Int32(), 2**40)),
        astx.ColumnType(
            "arrow_map", (astx.NullableType(astx.Int32()), astx.String())
        ),
    ],
)
def test_invalid_column_types(type_: astx.ColumnType) -> None:
    """
    title: Reject unsupported descriptors without a backend fallback.
    parameters:
      type_:
        type: astx.ColumnType
    """
    with pytest.raises((ValueError, TypeError)):
        column_arrow_type(type_)


def test_nullable_type_compatibility() -> None:
    """
    title: Never erase validity or confuse parameterized storage types.
    """
    optional = astx.NullableType(astx.Int32())
    assert is_assignable(optional, astx.Int32())
    assert not is_assignable(astx.Int32(), optional)
    assert not same_type(optional, astx.NullableType(astx.Float32()))
    assert same_type(optional, clone_type(optional))
    assert not same_type(
        astx.ColumnType("decimal128", (12, 3)),
        astx.ColumnType("decimal128", (12, 2)),
    )
