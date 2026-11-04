"""
title: Numeric lowering consumes analyzed operand plans without reinference.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import astx
import pytest

from astx.operators import OpCodeAugAssign
from irx.analysis import SemanticError, SemanticInfo, analyze
from irx.analysis.normalization import normalize_flags, normalize_operator
from irx.analysis.resolved_nodes import ImplicitConversion, SemanticFlags
from irx.builder import Builder, Visitor
from irx.diagnostics import LoweringError
from llvmlite import binding as llvm
from llvmlite import ir
from public import private

from .conftest import make_main_module


@private
def compound_module(
    operator: OpCodeAugAssign = "+=",
    target_type: astx.DataType | None = None,
    value: astx.DataType | None = None,
) -> tuple[astx.Module, astx.AugAssign]:
    """
    title: Construct a numeric declaration and compound operation for analysis.
    parameters:
      operator:
        type: OpCodeAugAssign
      target_type:
        type: astx.DataType | None
      value:
        type: astx.DataType | None
    returns:
      type: tuple[astx.Module, astx.AugAssign]
    """
    node = astx.AugAssign(
        astx.Identifier("x"),
        operator,
        value if value is not None else astx.LiteralInteger(2),
    )
    declaration = astx.VariableDeclaration(
        "x",
        target_type if target_type is not None else astx.Int32(),
        value=astx.LiteralInteger(3),
        mutability=astx.MutabilityKind.mutable,
    )
    return make_main_module(
        declaration, node, astx.FunctionReturn(astx.LiteralInt32(0))
    ), node


@pytest.mark.parametrize("operator", ["+=", "-=", "*=", "/=", "%="])
def test_compound_plans_and_value_lowering(operator: OpCodeAugAssign) -> None:
    """
    title: Direct AST compounds resolve numeric plans and yield stored values.
    parameters:
      operator:
        type: OpCodeAugAssign
    """
    module, node = compound_module(operator)
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    function.body.nodes[1:] = [astx.FunctionReturn(node)]
    text = Builder().translate(module)
    llvm.parse_assembly(text).verify()
    info = cast(SemanticInfo, node.semantic)
    plan = info.resolved_aug_assignment
    assert plan is not None
    assert plan.target.name == "x"
    assert plan.operation is info.resolved_operator
    assert plan.operation.op_code == operator[0]
    assert isinstance(plan.operation.computation_type, astx.Int32)
    assert plan.store_conversion.numeric is not None
    assert plan.store_conversion.numeric.implicit
    assert info.resolved_assignment is not None
    assert info.resolved_assignment.target is plan.target


@pytest.mark.parametrize(
    "target, value",
    [
        (astx.Int64(), astx.LiteralUInt8(2)),
        (astx.UInt32(), astx.LiteralUInt8(2)),
        (astx.Float64(), astx.LiteralInt32(2)),
        (astx.Float32(), astx.LiteralFloat16(2.0)),
    ],
)
def test_compound_lossless_promotions(
    target: astx.DataType, value: astx.DataType
) -> None:
    """
    title: Compound operand and store conversions preserve complete domains.
    parameters:
      target:
        type: astx.DataType
      value:
        type: astx.DataType
    """
    module, node = compound_module(target_type=target, value=value)
    analyze(module)
    info = cast(SemanticInfo, node.semantic)
    plan = info.resolved_aug_assignment
    assert plan is not None
    assert type(plan.operation.computation_type) is type(target)
    assert plan.operation.flags.unsigned is isinstance(target, astx.UInt32)
    assert plan.operation.rhs_conversion is not None
    assert plan.operation.rhs_conversion.numeric is not None
    assert plan.operation.rhs_conversion.numeric.implicit
    assert type(plan.store_conversion.target_type) is type(target)


@pytest.mark.parametrize(
    "target, value, message",
    [
        (astx.Int8(), astx.LiteralInt32(1), "cannot assign"),
        (astx.UInt32(), astx.LiteralInt32(1), "cannot assign"),
        (astx.Float32(), astx.LiteralFloat64(1), "cannot assign"),
        (astx.Int64(), astx.LiteralUInt64(1), "no lossless common type"),
        (astx.Int32(), astx.LiteralBoolean(True), "numeric scalars"),
    ],
)
def test_compound_rejects_lossy_or_non_numeric_operands(
    target: astx.DataType, value: astx.DataType, message: str
) -> None:
    """
    title: Direct AST compounds cannot introduce narrowing or Boolean coercion.
    parameters:
      target:
        type: astx.DataType
      value:
        type: astx.DataType
      message:
        type: str
    """
    module, _ = compound_module(target_type=target, value=value)
    with pytest.raises(SemanticError, match=message):
        analyze(module)


@pytest.mark.parametrize(
    "operator", ["//=", "**=", "&=", "|=", "^=", "<<=", ">>="]
)
def test_compound_rejects_unimplemented_ast_opcodes(
    operator: OpCodeAugAssign,
) -> None:
    """
    title: ASTx modeling does not silently enable unsupported IRx operations.
    parameters:
      operator:
        type: OpCodeAugAssign
    """
    module, _ = compound_module(operator)
    with pytest.raises(SemanticError, match="unsupported compound assignment"):
        analyze(module)


@pytest.mark.parametrize(
    "field",
    [
        "semantic",
        "resolved_aug_assignment",
        "computation_type",
        "lhs_conversion",
        "rhs_conversion",
    ],
)
def test_compound_missing_metadata_fails_closed(field: str) -> None:
    """
    title: Compound lowering requires its resolved target and operand plan.
    parameters:
      field:
        type: str
    """
    module, node = compound_module()
    analyze(module)
    info = cast(SemanticInfo, node.semantic)
    plan = info.resolved_aug_assignment
    assert plan is not None
    if field == "semantic":
        node.semantic = None
    elif field == "resolved_aug_assignment":
        info.resolved_aug_assignment = None
    else:
        info.resolved_aug_assignment = replace(
            plan, operation=replace(plan.operation, **{field: None})
        )
    with pytest.raises(LoweringError, match=f"missing {field} metadata"):
        numeric_visitor().visit(node)


@pytest.mark.parametrize("invalid", ["constant", "unknown", "field"])
def test_compound_rejects_invalid_bindings(invalid: str) -> None:
    """
    title: Direct AST mutation validates binding identity and mutability.
    parameters:
      invalid:
        type: str
    """
    module, node = compound_module()
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    declaration = function.body.nodes[0]
    assert isinstance(declaration, astx.VariableDeclaration)
    if invalid == "constant":
        declaration.mutability = astx.MutabilityKind.constant
        message = "declared as constant"
    elif invalid == "unknown":
        node.target.name = "missing"
        message = "cannot resolve name"
    else:
        node.target = cast(
            astx.Identifier, astx.FieldAccess(astx.Identifier("x"), "value")
        )
        message = "identifier target"
    with pytest.raises(SemanticError, match=message):
        analyze(module)


@pytest.mark.parametrize("missing", [False, True])
def test_compound_store_conversion_fails_before_publication(
    missing: bool,
) -> None:
    """
    title: Missing or lossy store plans never fall back to unchecked narrowing.
    parameters:
      missing:
        type: bool
    """
    module, node = compound_module(
        target_type=astx.Float64(), value=astx.LiteralFloat64(2)
    )
    analyze(module)
    info = cast(SemanticInfo, node.semantic)
    plan = info.resolved_aug_assignment
    assert plan is not None
    info.resolved_aug_assignment = replace(
        plan,
        store_conversion=ImplicitConversion(
            None if missing else astx.Float64(), astx.Int32()
        ),
    )
    visitor = numeric_visitor()
    builder = visitor._llvm.ir_builder
    address = builder.alloca(ir.DoubleType())
    builder.store(ir.Constant(ir.DoubleType(), 3), address)
    visitor.named_values[plan.target.symbol_id] = address
    with pytest.raises(LoweringError, match="conversion"):
        visitor.visit(node)
    assert visitor.result_stack == []
    assert (
        len(
            [
                instruction
                for instruction in builder.block.instructions
                if instruction.opname == "store"
            ]
        )
        == 1
    )


def test_compound_lowering_uses_resolved_target_and_opcode() -> None:
    """
    title: Lowering follows analyzed identity and operation, not raw AST names.
    """
    module, node = compound_module(
        target_type=astx.Float64(), value=astx.LiteralFloat64(2)
    )
    analyze(module)
    info = cast(SemanticInfo, node.semantic)
    plan = info.resolved_aug_assignment
    assert plan is not None
    node.target.name = "not_the_resolved_binding"
    node.op_code = "-="
    visitor = numeric_visitor()
    builder = visitor._llvm.ir_builder
    address = builder.alloca(ir.DoubleType())
    builder.store(ir.Constant(ir.DoubleType(), 3), address)
    visitor.named_values[plan.target.symbol_id] = address
    visitor.visit(node)
    assert len(visitor.result_stack) == 1
    result = visitor.result_stack.pop()
    assert builder.block.instructions[-1].operands[0] is result
    builder.ret_void()
    text = str(visitor._llvm.module)
    llvm.parse_assembly(text).verify()
    assert "fadd double" in text
    assert "fsub double" not in text


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
