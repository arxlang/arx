"""
title: Conservative validity proofs for direct local scalar predicates.
"""

from __future__ import annotations

import astx

from public import private, public

from irx.analysis.resolved_nodes import SemanticInfo
from irx.typecheck import typechecked


@public
@typechecked
def nullable_branch_symbols(condition: astx.AST, truth: bool) -> set[str]:
    """
    title: Resolve guaranteed validity facts for pure compound conditions.
    parameters:
      condition:
        type: astx.AST
      truth:
        type: bool
    returns:
      type: set[str]
    """
    if not proof_safe(condition):
        return set()
    if isinstance(condition, astx.BinaryOp):
        conjunction = condition.op_code in {"and", "&&"}
        if not conjunction and condition.op_code not in {"or", "||"}:
            return set()
        left = nullable_branch_symbols(condition.lhs, truth)
        right = nullable_branch_symbols(condition.rhs, truth)
        # Conjunction success (disjunction failure) traverses both sides.
        # The opposite outcome can exit on either side: retain common facts.
        return left | right if truth == conjunction else left & right
    if isinstance(condition, astx.UnaryOp) and condition.op_code == "!":
        return nullable_branch_symbols(condition.operand, not truth)
    if not isinstance(condition, astx.NullableQuery) or not isinstance(
        condition.operand, astx.Identifier
    ):
        return set()
    proves_valid = (
        condition.operation is astx.NullableOperation.IS_VALID and truth
    ) or (condition.operation is astx.NullableOperation.IS_NULL and not truth)
    info = getattr(condition.operand, "semantic", None)
    if (
        not proves_valid
        or not isinstance(info, SemanticInfo)
        or info.resolved_symbol is None
        or info.resolved_symbol.kind not in {"variable", "argument"}
    ):
        return set()
    return {info.resolved_symbol.symbol_id}


@private
@typechecked
def proof_safe(node: astx.AST) -> bool:
    """
    title: Exclude mutations and opaque effects from compound validity proofs.
    parameters:
      node:
        type: astx.AST
    returns:
      type: bool
    """
    if isinstance(node, (astx.Identifier, astx.Literal)):
        return True
    if isinstance(node, astx.NullableQuery):
        return isinstance(node.operand, astx.Identifier)
    if isinstance(node, astx.UnaryOp):
        return node.op_code in {"!", "+", "-"} and proof_safe(node.operand)
    if isinstance(node, astx.BinaryOp):
        return (
            node.op_code
            in {
                "and",
                "&&",
                "or",
                "||",
                "==",
                "!=",
                "<",
                "<=",
                ">",
                ">=",
                "+",
                "-",
                "*",
                "/",
                "%",
                "&",
                "|",
                "^",
            }
            and proof_safe(node.lhs)
            and proof_safe(node.rhs)
        )
    return False


@public
@typechecked
def nullable_branch_symbol(condition: astx.AST, truth: bool) -> str | None:
    """
    title: Preserve the single-symbol query for existing semantic consumers.
    parameters:
      condition:
        type: astx.AST
      truth:
        type: bool
    returns:
      type: str | None
    """
    facts = nullable_branch_symbols(condition, truth)
    return next(iter(facts)) if len(facts) == 1 else None
