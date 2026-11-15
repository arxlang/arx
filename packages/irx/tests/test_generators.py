"""
title: Generator semantic and lowering tests.
"""

from __future__ import annotations

import shutil
import subprocess

from pathlib import Path

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.analysis.resolved_nodes import IterationKind
from irx.builder import Builder
from llvmlite import ir

from .conftest import (
    assert_build_output,
    assert_ir_parses,
    build_and_run,
    make_main_module,
)

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
    assert '%"cursor.item" = alloca i32' in ir_text
    resume_call = next(
        line
        for line in ir_text.splitlines()
        if 'i32* %"cursor.item", i1* %"cursor.produced"' in line
    )
    context_and_frame_count = 2
    assert resume_call.count("i8*") == context_and_frame_count
    assert '%"cursor.produced" = alloca i1' in ir_text
    assert 'i32* %"cursor.item", i1* %"cursor.produced"' in ir_text
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
    second = main.body.nodes[3]
    main.body.nodes[3] = astx.ExceptionHandlerStmt(
        _block_of(second, astx.AssertStmt(astx.LiteralBoolean(False))),
        [
            astx.CatchHandlerStmt(
                _block_of(astx.LiteralInt32(0)),
                types=[astx.Identifier("RuntimeError")],
            )
        ],
    )
    assert_build_output(Builder(), tree, "11")


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
@pytest.mark.parametrize("transfer", ["break", "continue", "nested"])
def test_generator_cursor_closes_and_rejects_reacquisition(
    transfer: str,
) -> None:
    """
    title: Closed one-shot cursors reject reuse while preserving live owners.
    parameters:
      transfer:
        type: str
    """
    tree = _sum_generator_module()
    main = tree.nodes[1]
    assert isinstance(main, astx.FunctionDef)
    loop = main.body.nodes[1]
    assert isinstance(loop, astx.ForInLoopStmt)
    loop.iterable = astx.Identifier("values")
    repeated = astx.ForInLoopStmt(
        astx.Identifier("again"),
        astx.Identifier("values"),
        _block_of(astx.AssertStmt(astx.LiteralBoolean(False))),
    )
    if transfer == "nested":
        loop.body.append(
            astx.ExceptionHandlerStmt(
                _block_of(repeated),
                [
                    astx.CatchHandlerStmt(
                        _block_of(astx.LiteralInt32(0)),
                        types=[astx.Identifier("RuntimeError")],
                    )
                ],
            )
        )
    else:
        loop.body.append(
            astx.BreakStmt() if transfer == "break" else astx.ContinueStmt()
        )
    main.body = _block_of(
        main.body.nodes[0],
        astx.VariableDeclaration(
            "values",
            astx.GeneratorType(astx.Int32()),
            value=astx.FunctionCall("numbers", []),
        ),
        loop,
        astx.ExceptionHandlerStmt(
            _block_of(
                astx.ForInLoopStmt(
                    astx.Identifier("again"),
                    astx.Identifier("values"),
                    _block_of(astx.AssertStmt(astx.LiteralBoolean(False))),
                ),
                astx.AssertStmt(astx.LiteralBoolean(False)),
            ),
            [
                astx.CatchHandlerStmt(
                    _block_of(astx.FunctionReturn(astx.Identifier("total"))),
                    types=[astx.Identifier("RuntimeError")],
                )
            ],
        ),
        astx.FunctionReturn(astx.LiteralInt32(99)),
    )
    assert_build_output(Builder(), tree, "1" if transfer == "break" else "6")


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_nullable_generator_item_is_not_exhaustion() -> None:
    """
    title: Nullable payload validity and cursor-produced state remain separate.
    """
    type_ = astx.NullableType(astx.Int32())
    function = astx.FunctionDef(
        astx.FunctionPrototype(
            "nullable_items", astx.Arguments(), astx.GeneratorType(type_)
        ),
        _block_of(
            astx.YieldStmt(astx.Cast(astx.LiteralNone(), type_)),
            astx.YieldStmt(astx.Cast(astx.LiteralInt32(7), type_)),
        ),
    )
    module = make_main_module(
        astx.VariableDeclaration(
            "count",
            astx.Int32(),
            value=astx.LiteralInt32(0),
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.ForInLoopStmt(
            astx.Identifier("value"),
            astx.FunctionCall("nullable_items", []),
            _block_of(
                astx.VariableAssignment(
                    "count",
                    astx.BinaryOp(
                        "+", astx.Identifier("count"), astx.LiteralInt32(10)
                    ),
                ),
                astx.IfStmt(
                    astx.NullCheck(astx.Identifier("value")),
                    _block_of(
                        astx.VariableAssignment(
                            "count",
                            astx.BinaryOp(
                                "+",
                                astx.Identifier("count"),
                                astx.LiteralInt32(1),
                            ),
                        )
                    ),
                ),
            ),
        ),
        astx.FunctionReturn(astx.Identifier("count")),
    )
    module.block.insert(0, function)
    assert_build_output(Builder(), module, "21")


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


@pytest.mark.parametrize(
    "operation",
    ["index", "iteration", "text_index", "slice", "split", "strip"],
)
def test_owned_string_access_in_generators_is_diagnosed(
    operation: str,
) -> None:
    """
    title: Owned text results cannot escape generator frame cleanup.
    parameters:
      operation:
        type: str
    """
    if operation == "iteration":
        statement: astx.AST = astx.ForInLoopStmt(
            astx.Identifier("word"),
            astx.Identifier("values"),
            _block_of(astx.Identifier("word")),
        )
    elif operation == "index":
        statement = astx.ListIndex(
            astx.Identifier("values"), astx.LiteralInt32(0)
        )
    elif operation in {"text_index", "slice"}:
        statement = astx.SubscriptExpr(
            astx.LiteralString("text"),
            index=astx.LiteralInt32(0) if operation == "text_index" else None,
        )
    else:
        statement = astx.MethodCall(astx.LiteralString("text"), operation, [])
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "words",
                astx.Arguments(
                    astx.Argument("values", astx.ListType([astx.String()]))
                ),
                astx.GeneratorType(astx.Int32()),
            ),
            _block_of(statement, astx.YieldStmt(astx.LiteralInt32(1))),
        )
    )
    with pytest.raises(
        SemanticError, match=r"generators require.*lifecycle cleanup"
    ):
        analyze(module)


@pytest.mark.parametrize(
    "type_,value",
    [
        (
            astx.TensorType(astx.Int32(), shape=(1,)),
            astx.TensorLiteral(
                [astx.LiteralInt32(1)], element_type=astx.Int32(), shape=(1,)
            ),
        ),
        (astx.DataFrameType(), astx.Undefined()),
        (astx.FileType(), astx.Undefined()),
    ],
)
def test_generator_frames_reject_owned_non_scalar_locals(
    type_: astx.DataType, value: astx.Expr
) -> None:
    """
    title: Frame deallocation must not bypass nested resource destruction.
    parameters:
      type_:
        type: astx.DataType
      value:
        type: astx.Expr
    """
    function = _numbers_function()
    function.body = _block_of(
        astx.VariableDeclaration(
            "resource",
            type_,
            value=value,
            mutability=astx.MutabilityKind.mutable,
        ),
        astx.YieldStmt(astx.LiteralInt32(1)),
    )
    module = astx.Module()
    module.block.append(function)
    with pytest.raises(SemanticError, match="non-scalar locals in generators"):
        analyze(module)


@pytest.mark.skipif(not HAS_CLANG, reason="clang is required for build tests")
def test_materialization_failure_closes_borrowed_iterator() -> None:
    """
    title: Failed copies close one-shot state without freeing its owner.
    """

    def materialize(limit: int) -> astx.FunctionCall:
        """
        title: Borrow the same iterator with an exact i64 bound.
        parameters:
          limit:
            type: int
        returns:
          type: astx.FunctionCall
        """
        return astx.FunctionCall(
            "list",
            [astx.Identifier("source")],
            keywords=(
                astx.KeywordArgument("max_items", astx.LiteralInt64(limit)),
            ),
        )

    module = make_main_module(
        astx.VariableDeclaration(
            "source",
            astx.GeneratorType(astx.Int32()),
            value=astx.FunctionCall("numbers", []),
        ),
        astx.ExceptionHandlerStmt(
            _block_of(
                materialize(0), astx.AssertStmt(astx.LiteralBoolean(False))
            ),
            [
                astx.CatchHandlerStmt(
                    _block_of(astx.LiteralInt32(0)),
                    types=[astx.Identifier("ValueError")],
                )
            ],
        ),
        astx.ExceptionHandlerStmt(
            _block_of(materialize(2**63 - 1)),
            [
                astx.CatchHandlerStmt(
                    _block_of(astx.FunctionReturn(astx.LiteralInt32(0))),
                    types=[astx.Identifier("RuntimeError")],
                )
            ],
        ),
        astx.AssertStmt(astx.LiteralBoolean(False)),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    module.block.insert(0, _numbers_function())
    result = build_and_run(Builder(), module)
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def materialization_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """
    title: >-
      Compile bounded consumption once, with finite and infinite ABI inputs.
    summary: >-
      The test resume adapter exercises an infinite single-pass source without
      claiming nested source-level yield support. Allocation counters prove
      frame cleanup on normal completion and checked failures.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: Path
    """
    if not HAS_CLANG:
        pytest.skip("native generator checks require clang")
    bound = astx.BinaryOp(
        "-", astx.FunctionCall("getchar", []), astx.LiteralInt32(1)
    )
    materialized = astx.FunctionCall(
        "list",
        [astx.FunctionCall("numbers", [])],
        keywords=(astx.KeywordArgument("max_items", bound),),
    )
    module = make_main_module(
        astx.VariableDeclaration(
            "result", astx.ListType([astx.Int32()]), value=materialized
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    external = astx.FunctionPrototype(
        "getchar", astx.Arguments(), return_type=astx.Int32()
    )
    external.is_extern = True
    external.calling_convention = "c"
    module.block.insert(0, external)
    module.block.insert(0, _numbers_function())
    builder = Builder()
    builder.translate(module)
    llvm_module = builder.translator._llvm.module
    integer = ir.IntType(32)
    counters = {}
    for name in ("frames", "lists", "resumes", "infinite"):
        global_ = ir.GlobalVariable(llvm_module, integer, "test." + name)
        global_.initializer = ir.Constant(integer, 0)
        counters[name] = global_
    originals = list(llvm_module.functions)
    resume = next(
        function
        for function in originals
        if function.name.endswith(".__resume")
    )
    for original, delta in (
        (llvm_module.get_global("malloc"), 1),
        (llvm_module.get_global("free"), -1),
        (resume, 0),
        (llvm_module.get_global("irx_list_append"), 0),
        (llvm_module.get_global("irx_list_destroy"), 0),
    ):
        wrapper = ir.Function(
            llvm_module, original.function_type, "test." + original.name
        )
        for function in originals:
            for bb in function.blocks:
                for instruction in bb.instructions:
                    instruction.replace_usage(original, wrapper)
        emitter = ir.IRBuilder(wrapper.append_basic_block("entry"))
        if original is resume:
            counter = counters["resumes"]
            emitter.store(
                emitter.add(emitter.load(counter), ir.Constant(integer, 1)),
                counter,
            )
            with emitter.if_then(
                emitter.icmp_signed(
                    "!=",
                    emitter.load(counters["infinite"]),
                    ir.Constant(integer, 0),
                )
            ):
                emitter.store(ir.Constant(ir.IntType(32), 7), wrapper.args[2])
                emitter.store(ir.Constant(ir.IntType(1), 1), wrapper.args[3])
                emitter.ret(ir.Constant(integer, 0))
        else:
            counter = counters["frames"]
            emitter.store(
                emitter.add(
                    emitter.load(counter), ir.Constant(integer, delta)
                ),
                counter,
            )
        data_slot = None
        before = None
        if original.name in {"irx_list_append", "irx_list_destroy"}:
            data_slot = emitter.gep(
                wrapper.args[0],
                [ir.Constant(integer, 0), ir.Constant(integer, 0)],
            )
            data = emitter.load(data_slot)
            before = emitter.zext(
                emitter.icmp_unsigned(
                    "!=", data, ir.Constant(data.type, None)
                ),
                integer,
            )
        result = emitter.call(original, list(wrapper.args))
        if data_slot is not None and before is not None:
            data = emitter.load(data_slot)
            after = emitter.zext(
                emitter.icmp_unsigned(
                    "!=", data, ir.Constant(data.type, None)
                ),
                integer,
            )
            counter = counters["lists"]
            emitter.store(
                emitter.add(emitter.load(counter), emitter.sub(after, before)),
                counter,
            )

        if isinstance(result.type, ir.VoidType):
            emitter.ret_void()
        else:
            emitter.ret(result)
    text = str(llvm_module).replace(
        'define i32 @"main"()', 'define i32 @"test.original_main"()'
    )
    # Encode resumes even on failure; a leaked frame has a distinct code.
    text += """
define i32 @main() {
entry:
  %mode = call i32 @getchar()
  store i32 %mode, i32* @test.infinite
  %result = call i32 @test.original_main()
  %frames = load i32, i32* @test.frames
  %resumes = load i32, i32* @test.resumes
  %clean_frames = icmp eq i32 %frames, 0
  %lists = load i32, i32* @test.lists
  %clean_lists = icmp eq i32 %lists, 0
  %clean = and i1 %clean_frames, %clean_lists
  %failure = mul i32 %result, 20
  %code = add i32 %failure, %resumes
  %output = select i1 %clean, i32 %code, i32 99
  ret i32 %output
}
"""
    assert_ir_parses(text)
    executable = tmp_path_factory.mktemp("materialization") / "probe"
    builder._build_from_ir(text, str(executable))
    return executable


@pytest.mark.parametrize(
    "infinite,bound,resumes,failure",
    [
        (False, -1, 0, True),
        (False, 0, 1, True),
        (False, 1, 2, True),
        (False, 3, 4, False),
        (False, 4, 4, False),
        (True, 0, 1, True),
        (True, 1, 2, True),
        (True, 7, 8, True),
    ],
)
def test_bounded_materialization_consumption(
    materialization_binary: Path,
    infinite: bool,
    bound: int,
    resumes: int,
    failure: bool,
) -> None:
    """
    title: Consume at most N+1 items once and release owned frames on failure.
    parameters:
      materialization_binary:
        type: Path
      infinite:
        type: bool
      bound:
        type: int
      resumes:
        type: int
      failure:
        type: bool
    """
    result = subprocess.run(
        [str(materialization_binary)],
        input=bytes([int(infinite), bound + 1]),
        check=False,
        capture_output=True,
    )
    assert result.returncode == int(failure) * 20 + resumes, result.stderr
    if failure:
        assert b"max_items" in result.stderr
