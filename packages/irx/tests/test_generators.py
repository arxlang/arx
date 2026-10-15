"""
title: Generator semantic and lowering tests.
"""

from __future__ import annotations

import shutil

import astx
import pytest

from irx.analysis import SemanticError, analyze, resource_ownership
from irx.analysis.resolved_nodes import IterationKind, OwnershipKind
from irx.builder import Builder

from .conftest import assert_build_output, assert_ir_parses

HAS_CLANG = shutil.which("clang") is not None


def _block_of(*nodes: astx.AST) -> astx.Block:
    """
    title: Build one block from nodes.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Block
    """
    block = astx.Block()
    for node in nodes:
        block.append(node)
    return block


def _numbers_function() -> astx.FunctionDef:
    """
    title: Build a generator function that yields three integers.
    returns:
      type: astx.FunctionDef
    """
    return astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "numbers",
            args=astx.Arguments(),
            return_type=astx.GeneratorType(astx.Int32()),
        ),
        body=_block_of(
            astx.VariableDeclaration(
                "current",
                astx.Int32(),
                mutability=astx.MutabilityKind.mutable,
                value=astx.LiteralInt32(1),
            ),
            astx.YieldStmt(astx.Identifier("current")),
            astx.VariableAssignment("current", astx.LiteralInt32(2)),
            astx.YieldStmt(astx.Identifier("current")),
            astx.VariableAssignment("current", astx.LiteralInt32(3)),
            astx.YieldStmt(astx.Identifier("current")),
        ),
    )


def _sum_generator_module() -> astx.Module:
    """
    title: Build one module that sums values yielded by a generator.
    returns:
      type: astx.Module
    """
    module = astx.Module()
    module.block.append(_numbers_function())

    loop = astx.ForInLoopStmt(
        astx.Identifier("item"),
        astx.FunctionCall("numbers", []),
        _block_of(
            astx.VariableAssignment(
                "total",
                astx.BinaryOp(
                    "+",
                    astx.Identifier("total"),
                    astx.Identifier("item"),
                ),
            )
        ),
    )
    main_body = _block_of(
        astx.VariableDeclaration(
            "total",
            astx.Int32(),
            mutability=astx.MutabilityKind.mutable,
            value=astx.LiteralInt32(0),
        ),
        loop,
        astx.FunctionReturn(astx.Identifier("total")),
    )
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "main",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=main_body,
        )
    )
    return module


def _sum_generator_float_target_module() -> astx.Module:
    """
    title: Build a module that iterates Int32 yields into a Float64 target.
    returns:
      type: astx.Module
    """
    module = astx.Module()
    module.block.append(_numbers_function())

    loop = astx.ForInLoopStmt(
        astx.InlineVariableDeclaration("item", astx.Float64()),
        astx.FunctionCall("numbers", []),
        _block_of(
            astx.VariableAssignment(
                "total",
                astx.BinaryOp(
                    "+",
                    astx.Identifier("total"),
                    astx.Identifier("item"),
                ),
            )
        ),
    )
    main_body = _block_of(
        astx.VariableDeclaration(
            "total",
            astx.Float64(),
            mutability=astx.MutabilityKind.mutable,
            value=astx.LiteralFloat64(0.0),
        ),
        loop,
        astx.FunctionReturn(astx.Cast(astx.Identifier("total"), astx.Int32())),
    )
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "main",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=main_body,
        )
    )
    return module


def _guarded_exhaustion_module() -> astx.Module:
    """
    title: Build a module that re-iterates an exhausted generator.
    returns:
      type: astx.Module
    """
    guarded_generator = astx.FunctionDef(
        prototype=astx.FunctionPrototype(
            "guarded",
            args=astx.Arguments(),
            return_type=astx.GeneratorType(astx.Int32()),
        ),
        body=_block_of(
            astx.VariableDeclaration(
                "current",
                astx.Int32(),
                mutability=astx.MutabilityKind.mutable,
                value=astx.LiteralInt32(1),
            ),
            astx.YieldStmt(astx.Identifier("current")),
            astx.VariableAssignment(
                "current",
                astx.BinaryOp(
                    "+",
                    astx.Identifier("current"),
                    astx.LiteralInt32(1),
                ),
            ),
            astx.AssertStmt(
                astx.BinaryOp(
                    "==",
                    astx.Identifier("current"),
                    astx.LiteralInt32(2),
                )
            ),
        ),
    )
    first_loop = astx.ForInLoopStmt(
        astx.Identifier("item"),
        astx.Identifier("values"),
        _block_of(
            astx.VariableAssignment(
                "total",
                astx.BinaryOp(
                    "+",
                    astx.Identifier("total"),
                    astx.Identifier("item"),
                ),
            )
        ),
    )
    second_loop = astx.ForInLoopStmt(
        astx.Identifier("again"),
        astx.Identifier("values"),
        _block_of(
            astx.VariableAssignment(
                "total",
                astx.BinaryOp(
                    "+",
                    astx.Identifier("total"),
                    astx.Identifier("again"),
                ),
            )
        ),
    )
    module = astx.Module()
    module.block.append(guarded_generator)
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "main",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=_block_of(
                astx.VariableDeclaration(
                    "total",
                    astx.Int32(),
                    mutability=astx.MutabilityKind.mutable,
                    value=astx.LiteralInt32(0),
                ),
                astx.VariableDeclaration(
                    "values",
                    astx.GeneratorType(astx.Int32()),
                    value=astx.FunctionCall("guarded", []),
                ),
                first_loop,
                second_loop,
                astx.FunctionReturn(astx.Identifier("total")),
            ),
        )
    )
    return module


def test_generator_iteration_semantics() -> None:
    """
    title: Generator values should resolve as generator iterables.
    """
    module = analyze(_sum_generator_module())
    assert isinstance(module, astx.Module)
    main_function = module.nodes[1]
    assert isinstance(main_function, astx.FunctionDef)
    loop = main_function.body.nodes[1]
    assert isinstance(loop, astx.ForInLoopStmt)

    semantic = getattr(loop, "semantic", None)
    iteration = getattr(semantic, "resolved_iteration", None)
    assert iteration is not None
    assert iteration.kind is IterationKind.GENERATOR
    assert isinstance(iteration.element_type, astx.Int32)


def test_yield_requires_generator_return_type() -> None:
    """
    title: A function with yield must declare GeneratorType.
    """
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "bad",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=_block_of(astx.YieldStmt(astx.LiteralInt32(1))),
        )
    )
    with pytest.raises(SemanticError):
        analyze(module)


def test_nested_yield_is_diagnosed() -> None:
    """
    title: Nested yield sites should be rejected during analysis.
    """
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "bad",
                args=astx.Arguments(),
                return_type=astx.GeneratorType(astx.Int32()),
            ),
            body=_block_of(
                astx.IfStmt(
                    astx.LiteralBoolean(True),
                    _block_of(astx.YieldStmt(astx.LiteralInt32(1))),
                )
            ),
        )
    )
    with pytest.raises(
        SemanticError,
        match="yield inside nested control flow is not supported yet",
    ):
        analyze(module)


def test_owned_list_local_in_generator_has_frame_cleanup() -> None:
    """
    title: Generator frames should destroy owned list locals when closed.
    """
    list_type = astx.ListType([astx.Int32()])
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "bad_list_owner",
                args=astx.Arguments(),
                return_type=astx.GeneratorType(astx.Int32()),
            ),
            body=_block_of(
                astx.VariableDeclaration(
                    "values",
                    list_type,
                    mutability=astx.MutabilityKind.mutable,
                    value=astx.ListCreate(astx.Int32()),
                ),
                astx.YieldStmt(astx.LiteralInt32(1)),
            ),
        )
    )

    analyze(module)
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    declaration = function.body.nodes[0]
    ownership = resource_ownership(declaration)
    assert ownership is not None
    assert ownership.kind is OwnershipKind.OWNED

    ir_text = Builder().translate(module)
    assert "bad_list_owner.__destroy" in ir_text
    assert 'call void @"irx_list_destroy"' in ir_text
    assert_ir_parses(ir_text)


def test_owned_string_local_in_generator_has_frame_cleanup() -> None:
    """
    title: Generator frames should free owned string locals when closed.
    """
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "bad_string_owner",
                args=astx.Arguments(),
                return_type=astx.GeneratorType(astx.Int32()),
            ),
            body=_block_of(
                astx.VariableDeclaration(
                    "message",
                    astx.String(),
                    value=astx.BinaryOp(
                        "+",
                        astx.LiteralString("owned"),
                        astx.LiteralString(" string"),
                    ),
                ),
                astx.YieldStmt(astx.LiteralInt32(1)),
            ),
        )
    )

    analyze(module)
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    declaration = function.body.nodes[0]
    ownership = resource_ownership(declaration)
    assert ownership is not None
    assert ownership.kind is OwnershipKind.OWNED

    ir_text = Builder().translate(module)
    assert "bad_string_owner.__destroy" in ir_text
    assert 'call void @"free"' in ir_text
    assert_ir_parses(ir_text)


def test_owned_tensor_local_in_generator_has_frame_cleanup() -> None:
    """
    title: Generator frames should release owned tensor locals when closed.
    """
    tensor_type = astx.TensorType(astx.Int32(), shape=(1,))
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "bad_tensor_owner",
                args=astx.Arguments(),
                return_type=astx.GeneratorType(astx.Int32()),
            ),
            body=_block_of(
                astx.VariableDeclaration(
                    "values",
                    tensor_type,
                    value=astx.TensorLiteral(
                        (astx.LiteralInt32(1),),
                        element_type=astx.Int32(),
                        shape=(1,),
                    ),
                ),
                astx.YieldStmt(astx.LiteralInt32(1)),
            ),
        )
    )

    analyze(module)
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    declaration = function.body.nodes[0]
    ownership = resource_ownership(declaration)
    assert ownership is not None
    assert ownership.kind is OwnershipKind.OWNED

    ir_text = Builder().translate(module)
    assert "bad_tensor_owner.__destroy" in ir_text
    assert 'call i32 @"irx_buffer_view_release"' in ir_text
    assert_ir_parses(ir_text)


def test_yield_from_is_diagnosed() -> None:
    """
    title: Yield-from should be rejected during analysis for this MVP.
    """
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "bad",
                args=astx.Arguments(),
                return_type=astx.GeneratorType(astx.Int32()),
            ),
            body=_block_of(astx.YieldFromExpr(astx.FunctionCall("bad", []))),
        )
    )
    with pytest.raises(
        SemanticError,
        match="yield from is not supported yet",
    ):
        analyze(module)


def test_generator_return_value_is_diagnosed() -> None:
    """
    title: Generator return values should be rejected during analysis.
    """
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "bad",
                args=astx.Arguments(),
                return_type=astx.GeneratorType(astx.Int32()),
            ),
            body=_block_of(
                astx.YieldStmt(astx.LiteralInt32(1)),
                astx.FunctionReturn(astx.LiteralInt32(2)),
            ),
        )
    )
    with pytest.raises(
        SemanticError,
        match="generator functions may only use bare return or return None",
    ):
        analyze(module)


def test_generator_ir_parses() -> None:
    """
    title: Generator lowering should emit parseable LLVM IR.
    """
    ir_text = Builder().translate(_sum_generator_module())
    assert "numbers.__resume" in ir_text
    assert_ir_parses(ir_text)


def test_generator_resume_uses_element_slot() -> None:
    """
    title: Resume calls should write into yielded element storage.
    """
    ir_text = Builder().translate(_sum_generator_float_target_module())
    assert '%"item_yielded" = alloca i32' in ir_text
    resume_call = 'call i1 %"generator_resume"(i8* %"generator_frame", i32*'
    assert resume_call in ir_text
    assert_ir_parses(ir_text)


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_generator_executes() -> None:
    """
    title: A for-in loop should consume yielded generator values.
    """
    expected_sum = 6
    assert_build_output(Builder(), _sum_generator_module(), str(expected_sum))


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_generator_target_cast_executes() -> None:
    """
    title: Generator values should cast after resume into loop targets.
    """
    expected_sum = 6
    assert_build_output(
        Builder(),
        _sum_generator_float_target_module(),
        str(expected_sum),
    )


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_exhausted_generator_stays_done() -> None:
    """
    title: Exhausted generators should not re-run tail statements.
    """
    expected_sum = 1
    assert_build_output(
        Builder(),
        _guarded_exhaustion_module(),
        str(expected_sum),
    )


def test_resumed_owned_locals_have_dominating_failure_cleanup() -> None:
    """
    title: Cleanup after yield must not reference storage in an earlier state.
    """
    module = _sum_generator_module()
    function = module.nodes[0]
    assert isinstance(function, astx.FunctionDef)
    function.body.nodes.insert(
        0,
        astx.VariableDeclaration(
            "first",
            astx.String(),
            value=astx.BinaryOp(
                "+", astx.LiteralString("a"), astx.LiteralString("b")
            ),
        ),
    )
    function.body.nodes.insert(
        3,
        astx.VariableDeclaration(
            "second",
            astx.String(),
            value=astx.BinaryOp(
                "+", astx.LiteralString("c"), astx.LiteralString("d")
            ),
        ),
    )
    ir_text = Builder().translate(module)
    assert "generator.allocation.fail" in ir_text
    assert "ARX-RUNTIME-ALLOCATION-001" in ir_text
    assert_ir_parses(ir_text)
    if HAS_CLANG:
        assert_build_output(Builder(), module, "6")


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
@pytest.mark.parametrize("present", [False, True])
@pytest.mark.parametrize("tensor", [False, True])
def test_generator_captures_nullable_owners(
    present: bool, tensor: bool
) -> None:
    """
    title: Copy valid captures and guard absent pointer or aggregate payloads.
    parameters:
      present:
        type: bool
      tensor:
        type: bool
    """
    payload = (
        astx.TensorType(astx.Int32(), shape=(1,)) if tensor else astx.String()
    )
    generator = astx.FunctionDef(
        astx.FunctionPrototype(
            "capture",
            astx.Arguments(astx.Argument("value", astx.NullableType(payload))),
            astx.GeneratorType(astx.Boolean()),
        ),
        _block_of(
            astx.YieldStmt(
                astx.NullableQuery(
                    astx.NullableOperation.IS_VALID, astx.Identifier("value")
                )
            )
        ),
    )
    value: astx.Expr = astx.LiteralNone()
    if present:
        value = (
            astx.TensorLiteral(
                (astx.LiteralInt32(5),), element_type=astx.Int32(), shape=(1,)
            )
            if tensor
            else astx.LiteralString("owned")
        )
    main = astx.FunctionDef(
        astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
        _block_of(
            astx.ForInLoopStmt(
                astx.Identifier("item"),
                astx.FunctionCall("capture", [value]),
                _block_of(
                    astx.AssertStmt(
                        astx.BinaryOp(
                            "==",
                            astx.Identifier("item"),
                            astx.LiteralBoolean(present),
                        )
                    )
                ),
            ),
            astx.FunctionReturn(astx.LiteralInt32(0)),
        ),
    )
    module = astx.Module()
    module.block.append(generator)
    module.block.append(main)
    assert_ir_parses(Builder().translate(module))
    assert_build_output(Builder(), module, "0")
