"""
title: Tests for the UnaryOp.
"""

import re

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.builder import Builder as LLVMBuilder
from irx.builder import Visitor
from irx.builder.base import Builder
from irx.system import Cast, PrintExpr
from llvmlite import binding as llvm

from .conftest import assert_build_output, check_result


@pytest.mark.parametrize(
    "int_type, literal_type",
    [
        (astx.Int32, astx.LiteralInt32),
        (astx.Int16, astx.LiteralInt16),
        (astx.Int8, astx.LiteralInt8),
        (astx.Int64, astx.LiteralInt64),
        (astx.UInt32, astx.LiteralUInt32),
        (astx.UInt16, astx.LiteralUInt16),
        (astx.UInt8, astx.LiteralUInt8),
        (astx.UInt64, astx.LiteralUInt64),
    ],
)
@pytest.mark.parametrize(
    "action,expected_file",
    [
        # ("translate", "test_unary_op.ll"),
        ("build", ""),
    ],
)
@pytest.mark.parametrize(
    "builder_class",
    [
        LLVMBuilder,
    ],
)
def test_unary_op_increment_decrement(
    action: str,
    expected_file: str,
    builder_class: type[Builder],
    int_type: type,
    literal_type: type,
) -> None:
    """
    title: Test ASTx UnaryOp for increment and decrement operations.
    parameters:
      action:
        type: str
      expected_file:
        type: str
      builder_class:
        type: type[Builder]
      int_type:
        type: type
      literal_type:
        type: type
    """
    builder = builder_class()
    module = builder.module()

    decl_a = astx.VariableDeclaration(
        name="a",
        type_=int_type(),
        value=literal_type(5),
        mutability=astx.MutabilityKind.mutable,
    )
    decl_b = astx.VariableDeclaration(
        name="b",
        type_=int_type(),
        value=literal_type(10),
        mutability=astx.MutabilityKind.mutable,
    )
    var_a = astx.Identifier("a")
    var_b = astx.Identifier("b")

    incr_a = astx.UnaryOp(op_code="++", operand=var_a)
    incr_a.type_ = int_type()
    decr_b = astx.UnaryOp(op_code="--", operand=var_b)
    decr_b.type_ = int_type()

    main_proto = astx.FunctionPrototype(
        name="main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    )
    main_block = astx.Block()
    main_block.append(decl_a)
    main_block.append(decl_b)
    main_block.append(incr_a)
    main_block.append(decr_b)
    main_block.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main_fn = astx.FunctionDef(prototype=main_proto, body=main_block)

    module.block.append(main_fn)

    check_result(action, builder, module, expected_file)


@pytest.mark.parametrize(
    "float_type, literal_type",
    [
        (astx.Float32, astx.LiteralFloat32),
        (astx.Float64, astx.LiteralFloat64),
    ],
)
@pytest.mark.parametrize(
    "builder_class",
    [
        LLVMBuilder,
    ],
)
def test_unary_op_increment_decrement_float(
    builder_class: type[Builder],
    float_type: type,
    literal_type: type,
) -> None:
    """
    title: Test ASTx UnaryOp increment and decrement for float types.
    parameters:
      builder_class:
        type: type[Builder]
      float_type:
        type: type
      literal_type:
        type: type
    """
    builder = builder_class()
    module = builder.module()

    decl_a = astx.VariableDeclaration(
        name="a",
        type_=float_type(),
        value=literal_type(5.0),
        mutability=astx.MutabilityKind.mutable,
    )
    decl_b = astx.VariableDeclaration(
        name="b",
        type_=float_type(),
        value=literal_type(10.0),
        mutability=astx.MutabilityKind.mutable,
    )

    incr_a = astx.UnaryOp(op_code="++", operand=astx.Identifier("a"))
    incr_a.type_ = float_type()
    decr_b = astx.UnaryOp(op_code="--", operand=astx.Identifier("b"))
    decr_b.type_ = float_type()

    main_proto = astx.FunctionPrototype(
        name="main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    )
    main_block = astx.Block()
    main_block.append(decl_a)
    main_block.append(decl_b)
    main_block.append(incr_a)
    main_block.append(decr_b)
    main_block.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    main_fn = astx.FunctionDef(prototype=main_proto, body=main_block)

    module.block.append(main_fn)

    check_result("build", builder, module, "")


@pytest.mark.parametrize(
    "int_type, literal_type, value",
    [
        (astx.Int32, astx.LiteralInt32, 0),
        (astx.Int32, astx.LiteralInt32, 5),
        (astx.Int32, astx.LiteralInt32, -3),
        (astx.Int16, astx.LiteralInt16, 0),
        (astx.Int16, astx.LiteralInt16, 7),
        (astx.UInt32, astx.LiteralUInt32, 0),
        (astx.UInt32, astx.LiteralUInt32, 10),
    ],
)
def test_unary_op_logical_not_int_rejected(
    int_type: type,
    literal_type: type,
    value: int,
) -> None:
    """
    title: Logical NOT should reject integer operands.
    parameters:
      int_type:
        type: type
      literal_type:
        type: type
      value:
        type: int
    """
    del int_type
    expr = astx.UnaryOp(op_code="!", operand=literal_type(value))

    with pytest.raises(
        SemanticError,
        match=r"unary operator '!' requires Boolean operand",
    ):
        analyze(expr)


@pytest.mark.parametrize(
    "value, expected_output",
    [
        (False, "1"),
        (True, "0"),
    ],
)
@pytest.mark.parametrize(
    "builder_class",
    [
        LLVMBuilder,
    ],
)
def test_unary_op_logical_not_boolean(
    builder_class: type[Builder],
    value: bool,
    expected_output: str,
) -> None:
    """
    title: Test logical NOT (!) for boolean type.
    parameters:
      builder_class:
        type: type[Builder]
      value:
        type: bool
      expected_output:
        type: str
    """
    builder = builder_class()
    module = builder.module()

    decl_a = astx.VariableDeclaration(
        name="a",
        type_=astx.Boolean(),
        value=astx.LiteralBoolean(value),
        mutability=astx.MutabilityKind.mutable,
    )

    not_a = astx.UnaryOp(op_code="!", operand=astx.Identifier("a"))
    not_a.type_ = astx.Boolean()

    main_proto = astx.FunctionPrototype(
        name="main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    )
    main_block = astx.Block()
    main_block.append(decl_a)
    main_block.append(not_a)
    main_block.append(
        astx.FunctionReturn(
            Cast(
                value=astx.UnaryOp(
                    op_code="!",
                    operand=astx.Identifier("a"),
                ),
                target_type=astx.Int32(),
            )
        )
    )

    main_fn = astx.FunctionDef(prototype=main_proto, body=main_block)

    module.block.append(main_fn)

    check_result("build", builder, module, expected_output=expected_output)


def build_print_module(*statements: astx.AST) -> astx.Module:
    """
    title: Build a module whose main runs statements and returns zero.
    parameters:
      statements:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    module = astx.Module()
    main_proto = astx.FunctionPrototype(
        name="main",
        args=astx.Arguments(),
        return_type=astx.Int32(),
    )
    main_block = astx.Block()
    for statement in statements:
        main_block.append(statement)
    main_block.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module.block.append(
        astx.FunctionDef(prototype=main_proto, body=main_block)
    )
    return module


@pytest.mark.parametrize(
    "int_type, literal_type",
    [
        (astx.Int8, astx.LiteralInt8),
        (astx.Int16, astx.LiteralInt16),
        (astx.Int32, astx.LiteralInt32),
        (astx.Int64, astx.LiteralInt64),
    ],
)
def test_unary_minus_and_plus_integer(
    int_type: type,
    literal_type: type,
) -> None:
    """
    title: Unary minus negates and unary plus keeps signed integers.
    parameters:
      int_type:
        type: type
      literal_type:
        type: type
    """
    module = build_print_module(
        astx.VariableDeclaration(
            name="a",
            type_=int_type(),
            value=literal_type(5),
            mutability=astx.MutabilityKind.mutable,
        ),
        PrintExpr(astx.UnaryOp(op_code="-", operand=astx.Identifier("a"))),
        PrintExpr(astx.UnaryOp(op_code="+", operand=astx.Identifier("a"))),
        PrintExpr(
            astx.UnaryOp(
                op_code="-",
                operand=astx.UnaryOp(
                    op_code="-", operand=astx.Identifier("a")
                ),
            )
        ),
    )

    assert_build_output(LLVMBuilder(), module, "-5\n5\n5")


@pytest.mark.parametrize(
    "float_type, literal_type",
    [
        (astx.Float32, astx.LiteralFloat32),
        (astx.Float64, astx.LiteralFloat64),
    ],
)
def test_unary_minus_float(float_type: type, literal_type: type) -> None:
    """
    title: Unary minus negates floats, including the sign of zero.
    parameters:
      float_type:
        type: type
      literal_type:
        type: type
    """
    module = build_print_module(
        astx.VariableDeclaration(
            name="a",
            type_=float_type(),
            value=literal_type(2.5),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.VariableDeclaration(
            name="zero",
            type_=float_type(),
            value=literal_type(0.0),
            mutability=astx.MutabilityKind.mutable,
        ),
        PrintExpr(astx.UnaryOp(op_code="-", operand=astx.Identifier("a"))),
        PrintExpr(astx.UnaryOp(op_code="-", operand=astx.Identifier("zero"))),
    )

    assert_build_output(LLVMBuilder(), module, "-2.500000\n-0.000000")


class FastMathBuilder(LLVMBuilder):
    """
    title: Builder whose translators start with fast math enabled.
    """

    def _new_translator(self) -> Visitor:
        """
        title: New translator with fast math enabled.
        returns:
          type: Visitor
        """
        translator = super()._new_translator()
        translator.set_fast_math(True)
        return translator


def build_float_negation_module() -> astx.Module:
    """
    title: Build a module that prints the negation of a Float64 zero.
    returns:
      type: astx.Module
    """
    return build_print_module(
        astx.VariableDeclaration(
            name="zero",
            type_=astx.Float64(),
            value=astx.LiteralFloat64(0.0),
            mutability=astx.MutabilityKind.mutable,
        ),
        PrintExpr(astx.UnaryOp(op_code="-", operand=astx.Identifier("zero"))),
    )


def test_unary_minus_float_ir_uses_fneg() -> None:
    """
    title: Float negation lowers to a plain fneg.
    """
    ir_text = LLVMBuilder().translate(build_float_negation_module())
    llvm.parse_assembly(ir_text)
    assert re.search(r"= fneg double %", ir_text)


def test_unary_minus_float_keeps_signed_zero_with_fast_math() -> None:
    """
    title: Fast math adds no flags such as nsz to fneg, so -(0.0) is -0.0.
    """
    builder = FastMathBuilder()
    ir_text = builder.translate(build_float_negation_module())
    llvm.parse_assembly(ir_text)
    fneg_lines = [line for line in ir_text.splitlines() if "fneg" in line]
    assert fneg_lines
    for line in fneg_lines:
        assert re.search(r"= fneg double %", line), line

    assert_build_output(builder, build_float_negation_module(), "-0.000000")


@pytest.mark.parametrize("op_code", ["-", "+"])
@pytest.mark.parametrize(
    "operand",
    [astx.LiteralBoolean(True), astx.LiteralUTF8String("a")],
)
def test_unary_minus_and_plus_reject_non_numeric(
    op_code: str,
    operand: astx.AST,
) -> None:
    """
    title: Unary minus and plus reject non-numeric operands.
    parameters:
      op_code:
        type: str
      operand:
        type: astx.AST
    """
    expr = astx.UnaryOp(op_code=op_code, operand=operand)
    with pytest.raises(
        SemanticError,
        match="unary sign requires a numeric operand",
    ):
        analyze(expr)


@pytest.mark.parametrize("op_code", ["*", "<", "not"])
def test_unary_operator_rejects_unsupported_operator(op_code: str) -> None:
    """
    title: Analysis rejects prefix operators that IRx cannot lower.
    parameters:
      op_code:
        type: str
    """
    expr = astx.UnaryOp(op_code=op_code, operand=astx.LiteralInt32(1))
    with pytest.raises(
        SemanticError,
        match=rf"unary operator '{re.escape(op_code)}' is not supported",
    ):
        analyze(expr)
