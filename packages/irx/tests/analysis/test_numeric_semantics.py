"""
title: Tests for scalar numeric semantics.
"""

from __future__ import annotations

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.analysis.numeric_literals import numeric_constant


@pytest.mark.parametrize(
    "left,right,expected", [(-19, 5, -4), (19, -5, 4), (-19, -5, -4)]
)
def test_constant_remainder_truncates(
    left: int, right: int, expected: int
) -> None:
    """
    title: Constant remainder uses the dividend sign, not Python floor modulo.
    parameters:
      left:
        type: int
      right:
        type: int
      expected:
        type: int
    """
    expression = astx.BinaryOp(
        "%", astx.LiteralInt32(left), astx.LiteralInt32(right)
    )
    analyze(expression)
    assert numeric_constant(expression) == expected


@pytest.mark.parametrize(
    "operand",
    [
        astx.LiteralBoolean(True),
        astx.LiteralList([astx.LiteralInt32(1), astx.LiteralInt32(2)]),
        astx.TensorLiteral(
            [astx.LiteralInt32(1)], element_type=astx.Int32(), shape=(1,)
        ),
        astx.Cast(astx.LiteralInt32(1), astx.NullableType(astx.Int32())),
    ],
)
def test_remainder_requires_numeric_scalars(operand: astx.DataType) -> None:
    """
    title: Unsupported remainder domains fail before scalar LLVM lowering.
    parameters:
      operand:
        type: astx.DataType
    """
    with pytest.raises(SemanticError, match="non-nullable numeric scalars"):
        analyze(astx.BinaryOp("%", operand, astx.LiteralInt32(2)))


def _semantic_type(node: astx.AST) -> astx.DataType | None:
    """
    title: Return the resolved semantic type attached to one node.
    parameters:
      node:
        type: astx.AST
    returns:
      type: astx.DataType | None
    """
    return getattr(getattr(node, "semantic", None), "resolved_type", None)


def test_analyze_promotes_int32_and_float32_to_float64() -> None:
    """
    title: Mixed int32 and float32 arithmetic should promote to float64.
    """
    expr = astx.BinaryOp(
        "+",
        astx.LiteralInt32(1),
        astx.LiteralFloat32(2.0),
    )

    analyze(expr)

    resolved_type = _semantic_type(expr)
    assert resolved_type is not None
    assert resolved_type.__class__ is astx.Float64


def test_analyze_marks_signed_result_when_signed_operand_is_wider() -> None:
    """
    title: Wider signed integers should keep signed semantics against unsigned.
    """
    expr = astx.BinaryOp(
        "/",
        astx.LiteralInt32(9),
        astx.LiteralUInt16(2),
    )

    analyze(expr)

    semantic = getattr(expr, "semantic")
    assert semantic.resolved_type.__class__ is astx.Int32
    assert semantic.semantic_flags.unsigned is False


def test_mixed_comparison_uses_lossless_signed_domain() -> None:
    """
    title: >-
      Mixed integer comparisons use a signed domain containing both operands.
    """
    expr = astx.BinaryOp(
        ">",
        astx.LiteralInt16(-1),
        astx.LiteralUInt32(1),
    )

    analyze(expr)

    semantic = getattr(expr, "semantic")
    assert semantic.resolved_type.__class__ is astx.Boolean
    assert semantic.semantic_flags.unsigned is False


def test_analyze_widens_at_equal_width_boundary() -> None:
    """
    title: >-
      Equal-width signed and unsigned integers require a wider signed type.
    """
    expr = astx.BinaryOp(
        "+",
        astx.LiteralInt32(-1),
        astx.LiteralUInt32(1),
    )

    analyze(expr)

    semantic = getattr(expr, "semantic")
    assert semantic.resolved_type.__class__ is astx.Int64
    assert semantic.semantic_flags.unsigned is False


def test_analyze_rejects_implicit_signed_to_unsigned_assignment() -> None:
    """
    title: >-
      Implicit signed-to-unsigned assignment should require an explicit cast.
    """
    module = astx.Module()
    proto = astx.FunctionPrototype(
        "main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    )
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            name="value",
            type_=astx.UInt32(),
            value=astx.LiteralInt32(1),
        )
    )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(astx.FunctionDef(prototype=proto, body=body))

    with pytest.raises(
        SemanticError,
        match="cannot assign Int32 to 'value' of type UInt32",
    ):
        analyze(module)


def test_rejects_implicit_unsigned_to_same_width_signed_assignment() -> None:
    """
    title: Unsigned integers need a strictly wider signed target implicitly.
    """
    module = astx.Module()
    proto = astx.FunctionPrototype(
        "main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    )
    body = astx.Block()
    body.append(
        astx.VariableDeclaration(
            name="value",
            type_=astx.Int32(),
            value=astx.LiteralUInt32(1),
        )
    )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(astx.FunctionDef(prototype=proto, body=body))

    with pytest.raises(
        SemanticError,
        match="cannot assign UInt32 to 'value' of type Int32",
    ):
        analyze(module)


def test_analyze_rejects_explicit_string_to_int_cast() -> None:
    """
    title: Non-numeric explicit casts should still be rejected semantically.
    """
    expr = astx.Cast(
        value=astx.LiteralString("7"),
        target_type=astx.Int32(),
    )

    with pytest.raises(
        SemanticError,
        match="unsupported cast from String to Int32",
    ):
        analyze(expr)
