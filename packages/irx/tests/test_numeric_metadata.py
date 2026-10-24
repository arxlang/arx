"""
title: Numeric lowering consumes analyzed operand plans without reinference.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import astx
import pytest

from irx.analysis import SemanticInfo, analyze
from irx.analysis.normalization import normalize_flags, normalize_operator
from irx.analysis.resolved_nodes import ImplicitConversion, SemanticFlags
from irx.builder import Builder, Visitor
from irx.diagnostics import LoweringError
from llvmlite import binding as llvm
from llvmlite import ir
from public import private


@private
def numeric_visitor() -> Visitor:
    """
    title: Create a live instruction block for an already-analyzed expression.
    returns:
      type: Visitor
    """
    visitor = Builder().translator
    function = ir.Function(
        visitor._llvm.module, ir.FunctionType(ir.VoidType(), []), "probe"
    )
    visitor._llvm.ir_builder = ir.IRBuilder(
        function.append_basic_block("entry")
    )
    return visitor


@pytest.mark.parametrize("operator", ["+", "<"])
def test_operand_conversions_are_recorded(operator: str) -> None:
    """
    title: Comparison result types do not erase the arithmetic operand domain.
    parameters:
      operator:
        type: str
    """
    expression = astx.BinaryOp(
        operator, astx.LiteralInt8(1), astx.LiteralInt16(2)
    )
    analyze(expression)
    semantic = cast(SemanticInfo, getattr(expression, "semantic"))
    plan = semantic.resolved_operator
    assert plan is not None
    assert isinstance(plan.computation_type, astx.Int16)
    assert isinstance(
        plan.result_type, astx.Boolean if operator == "<" else astx.Int16
    )
    assert plan.lhs_conversion is not None
    assert plan.rhs_conversion is not None
    assert isinstance(plan.lhs_conversion.source_type, astx.Int8)
    assert isinstance(plan.lhs_conversion.target_type, astx.Int16)
    assert plan.lhs_conversion.numeric is not None
    assert plan.lhs_conversion.numeric.implicit
    assert isinstance(plan.rhs_conversion.source_type, astx.Int16)
    assert isinstance(plan.rhs_conversion.target_type, astx.Int16)


def test_lowering_obeys_resolved_conversions_and_signedness() -> None:
    """
    title: Lowering does not choose a fresh common type from operand AST nodes.
    """
    expression = astx.BinaryOp("<", astx.LiteralInt8(-1), astx.LiteralUInt8(1))
    analyze(expression)
    semantic = cast(SemanticInfo, getattr(expression, "semantic"))
    plan = semantic.resolved_operator
    assert plan is not None
    # Supply a wider valid plan than the natural i16 computation domain.
    # Lowering must not replace the analyzed plan with its own promotion.
    semantic.resolved_operator = replace(
        plan,
        computation_type=astx.Int64(),
        lhs_conversion=ImplicitConversion(astx.Int8(), astx.Int64()),
        rhs_conversion=ImplicitConversion(astx.UInt8(), astx.Int64()),
        flags=SemanticFlags(unsigned=False),
    )
    visitor = numeric_visitor()
    visitor.visit(expression)
    assert len(visitor.result_stack) == 1
    visitor.result_stack.pop()
    visitor._llvm.ir_builder.ret_void()
    text = str(visitor._llvm.module)
    llvm.parse_assembly(text).verify()
    assert "sext i8 -1 to i64" in text
    assert "zext i8 1 to i64" in text
    assert "icmp slt i64" in text


def test_union_comparison_plan_describes_numeric_storage() -> None:
    """
    title: >-
      Comparison conversion sources describe untagged numeric union storage.
    """
    lhs = astx.UnionType([astx.UInt8(), astx.UInt16()])
    rhs = astx.UInt32()
    expression = astx.BinaryOp(
        "<", astx.LiteralUInt8(1), astx.LiteralUInt32(2)
    )
    flags = normalize_flags(expression, lhs_type=lhs, rhs_type=rhs)
    plan = normalize_operator(
        "<",
        result_type=astx.Boolean(),
        lhs_type=lhs,
        rhs_type=rhs,
        flags=flags,
    )
    assert plan.lhs_type is lhs
    assert isinstance(plan.computation_type, astx.UInt32)
    assert plan.lhs_conversion is not None
    assert isinstance(plan.lhs_conversion.source_type, astx.UInt16)
    assert isinstance(plan.lhs_conversion.target_type, astx.UInt32)
    assert plan.flags.unsigned


@pytest.mark.parametrize(
    "field",
    [
        "resolved_operator",
        "computation_type",
        "lhs_conversion",
        "rhs_conversion",
        "lhs_conversion.source_type",
        "lhs_conversion.target_type",
        "rhs_conversion.source_type",
        "rhs_conversion.target_type",
    ],
)
def test_missing_numeric_plans_fail_closed(field: str) -> None:
    """
    title: Missing plans cause a lowering diagnostic, never LLVM type guessing.
    parameters:
      field:
        type: str
    """
    expression = astx.BinaryOp("+", astx.LiteralInt32(1), astx.LiteralInt32(2))
    analyze(expression)
    semantic = cast(SemanticInfo, getattr(expression, "semantic"))
    plan = semantic.resolved_operator
    assert plan is not None
    semantic.resolved_operator = {
        "resolved_operator": None,
        "computation_type": replace(plan, computation_type=None),
        "lhs_conversion": replace(plan, lhs_conversion=None),
        "rhs_conversion": replace(plan, rhs_conversion=None),
        "lhs_conversion.source_type": replace(
            plan, lhs_conversion=ImplicitConversion(None, astx.Int32())
        ),
        "lhs_conversion.target_type": replace(
            plan, lhs_conversion=ImplicitConversion(astx.Int32(), None)
        ),
        "rhs_conversion.source_type": replace(
            plan, rhs_conversion=ImplicitConversion(None, astx.Int32())
        ),
        "rhs_conversion.target_type": replace(
            plan, rhs_conversion=ImplicitConversion(astx.Int32(), None)
        ),
    }[field]
    visitor = numeric_visitor()
    with pytest.raises(LoweringError, match=f"missing {field} metadata"):
        visitor.visit(expression)


def test_unanalyzed_numeric_operation_fails_closed() -> None:
    """
    title: >-
      The source-language numeric visitor no longer provides a raw fallback.
    """
    visitor = numeric_visitor()
    expression = astx.BinaryOp("+", astx.LiteralInt32(1), astx.LiteralInt32(2))
    with pytest.raises(LoweringError, match="missing semantic metadata"):
        visitor.visit(expression)


def test_boolean_equality_keeps_identity_operand_conversions() -> None:
    """
    title: Boolean comparisons remain valid without numeric promotion.
    """
    expression = astx.BinaryOp(
        "==", astx.LiteralBoolean(True), astx.LiteralBoolean(False)
    )
    analyze(expression)
    visitor = numeric_visitor()
    visitor.visit(expression)
    assert len(visitor.result_stack) == 1
    visitor.result_stack.pop()
    visitor._llvm.ir_builder.ret_void()
    llvm.parse_assembly(str(visitor._llvm.module)).verify()


def test_numeric_cast_requires_conversion_plan() -> None:
    """
    title: >-
      Missing explicit numeric conversion plans cannot reach unchecked casts.
    """
    expression = astx.Cast(astx.LiteralInt32(7), astx.Int8())
    analyze(expression)
    semantic = cast(SemanticInfo, getattr(expression, "semantic"))
    semantic.numeric_conversion = None
    with pytest.raises(LoweringError, match="numeric cast is missing"):
        numeric_visitor().visit(expression)


@pytest.mark.parametrize(
    "value", [astx.LiteralInteger(1), astx.LiteralFloat("1.25")]
)
def test_contextual_literal_lowering_requires_resolved_value(
    value: astx.Literal,
) -> None:
    """
    title: Lowering must not reconstruct an exact literal's converted value.
    parameters:
      value:
        type: astx.Literal
    """
    analyze(value)
    semantic = cast(SemanticInfo, getattr(value, "semantic"))
    semantic.numeric_constant = None
    visitor = numeric_visitor()
    with pytest.raises(LoweringError, match="missing numeric_constant"):
        visitor.visit(value)


def test_contextual_literal_lowering_uses_the_semantic_constant() -> None:
    """
    title: >-
      The backend consumes the resolved value rather than the original decimal.
    """
    value = astx.LiteralFloat("1.25")
    analyze(value)
    semantic = cast(SemanticInfo, getattr(value, "semantic"))
    expected = 1.5
    semantic.numeric_constant = expected
    visitor = numeric_visitor()
    visitor.visit(value)
    (constant,) = visitor.result_stack
    assert isinstance(constant, ir.Constant)
    assert constant.constant == expected
