"""
title: Canonical legacy column storage and optional owner assignment.
"""

import astx
import pytest

from irx.analysis.types import is_assignable, same_type


@pytest.mark.parametrize("optional_owner", [False, True])
def test_series_element_nullability_is_canonical(optional_owner: bool) -> None:
    """
    title: Separate nullable column elements from a nullable Series owner.
    parameters:
      optional_owner:
        type: bool
    """
    annotated: astx.DataType = astx.SeriesType(
        astx.UnionType((astx.Int32(), astx.NoneType()))
    )
    modeled: astx.DataType = astx.SeriesType(astx.Int32(), nullable=True)
    required: astx.DataType = astx.SeriesType(astx.Int32())
    if optional_owner:
        annotated = astx.NullableType(annotated)
        modeled = astx.NullableType(modeled)
        required = astx.NullableType(required)
    assert same_type(annotated, modeled)
    assert is_assignable(annotated, modeled)
    assert is_assignable(modeled, annotated)
    assert not same_type(required, modeled)
    assert not is_assignable(required, annotated)
    assert not is_assignable(annotated, required)


def test_optional_dataframe_preserves_schema_checks() -> None:
    """
    title: Optional runtime schemas cannot acquire static column guarantees.
    """
    static = astx.NullableType(
        astx.DataFrameType((astx.DataFrameColumn("id", astx.Int32()),))
    )
    dynamic = astx.NullableType(astx.DataFrameType())
    assert is_assignable(dynamic, static)
    assert not is_assignable(static, dynamic)
