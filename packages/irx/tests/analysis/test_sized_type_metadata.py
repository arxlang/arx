"""
title: Tests for sized type metadata helpers.
"""

from __future__ import annotations

import astx

from irx.analysis.types import (
    clone_type,
    display_type_name,
    is_assignable,
    requires_shape_check,
    requires_size_check,
    same_type,
)

LIST_SIZE = 4
SERIES_SIZE = 100
DATAFRAME_ROW_COUNT = 100


def _dataframe_columns() -> tuple[astx.DataFrameColumn, ...]:
    """
    title: Build a small dataframe schema for metadata tests.
    returns:
      type: tuple[astx.DataFrameColumn, Ellipsis]
    """
    return (astx.DataFrameColumn("age", astx.Int32()),)


def test_clone_type_preserves_sized_metadata() -> None:
    """
    title: clone_type preserves collection size and shape metadata.
    """
    list_type = clone_type(astx.ListType([astx.Int32()], size=LIST_SIZE))
    tensor_type = clone_type(astx.TensorType(astx.Float64(), shape=(2, 3)))
    series_type = clone_type(astx.SeriesType(astx.Int32(), size=SERIES_SIZE))
    dataframe_type = clone_type(
        astx.DataFrameType(
            _dataframe_columns(),
            row_count=DATAFRAME_ROW_COUNT,
        )
    )

    assert isinstance(list_type, astx.ListType)
    assert list_type.size == LIST_SIZE
    assert isinstance(tensor_type, astx.TensorType)
    assert tensor_type.shape == (2, 3)
    assert isinstance(series_type, astx.SeriesType)
    assert series_type.size == SERIES_SIZE
    assert isinstance(dataframe_type, astx.DataFrameType)
    assert dataframe_type.row_count == DATAFRAME_ROW_COUNT


def test_display_type_name_canonicalizes_sized_metadata() -> None:
    """
    title: display_type_name omits unconstrained and renders constrained sizes.
    """
    assert display_type_name(astx.ListType([astx.Int32()])) == (
        "ListType[Int32]"
    )
    assert display_type_name(astx.TensorType(astx.Float64())) == (
        "TensorType[Float64]"
    )
    assert display_type_name(astx.SeriesType(astx.Int32())) == (
        "SeriesType[Int32]"
    )
    assert display_type_name(astx.DataFrameType(_dataframe_columns())) == (
        "DataFrameType[age: Int32]"
    )

    assert display_type_name(astx.ListType([astx.Int32()], size=4)) == (
        "ListType[Int32, 4]"
    )
    assert (
        display_type_name(astx.TensorType(astx.Float64(), shape=(2, 3)))
        == "TensorType[Float64, 2, 3]"
    )
    assert display_type_name(astx.SeriesType(astx.Int32(), size=100)) == (
        "SeriesType[Int32, 100]"
    )
    assert (
        display_type_name(
            astx.DataFrameType(_dataframe_columns(), row_count=100)
        )
        == "DataFrameType[age: Int32, 100]"
    )


def test_same_type_allows_unconstrained_tensor_shape_wildcard() -> None:
    """
    title: Tensor same_type keeps unconstrained shape wildcard behavior.
    """
    assert same_type(
        astx.TensorType(astx.Float64()),
        astx.TensorType(astx.Float64(), shape=(2, 3)),
    )
    assert not same_type(
        astx.TensorType(astx.Float64(), shape=(2, 3)),
        astx.TensorType(astx.Float64(), shape=(3, 2)),
    )


def test_tensor_assignability_checks_known_shapes() -> None:
    """
    title: Tensor assignability rejects incompatible known shapes.
    """
    assert is_assignable(
        astx.TensorType(astx.Float64(), shape=(2, 3)),
        astx.TensorType(astx.Float64(), shape=(2, 3)),
    )
    assert not is_assignable(
        astx.TensorType(astx.Float64(), shape=(2, 3)),
        astx.TensorType(astx.Float64(), shape=(3, 2)),
    )
    assert is_assignable(
        astx.TensorType(astx.Float64()),
        astx.TensorType(astx.Float64(), shape=(2, 3)),
    )
    assert is_assignable(
        astx.TensorType(astx.Float64(), shape=(2, 3)),
        astx.TensorType(astx.Float64()),
    )


def test_runtime_check_helpers_detect_unknown_metadata_narrowing() -> None:
    """
    title: Runtime-check helpers identify unknown-to-known size narrowing.
    """
    assert requires_size_check(4, None)
    assert not requires_size_check(None, 4)
    assert requires_shape_check((2, 3), None)
    assert not requires_shape_check(None, (2, 3))
