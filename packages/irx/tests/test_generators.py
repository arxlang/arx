"""
title: Generator semantic and lowering tests.
"""

from __future__ import annotations

import shutil

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.analysis.resolved_nodes import IterationKind
from irx.builder import Builder

from .conftest import assert_build_output, assert_ir_parses, build_and_run

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


def test_owned_list_local_in_generator_is_diagnosed() -> None:
    """
    title: >-
      Generator frames should reject owned lists until close cleanup exists.
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

    with pytest.raises(
        SemanticError,
        match="owned list locals in generators require generator lifecycle",
    ):
        analyze(module)


def test_owned_string_local_in_generator_is_diagnosed() -> None:
    """
    title: >-
      Generator frames should reject owned strings until close cleanup exists.
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

    with pytest.raises(
        SemanticError,
        match="owned string locals in generators require generator lifecycle",
    ):
        analyze(module)


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
    resume_call = next(
        line
        for line in ir_text.splitlines()
        if 'call i32 %"generator_resume"' in line
    )
    assert 'i8* %"generator_frame"' in resume_call
    context_and_frame_count = 2
    assert resume_call.count("i8*") == context_and_frame_count
    assert '%"generator.produced" = alloca i1' in ir_text
    assert 'i32* %"item_yielded", i1* %"generator.produced"' in ir_text
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


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_generator_failure_is_not_exhaustion() -> None:
    """
    title: A failed resume propagates once and leaves the generator exhausted.
    """
    tree = _sum_generator_module()
    generator = tree.nodes[0]
    assert isinstance(generator, astx.FunctionDef)
    generator.body.nodes.insert(
        2,
        astx.ThrowStmt(
            astx.ClassConstruct(
                "ValueError", (astx.LiteralString("resume failed"),)
            )
        ),
    )
    main = tree.nodes[1]
    assert isinstance(main, astx.FunctionDef)
    loop = main.body.nodes[1]
    assert isinstance(loop, astx.ForInLoopStmt)
    loop.iterable = astx.Identifier("values")
    main.body = _block_of(
        main.body.nodes[0],
        astx.VariableDeclaration(
            "values",
            astx.GeneratorType(astx.Int32()),
            value=astx.FunctionCall("numbers", []),
        ),
        astx.ExceptionHandlerStmt(
            _block_of(loop),
            [
                astx.CatchHandlerStmt(
                    _block_of(
                        astx.VariableAssignment(
                            "total",
                            astx.BinaryOp(
                                "+",
                                astx.Identifier("total"),
                                astx.LiteralInt32(10),
                            ),
                        )
                    ),
                    types=[astx.Identifier("ValueError")],
                )
            ],
        ),
        astx.ForInLoopStmt(
            astx.Identifier("again"),
            astx.Identifier("values"),
            _block_of(astx.VariableAssignment("total", astx.LiteralInt32(99))),
        ),
        astx.FunctionReturn(astx.Identifier("total")),
    )
    assert_ir_parses(Builder().translate(tree))
    assert_build_output(Builder(), tree, "11")


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_generator_return_runs_nonsuspending_finally() -> None:
    """
    title: A generator return executes a finalizer before reporting exhaustion.
    """
    tree = _sum_generator_module()
    generator = tree.nodes[0]
    assert isinstance(generator, astx.FunctionDef)
    generator.body = _block_of(
        astx.YieldStmt(astx.LiteralInt32(1)),
        astx.ExceptionHandlerStmt(
            _block_of(astx.FunctionReturn(astx.LiteralNone())),
            [],
            astx.FinallyHandlerStmt(
                _block_of(astx.PrintExpr(astx.LiteralString("done")))
            ),
        ),
    )
    result = build_and_run(Builder(), tree)
    assert result.returncode == 1
    assert result.stdout.strip() == "done"
    assert result.stderr == ""
