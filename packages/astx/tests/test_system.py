"""
title: Tests for system expression value modeling.
"""

import astx


def test_system_expressions_expose_concrete_value_types() -> None:
    """
    title: System expressions used by operators expose concrete value types.
    """
    value = astx.LiteralInt32(7)
    cast_expr = astx.Cast(value, astx.Float32())
    isinstance_expr = astx.IsInstanceExpr(value, astx.Int32())
    type_expr = astx.TypeOfExpr(value)

    assert isinstance(cast_expr.type_, astx.Float32)
    assert isinstance(isinstance_expr.type_, astx.Boolean)
    assert isinstance(type_expr.type_, astx.String)
    assert astx.BinaryOp("==", isinstance_expr, astx.LiteralBoolean(True))
    assert astx.BinaryOp("==", type_expr, astx.LiteralString("Int32"))
