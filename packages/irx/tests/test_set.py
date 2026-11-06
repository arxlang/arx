"""
title: Tests for LiteralSet lowering using project conventions.
"""

from __future__ import annotations

import re

from typing import cast

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.builder import Builder as LLVMBuilder
from irx.builder import Visitor as LLVMVisitor
from irx.builder.base import Builder
from llvmlite import ir

EXPECTED_SET_LENGTH = 2
EXPECTED_PROMOTED_WIDTH = 32
EXPECTED_WIDEST_SET_OP_WIDTH = 64
HAS_LITERAL_LIST = hasattr(astx, "LiteralList")


def _array_i32_values(const: ir.Constant) -> list[int]:
    """
    title: Extract i32-like values from array constant via regex (suite style).
    parameters:
      const:
        type: ir.Constant
    returns:
      type: list[int]
    """
    return [int(v) for v in re.findall(r"i\d+\s+(-?\d+)", str(const))]


def _make_visitor_in_function(
    builder_class: type[Builder],
) -> LLVMVisitor:
    """
    title: Return a visitor whose ir_builder is inside a live basic block.
    parameters:
      builder_class:
        type: type[Builder]
    returns:
      type: LLVMVisitor
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    fn_ty = ir.FunctionType(visitor._llvm.VOID_TYPE, [])
    fn = ir.Function(visitor._llvm.module, fn_ty, name="_test_dummy")
    bb = fn.append_basic_block("entry")
    visitor._llvm.ir_builder = ir.IRBuilder(bb)
    return visitor


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_literal_set_empty(builder_class: type[Builder]) -> None:
    """
    title: Empty set lowers to constant [0 x i32].
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    visitor.visit(analyze(astx.LiteralSet(elements=set())))
    const = visitor.function_state.result_stack.pop()

    assert isinstance(const, ir.Constant)
    assert isinstance(const.type, ir.ArrayType)
    assert const.type.count == 0
    assert const.type.element == ir.IntType(32)


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_literal_set_homogeneous_ints(builder_class: type[Builder]) -> None:
    """
    title: Homogeneous integer constants lower to constant array [N x i32].
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    visitor.visit(
        analyze(
            astx.LiteralSet(
                elements={
                    astx.LiteralInt32(1),
                    astx.LiteralInt32(2),
                    astx.LiteralInt32(3),
                }
            )
        )
    )
    const = visitor.function_state.result_stack.pop()

    assert isinstance(const, ir.Constant)
    assert isinstance(const.type, ir.ArrayType)
    assert const.type.count == 3  # noqa: PLR2004
    assert const.type.element == ir.IntType(32)
    # Values should be deterministically sorted
    vals = _array_i32_values(const)
    assert vals == [1, 2, 3]


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_literal_set_mixed_int_widths(builder_class: type[Builder]) -> None:
    """
    title: Mixed-width integer constants lower correctly.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    visitor.visit(
        analyze(
            astx.LiteralSet(
                elements={astx.LiteralInt16(1), astx.LiteralInt32(2)}
            )
        )
    )

    const = visitor.function_state.result_stack.pop()

    assert isinstance(const, ir.Constant)
    assert isinstance(const.type, ir.ArrayType)
    assert const.type.count == EXPECTED_SET_LENGTH

    # Check promoted type is i32 (widest type)
    assert isinstance(const.type.element, ir.IntType)
    assert const.type.element.width == EXPECTED_PROMOTED_WIDTH

    # Check values are correct after promotion
    vals = _array_i32_values(const)
    assert vals == [1, 2]


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_literal_set_non_integer_unsupported(
    builder_class: type[Builder],
) -> None:
    """
    title: Non-integer homogeneous sets are not yet supported.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    with pytest.raises(SemanticError, match="integer constants"):
        visitor.visit(
            analyze(
                astx.LiteralSet(
                    elements={
                        astx.LiteralFloat32(1.0),
                        astx.LiteralFloat32(2.0),
                    }
                )
            )
        )


def _make_set(*vals: int) -> astx.LiteralSet:
    """
    title: Make set.
    parameters:
      vals:
        type: int
        variadic: positional
    returns:
      type: astx.LiteralSet
    """
    return astx.LiteralSet(elements={astx.LiteralInt32(v) for v in vals})


def _set_values(const: ir.Value) -> list[int]:
    """
    title: Set values.
    parameters:
      const:
        type: ir.Value
    returns:
      type: list[int]
    """
    return _array_i32_values(const)


def emit_raw_set_operation(visitor: LLVMVisitor, node: astx.BinaryOp) -> None:
    """
    title: Exercise raw constant-set adapters without claiming source support.
    summary: >-
      Literal operands still require analyzed storage. Binary composition calls
      the explicit representation adapter; source subtraction has a separate
      semantic contract and is not accepted merely because this adapter exists.
    parameters:
      visitor:
        type: LLVMVisitor
      node:
        type: astx.BinaryOp
    """
    values: list[ir.Value] = []
    for operand in (node.lhs, node.rhs):
        if isinstance(operand, astx.BinaryOp):
            emit_raw_set_operation(visitor, operand)
        else:
            visitor.visit(analyze(operand))
        value = visitor.function_state.result_stack.pop()
        assert value is not None
        values.append(value)
    assert visitor.collection.try_set_binary_op(
        values[0], values[1], node.op_code
    )


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_set_union(builder_class: type[Builder]) -> None:
    """
    title: Raw constant-set union preserves all distinct members.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.BinaryOp(op_code="|", lhs=_make_set(1, 2), rhs=_make_set(2, 3))
    emit_raw_set_operation(visitor, expr)
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    assert isinstance(result.type, ir.ArrayType)
    assert _set_values(result) == [1, 2, 3]


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_set_intersection(builder_class: type[Builder]) -> None:
    """
    title: Raw constant-set intersection preserves common members.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.BinaryOp(
        op_code="&", lhs=_make_set(1, 2, 3), rhs=_make_set(2, 3, 4)
    )
    emit_raw_set_operation(visitor, expr)
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    assert _set_values(result) == [2, 3]


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_set_difference(builder_class: type[Builder]) -> None:
    """
    title: Raw constant-set difference removes right-side members.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.BinaryOp(
        op_code="-", lhs=_make_set(1, 2, 3), rhs=_make_set(2, 3)
    )
    emit_raw_set_operation(visitor, expr)
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    assert _set_values(result) == [1]


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_set_symmetric_difference(builder_class: type[Builder]) -> None:
    """
    title: Raw symmetric difference excludes common members.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.BinaryOp(op_code="^", lhs=_make_set(1, 2), rhs=_make_set(2, 3))
    emit_raw_set_operation(visitor, expr)
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    assert _set_values(result) == [1, 3]


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_set_disjoint_intersection_is_empty(
    builder_class: type[Builder],
) -> None:
    """
    title: Intersection of disjoint sets is an empty constant array.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.BinaryOp(op_code="&", lhs=_make_set(1, 2), rhs=_make_set(3, 4))
    emit_raw_set_operation(visitor, expr)
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    assert isinstance(result.type, ir.ArrayType)
    assert result.type.count == 0


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_set_union_mixed_widths_in_function(
    builder_class: type[Builder],
) -> None:
    """
    title: Mixed-width set union stays constant in function context.
    parameters:
      builder_class:
        type: type[Builder]
    """
    visitor = _make_visitor_in_function(builder_class)

    expr = astx.BinaryOp(
        op_code="|",
        lhs=astx.LiteralSet(
            elements={astx.LiteralInt16(1), astx.LiteralInt32(2)}
        ),
        rhs=astx.LiteralSet(
            elements={astx.LiteralInt32(2), astx.LiteralInt64(4)}
        ),
    )
    emit_raw_set_operation(visitor, expr)
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    assert isinstance(result.type, ir.ArrayType)
    assert isinstance(result.type.element, ir.IntType)
    assert result.type.element.width == EXPECTED_WIDEST_SET_OP_WIDTH
    assert _set_values(result) == [1, 2, 4]


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_nested_set_binary_ops_preserve_set_semantics(
    builder_class: type[Builder],
) -> None:
    """
    title: Chained set binary ops keep using set semantics.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.BinaryOp(
        op_code="-",
        lhs=astx.BinaryOp(
            op_code="|",
            lhs=_make_set(1, 2),
            rhs=_make_set(2, 3),
        ),
        rhs=_make_set(1),
    )
    emit_raw_set_operation(visitor, expr)
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    assert _set_values(result) == [2, 3]


@pytest.mark.skipif(
    not HAS_LITERAL_LIST, reason="astx.LiteralList not available"
)
@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_literal_list_binary_or_does_not_use_set_semantics(
    builder_class: type[Builder],
) -> None:
    """
    title: List storage does not acquire raw set identity.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.BinaryOp(
        op_code="|",
        lhs=astx.LiteralList(
            elements=[astx.LiteralInt32(1), astx.LiteralInt32(2)]
        ),
        rhs=astx.LiteralList(
            elements=[astx.LiteralInt32(2), astx.LiteralInt32(3)]
        ),
    )

    visitor.visit(analyze(expr.lhs))
    left = visitor.function_state.result_stack.pop()
    visitor.visit(analyze(expr.rhs))
    right = visitor.function_state.result_stack.pop()
    assert not visitor.collection.try_set_binary_op(left, right, "|")
    assert not visitor.function_state.result_stack
