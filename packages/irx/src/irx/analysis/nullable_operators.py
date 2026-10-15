"""
title: Closed primitive nullable operator signatures.
"""

from __future__ import annotations

import astx

from public import public

from irx.analysis.nullability import ResolvedNullableOperator
from irx.analysis.types import (
    common_numeric_type,
    is_boolean_type,
    is_integer_type,
    is_numeric_type,
)
from irx.typecheck import typechecked


@public
@typechecked
def resolve_nullable_operator(
    op: str, lhs: astx.DataType, rhs: astx.DataType | None = None
) -> ResolvedNullableOperator | None:
    """
    title: Resolve propagation and Kleene logic without implicit null coercion.
    parameters:
      op:
        type: str
      lhs:
        type: astx.DataType
      rhs:
        type: astx.DataType | None
    returns:
      type: ResolvedNullableOperator | None
    """
    left = lhs.payload_type if isinstance(lhs, astx.NullableType) else lhs
    right = rhs.payload_type if isinstance(rhs, astx.NullableType) else rhs
    if rhs is None:
        if (op in {"+", "-"} and is_numeric_type(left)) or (
            op == "!" and is_boolean_type(left)
        ):
            return ResolvedNullableOperator(op, lhs, None, left, left)
        return None
    if op in {"and", "&&", "or", "||"}:
        if is_boolean_type(left) and is_boolean_type(right):
            return ResolvedNullableOperator(
                op, lhs, rhs, astx.Boolean(), astx.Boolean(), kleene=True
            )
        return None
    if op in {"==", "!="} and (
        is_boolean_type(left) and is_boolean_type(right)
    ):
        return ResolvedNullableOperator(
            op, lhs, rhs, astx.Boolean(), astx.Boolean()
        )
    if not (is_numeric_type(left) and is_numeric_type(right)):
        return None
    common = common_numeric_type(left, right)
    if common is None:
        return None
    if op in {"<", "<=", ">", ">=", "==", "!="}:
        return ResolvedNullableOperator(op, lhs, rhs, common, astx.Boolean())
    if op in {"+", "-", "*", "/", "%"} or (
        op in {"&", "|", "^"} and is_integer_type(common)
    ):
        return ResolvedNullableOperator(op, lhs, rhs, common, common)
    return None
