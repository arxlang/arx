"""
title: Semantic normalization helpers.
summary: >-
  Normalize raw AST operator and flag information into the structured semantic
  records used by later analysis and codegen.
"""

from __future__ import annotations

import astx

from public import private

from irx.analysis.resolved_nodes import (
    ImplicitConversion,
    ResolvedOperator,
    SemanticFlags,
)
from irx.analysis.types import (
    common_numeric_type,
    is_boolean_type,
    is_numeric_type,
    is_unsigned_type,
    union_storage_type,
)
from irx.typecheck import typechecked


@private
@typechecked
def numeric_operand_storage(
    type_: astx.DataType | None,
) -> astx.DataType | None:
    """
    title: >-
      Resolve the current scalar representation of a numeric union operand.
    summary: >-
      Numeric union comparisons already use a shared untagged storage type.
      Record that type during analysis rather than asking LLVM operand widths
      to choose the comparison domain. This does not enable union arithmetic.
    parameters:
      type_:
        type: astx.DataType | None
    returns:
      type: astx.DataType | None
    """
    if not isinstance(type_, astx.UnionType):
        return type_
    return union_storage_type(type_)


@typechecked
def normalize_flags(
    node: astx.AST,
    *,
    lhs_type: astx.DataType | None = None,
    rhs_type: astx.DataType | None = None,
) -> SemanticFlags:
    """
    title: Normalize semantic flags from the raw AST node.
    parameters:
      node:
        type: astx.AST
      lhs_type:
        type: astx.DataType | None
      rhs_type:
        type: astx.DataType | None
    returns:
      type: SemanticFlags
    """
    promoted_type = common_numeric_type(
        numeric_operand_storage(lhs_type), numeric_operand_storage(rhs_type)
    )
    unsigned = is_unsigned_type(promoted_type or lhs_type)
    return SemanticFlags(
        unsigned=unsigned,
        fast_math=bool(getattr(node, "fast_math", False)),
        fma=bool(getattr(node, "fma", False)),
        fma_rhs=getattr(node, "fma_rhs", None),
    )


@typechecked
def normalize_operator(
    op_code: str,
    *,
    result_type: astx.DataType | None,
    lhs_type: astx.DataType | None = None,
    rhs_type: astx.DataType | None = None,
    flags: SemanticFlags | None = None,
    mode: astx.NumericMode = astx.NumericMode.CHECKED,
) -> ResolvedOperator:
    """
    title: Create a normalized operator record.
    parameters:
      op_code:
        type: str
      result_type:
        type: astx.DataType | None
      lhs_type:
        type: astx.DataType | None
      rhs_type:
        type: astx.DataType | None
      flags:
        type: SemanticFlags | None
      mode:
        type: astx.NumericMode
    returns:
      type: ResolvedOperator
    """
    lhs_storage = numeric_operand_storage(lhs_type)
    rhs_storage = numeric_operand_storage(rhs_type)
    computation_type = (
        common_numeric_type(lhs_storage, rhs_storage)
        if rhs_type is not None
        else lhs_storage
        if is_numeric_type(lhs_storage)
        else None
    )
    if op_code == "=":
        computation_type = None
    elif is_boolean_type(lhs_type) and is_boolean_type(rhs_type):
        computation_type = lhs_type
    return ResolvedOperator(
        op_code=op_code,
        mode=mode,
        result_type=result_type,
        lhs_type=lhs_type,
        rhs_type=rhs_type,
        flags=flags or SemanticFlags(),
        computation_type=computation_type,
        lhs_conversion=(
            ImplicitConversion(lhs_storage, computation_type)
            if computation_type is not None and lhs_storage is not None
            else None
        ),
        rhs_conversion=(
            ImplicitConversion(rhs_storage, computation_type)
            if computation_type is not None and rhs_storage is not None
            else None
        ),
    )
