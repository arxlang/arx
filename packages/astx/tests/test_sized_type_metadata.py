"""
title: Tests for optional sized type metadata.
"""

from __future__ import annotations

import pytest

import astx

LIST_SIZE = 4
SERIES_SIZE = 100
DATAFRAME_ROW_COUNT = 100
INFERRED_ROW_COUNT = 2


def test_list_type_optional_size_metadata() -> None:
    """
    title: ListType stores optional static sizes.
    """
    unconstrained = astx.ListType([astx.Int32()])
    sized = astx.ListType([astx.Int32()], size=LIST_SIZE)

    assert unconstrained.size is None
    assert sized.size == LIST_SIZE
    assert str(unconstrained) == "ListType[Int32]"
    assert str(sized) == "ListType[Int32, 4]"
    with pytest.raises(ValueError, match="non-negative"):
        astx.ListType([astx.Int32()], size=-1)


def test_tensor_type_optional_shape_metadata() -> None:
    """
    title: TensorType stores optional static shapes.
    """
    unconstrained = astx.TensorType(astx.Float64())
    shaped = astx.TensorType(astx.Float64(), shape=(2, 3))

    assert unconstrained.shape is None
    assert shaped.shape == (2, 3)
    assert str(unconstrained) == "TensorType[Float64]"
    assert str(shaped) == "TensorType[Float64, 2, 3]"
    with pytest.raises(ValueError, match="non-negative"):
        astx.TensorType(astx.Float64(), shape=(2, -1))


def test_tensor_literal_and_view_preserve_shape_metadata() -> None:
    """
    title: Tensor-producing nodes preserve static shapes on their types.
    """
    literal = astx.TensorLiteral(
        [
            astx.LiteralFloat64(1.0),
            astx.LiteralFloat64(2.0),
            astx.LiteralFloat64(3.0),
            astx.LiteralFloat64(4.0),
            astx.LiteralFloat64(5.0),
            astx.LiteralFloat64(6.0),
        ],
        element_type=astx.Float64(),
        shape=(2, 3),
    )
    view = astx.TensorView(literal, shape=(3, 2))

    assert literal.type_.shape == (2, 3)
    assert view.type_.shape == (3, 2)


def test_series_type_optional_size_metadata() -> None:
    """
    title: SeriesType stores optional static sizes.
    """
    unconstrained = astx.SeriesType(astx.Int32())
    sized = astx.SeriesType(astx.Int32(), size=SERIES_SIZE)

    assert unconstrained.size is None
    assert sized.size == SERIES_SIZE
    assert str(unconstrained) == "SeriesType[Int32]"
    assert str(sized) == "SeriesType[Int32, 100]"
    with pytest.raises(ValueError, match="non-negative"):
        astx.SeriesType(astx.Int32(), size=-1)


def test_dataframe_type_optional_row_count_metadata() -> None:
    """
    title: DataFrameType stores optional static row counts.
    """
    columns = (astx.DataFrameColumn("age", astx.Int32()),)
    unconstrained = astx.DataFrameType(columns)
    sized = astx.DataFrameType(columns, row_count=DATAFRAME_ROW_COUNT)

    assert unconstrained.row_count is None
    assert sized.row_count == DATAFRAME_ROW_COUNT
    assert str(unconstrained) == "DataFrameType[age: Int32]"
    assert str(sized) == "DataFrameType[age: Int32, 100]"
    with pytest.raises(ValueError, match="non-negative"):
        astx.DataFrameType(columns, row_count=-1)


def test_dataframe_literal_infers_unconstrained_row_count() -> None:
    """
    title: DataFrameLiteral infers row counts when no explicit type is given.
    """
    literal = astx.DataFrameLiteral(
        (
            astx.DataFrameLiteralColumn(
                "age",
                (astx.LiteralInt32(1), astx.LiteralInt32(2)),
            ),
        )
    )
    explicit_type = astx.DataFrameType(
        (astx.DataFrameColumn("age", astx.Int32()),),
        row_count=DATAFRAME_ROW_COUNT,
    )
    explicit_literal = astx.DataFrameLiteral(
        literal.columns,
        type_=explicit_type,
    )

    assert literal.type_.row_count == INFERRED_ROW_COUNT
    assert explicit_literal.type_.row_count == DATAFRAME_ROW_COUNT
