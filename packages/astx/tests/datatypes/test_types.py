"""
title: Tests for classes in types.py.
"""

from __future__ import annotations

from astx.data import Variable
from astx.types.casting import TypeCastExpr
from astx.types.numeric import Int32
from astx.viz import visualize_image


def test_typecastexpr() -> None:
    """
    title: Test TypeCastExpr.
    """
    # Expression to cast
    expr = Variable(name="x")

    # Target type for casting
    target_type = Int32()

    # Create the TypeCastExpr
    cast_expr = TypeCastExpr(expr=expr, target_type=target_type)

    assert str(cast_expr)
    assert cast_expr.get_struct()
    assert cast_expr.get_struct(simplified=True)

    visualize_image(cast_expr.get_struct())


def test_inferred_type_is_an_explicit_source_request() -> None:
    """
    title: Inference requests are distinct from wildcard and concrete types.
    """
    import pytest

    import astx

    annotation = astx.InferredType()
    assert isinstance(annotation, astx.DataType)
    assert not isinstance(annotation, astx.types.AnyType)
    assert annotation is not astx.InferredType()
    with pytest.raises(TypeError):
        astx.InferredType("invalid")  # type: ignore[call-arg]
