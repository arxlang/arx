"""
title: Iterable semantic and lowering tests.
"""

from __future__ import annotations

import shutil

from pathlib import Path
from typing import Literal

import astx
import pytest

from astx.base import SourceLocation
from irx.analysis import SemanticError, analyze
from irx.analysis.resolved_nodes import IterationKind
from irx.builder import Builder
from irx.diagnostics import DiagnosticCodes, LoweringError

from .conftest import assert_build_output, assert_ir_parses
from .test_dynamic_list import (
    _list_i32_type,
    _mutable_decl,
    assert_executed_list_cleanups,
)
from .test_string import assert_executed_string_frees

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


def _main_module(*nodes: astx.AST) -> astx.Module:
    """
    title: Build one Int32 main module.
    parameters:
      nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    module = astx.Module()
    body = astx.Block()
    for node in nodes:
        body.append(node)
    module.block.append(
        astx.FunctionDef(
            prototype=astx.FunctionPrototype(
                "main",
                args=astx.Arguments(),
                return_type=astx.Int32(),
            ),
            body=body,
        )
    )
    return module


def _literal_list(*values: int) -> astx.LiteralList:
    """
    title: Build one Int32 literal list.
    parameters:
      values:
        type: int
        variadic: positional
    returns:
      type: astx.LiteralList
    """
    return astx.LiteralList([astx.LiteralInt32(value) for value in values])


def _sum_for_in_module() -> astx.Module:
    """
    title: Build one module that sums a literal list with for-in.
    returns:
      type: astx.Module
    """
    loop_body = _block_of(
        astx.VariableAssignment(
            "total",
            astx.BinaryOp(
                "+",
                astx.Identifier("total"),
                astx.Identifier("item"),
            ),
        )
    )
    loop = astx.ForInLoopStmt(
        astx.Identifier("item"),
        _literal_list(1, 2, 3),
        loop_body,
    )
    return _main_module(
        astx.VariableDeclaration(
            "total",
            astx.Int32(),
            mutability=astx.MutabilityKind.mutable,
            value=astx.LiteralInt32(0),
        ),
        loop,
        astx.FunctionReturn(astx.Identifier("total")),
    )


def _filtered_comprehension_module() -> astx.Module:
    """
    title: Build one module that returns a filtered list-comprehension length.
    returns:
      type: astx.Module
    """
    comprehension = astx.ListComprehension(
        element=astx.BinaryOp(
            "*",
            astx.Identifier("item"),
            astx.LiteralInt32(2),
        ),
        generators=[
            astx.ComprehensionClause(
                astx.Identifier("item"),
                _literal_list(1, 2, 3),
                [
                    astx.BinaryOp(
                        ">",
                        astx.Identifier("item"),
                        astx.LiteralInt32(1),
                    )
                ],
            )
        ],
    )
    list_type = astx.ListType([astx.Int32()])
    return _main_module(
        astx.VariableDeclaration(
            "values",
            list_type,
            mutability=astx.MutabilityKind.mutable,
            value=comprehension,
        ),
        astx.FunctionReturn(
            astx.Cast(astx.ListLength(astx.Identifier("values")), astx.Int32())
        ),
    )


def _dynamic_for_in_module() -> astx.Module:
    """
    title: Build one module that iterates a runtime list variable.
    returns:
      type: astx.Module
    """
    list_type = astx.ListType([astx.Int32()])
    loop_body = _block_of(
        astx.VariableAssignment(
            "total",
            astx.BinaryOp(
                "+",
                astx.Identifier("total"),
                astx.Identifier("item"),
            ),
        )
    )
    return _main_module(
        astx.VariableDeclaration(
            "values",
            list_type,
            mutability=astx.MutabilityKind.mutable,
            value=astx.ListCreate(astx.Int32()),
        ),
        astx.ListAppend(astx.Identifier("values"), astx.LiteralInt32(4)),
        astx.ListAppend(astx.Identifier("values"), astx.LiteralInt32(5)),
        astx.VariableDeclaration(
            "total",
            astx.Int32(),
            mutability=astx.MutabilityKind.mutable,
            value=astx.LiteralInt32(0),
        ),
        astx.ForInLoopStmt(
            astx.Identifier("item"),
            astx.Identifier("values"),
            loop_body,
        ),
        astx.FunctionReturn(astx.Identifier("total")),
    )


def _nested_comprehension_module() -> astx.Module:
    """
    title: Build one module with two comprehension clauses.
    returns:
      type: astx.Module
    """
    comprehension = astx.ListComprehension(
        element=astx.BinaryOp(
            "+",
            astx.Identifier("left"),
            astx.Identifier("right"),
        ),
        generators=[
            astx.ComprehensionClause(
                astx.Identifier("left"),
                _literal_list(1, 2),
            ),
            astx.ComprehensionClause(
                astx.Identifier("right"),
                _literal_list(10, 20, 30),
                [
                    astx.BinaryOp(
                        ">",
                        astx.Identifier("right"),
                        astx.BinaryOp(
                            "*",
                            astx.Identifier("left"),
                            astx.LiteralInt32(10),
                        ),
                    )
                ],
            ),
        ],
    )
    list_type = astx.ListType([astx.Int32()])
    result_sum = astx.BinaryOp(
        "+",
        astx.ListIndex(astx.Identifier("values"), astx.LiteralInt32(0)),
        astx.BinaryOp(
            "+",
            astx.ListIndex(astx.Identifier("values"), astx.LiteralInt32(1)),
            astx.BinaryOp(
                "+",
                astx.ListIndex(
                    astx.Identifier("values"),
                    astx.LiteralInt32(2),
                ),
                astx.Cast(
                    astx.ListLength(astx.Identifier("values")), astx.Int32()
                ),
            ),
        ),
    )
    return _main_module(
        astx.VariableDeclaration(
            "values",
            list_type,
            mutability=astx.MutabilityKind.mutable,
            value=comprehension,
        ),
        astx.FunctionReturn(result_sum),
    )


def test_for_in_resolves_list_iteration() -> None:
    """
    title: For-in analysis should attach list iteration metadata.
    """
    module = _sum_for_in_module()
    loop = module.nodes[0].body.nodes[1]

    analyze(module)

    iteration = loop.semantic.resolved_iteration
    target_symbol = loop.target.semantic.resolved_symbol
    assert iteration is not None
    assert target_symbol is not None
    assert iteration.kind is IterationKind.LIST
    assert isinstance(iteration.element_type, astx.Int32)
    assert iteration.target_symbol == target_symbol


@pytest.mark.parametrize(
    "source_kind, assignment_kind",
    [
        ("identifier", "binary"),
        ("identifier", "variable"),
        ("assignment", "binary"),
        ("cast", "binary"),
    ],
)
def test_for_in_rejects_owner_replacement(
    source_kind: Literal["identifier", "assignment", "cast"],
    assignment_kind: Literal["binary", "variable"],
) -> None:
    """
    title: All supported owner-backed iterable forms protect their binding.
    parameters:
      source_kind:
        type: Literal[identifier, assignment, cast]
      assignment_kind:
        type: Literal[binary, variable]
    """
    source: astx.Expr = astx.Identifier("values")
    if source_kind == "assignment":
        source = astx.BinaryOp("=", source, astx.ListCreate(astx.Int32()))
    elif source_kind == "cast":
        source = astx.Cast(source, _list_i32_type())
    replacement = (
        astx.BinaryOp(
            "=", astx.Identifier("values"), astx.ListCreate(astx.Int32())
        )
        if assignment_kind == "binary"
        else astx.VariableAssignment("values", astx.ListCreate(astx.Int32()))
    )
    replacement.loc = SourceLocation(8, 5)
    module = _main_module(
        _mutable_decl(
            "values", _list_i32_type(), astx.ListCreate(astx.Int32())
        ),
        astx.ForInLoopStmt(
            astx.Identifier("item"), source, _block_of(replacement)
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    with pytest.raises(SemanticError) as error:
        analyze(module)

    diagnostics = error.value.diagnostics.diagnostics
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP
    assert "cannot replace list 'values' while it is being iterated" in (
        diagnostic.message
    )
    assert "after the loop or use a different binding" in diagnostic.message
    location = diagnostic.resolved_source()
    assert location is not None
    assert (location.line, location.col) == (8, 5)
    assert replacement.semantic.resource_ownership is None


@pytest.mark.parametrize(
    "region", ["branch", "try", "except", "else", "finally"]
)
def test_for_in_protects_owner_in_nested_regions(region: str) -> None:
    """
    title: List iteration borrows span branches and all exception clauses.
    parameters:
      region:
        type: str
    """
    replacement = astx.VariableAssignment(
        "values", astx.ListCreate(astx.Int32())
    )
    body = _block_of(replacement, astx.FunctionReturn(astx.LiteralInt32(0)))
    nested: astx.AST
    if region == "branch":
        nested = astx.IfStmt(astx.LiteralBoolean(False), body)
    else:
        nested = astx.ExceptionHandlerStmt(
            body if region == "try" else _block_of(astx.LiteralInt32(0)),
            [
                astx.CatchHandlerStmt(
                    body if region == "except" else _block_of(),
                    types=[astx.Identifier("ValueError")],
                )
            ],
            astx.FinallyHandlerStmt(
                body if region == "finally" else _block_of()
            ),
            else_body=body if region == "else" else None,
        )
    module = _main_module(
        _mutable_decl(
            "values", _list_i32_type(), astx.ListCreate(astx.Int32())
        ),
        astx.ForInLoopStmt(
            astx.Identifier("item"),
            astx.Identifier("values"),
            _block_of(nested),
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    with pytest.raises(SemanticError, match="while it is being iterated"):
        analyze(module)


def test_nested_iteration_retains_outer_owner_borrow() -> None:
    """
    title: Exiting an inner loop must not release the same outer owner borrow.
    """
    module = _main_module(
        _mutable_decl(
            "values", _list_i32_type(), astx.ListCreate(astx.Int32())
        ),
        astx.ForInLoopStmt(
            astx.Identifier("outer"),
            astx.Identifier("values"),
            _block_of(
                astx.ForInLoopStmt(
                    astx.Identifier("inner"),
                    astx.Identifier("values"),
                    _block_of(),
                ),
                astx.VariableAssignment(
                    "values", astx.ListCreate(astx.Int32())
                ),
            ),
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    with pytest.raises(SemanticError, match="while it is being iterated"):
        analyze(module)


@pytest.mark.parametrize("position", ["filter", "dependent", "element"])
def test_comprehension_protects_iteration_owner(position: str) -> None:
    """
    title: Comprehension borrows span filters, dependent sources, and results.
    parameters:
      position:
        type: str
    """
    replacement = astx.BinaryOp(
        "=", astx.Identifier("values"), astx.ListCreate(astx.Int32())
    )
    filters = (
        [
            astx.BinaryOp(
                "==", astx.ListLength(replacement), astx.LiteralInt64(0)
            )
        ]
        if position == "filter"
        else []
    )
    clauses = [
        astx.ComprehensionClause(
            astx.Identifier("item"), astx.Identifier("values"), filters
        )
    ]
    if position == "dependent":
        clauses.append(
            astx.ComprehensionClause(astx.Identifier("other"), replacement)
        )
    element = (
        astx.ListLength(replacement)
        if position == "element"
        else astx.LiteralInt64(0)
    )
    module = _main_module(
        _mutable_decl(
            "values", _list_i32_type(), astx.ListCreate(astx.Int32())
        ),
        astx.ListComprehension(element, clauses),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    with pytest.raises(SemanticError, match="while it is being iterated"):
        analyze(module)


def test_iteration_owners_resolve_before_same_name_targets() -> None:
    """
    title: Shadowed targets do not hide the source owner or leak its borrow.
    """
    declaration = _mutable_decl(
        "values", _list_i32_type(), astx.ListCreate(astx.Int32())
    )
    loop = astx.ForInLoopStmt(
        astx.Identifier("values"), astx.Identifier("values"), _block_of()
    )
    clause = astx.ComprehensionClause(
        astx.Identifier("values"), astx.Identifier("values")
    )
    module = _main_module(
        declaration,
        loop,
        astx.VariableAssignment("values", astx.ListCreate(astx.Int32())),
        astx.ListComprehension(astx.Identifier("values"), [clause]),
        astx.VariableAssignment("values", astx.ListCreate(astx.Int32())),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    analyze(module)
    owner_id = declaration.semantic.resolved_symbol.symbol_id
    for node in (loop, clause):
        iteration = node.semantic.resolved_iteration
        assert iteration.borrowed_owner_symbol_id == owner_id
        assert iteration.target_symbol.symbol_id != owner_id


def test_for_in_returned_owner_cleans_on_exception(tmp_path: Path) -> None:
    """
    title: Move an iterated owner and clean it on exceptional iteration exit.
    parameters:
      tmp_path:
        type: Path
    """
    make = astx.FunctionDef(
        astx.FunctionPrototype("make", astx.Arguments(), _list_i32_type()),
        _block_of(
            _mutable_decl(
                "values",
                _list_i32_type(),
                astx.ListExpr([astx.LiteralInt32(1)]),
            ),
            astx.ForInLoopStmt(
                astx.Identifier("item"),
                astx.Identifier("values"),
                _block_of(astx.FunctionReturn(astx.Identifier("values"))),
            ),
            astx.FunctionReturn(astx.Identifier("values")),
        ),
    )
    module = _main_module(
        astx.ExceptionHandlerStmt(
            _block_of(
                astx.ForInLoopStmt(
                    astx.Identifier("item"),
                    astx.FunctionCall("make", []),
                    _block_of(
                        astx.ThrowStmt(
                            astx.ClassConstruct(
                                "ValueError", (astx.LiteralString("leave"),)
                            )
                        )
                    ),
                )
            ),
            [
                astx.CatchHandlerStmt(
                    _block_of(), types=[astx.Identifier("ValueError")]
                )
            ],
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    module.block.append(make)
    assert_executed_list_cleanups(module, tmp_path, expected=1)


def test_for_in_rejects_non_iterable() -> None:
    """
    title: For-in analysis should reject scalar iterables.
    """
    module = _main_module(
        astx.ForInLoopStmt(
            astx.Identifier("item"),
            astx.LiteralInt32(1),
            astx.Block(),
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    with pytest.raises(SemanticError, match="for-in requires an iterable"):
        analyze(module)


def test_for_in_target_does_not_leak() -> None:
    """
    title: For-in targets should stay scoped to the loop body.
    """
    module = _main_module(
        astx.ForInLoopStmt(
            astx.Identifier("item"),
            _literal_list(1),
            astx.Block(),
        ),
        astx.FunctionReturn(astx.Identifier("item")),
    )

    with pytest.raises(SemanticError, match="cannot resolve name 'item'"):
        analyze(module)


def test_list_comprehension_resolves_iteration_and_result_type() -> None:
    """
    title: List comprehensions should resolve clause and result types.
    """
    module = _filtered_comprehension_module()
    declaration = module.nodes[0].body.nodes[0]
    comprehension = declaration.value

    analyze(module)

    clause = comprehension.generators.nodes[0]
    assert clause.semantic.resolved_iteration is not None
    assert clause.semantic.resolved_iteration.kind is IterationKind.LIST
    assert isinstance(comprehension.semantic.resolved_type, astx.ListType)


def test_comprehension_filter_requires_boolean() -> None:
    """
    title: Comprehension filters should be Boolean expressions.
    """
    comprehension = astx.ListComprehension(
        element=astx.Identifier("item"),
        generators=[
            astx.ComprehensionClause(
                astx.Identifier("item"),
                _literal_list(1),
                [astx.LiteralInt32(1)],
            )
        ],
    )

    with pytest.raises(SemanticError, match="filter must be Boolean"):
        analyze(comprehension)


def test_set_and_dict_comprehensions_analyze_iterables() -> None:
    """
    title: Set and dict comprehensions should resolve semantic result types.
    """
    set_comprehension = astx.SetComprehension(
        element=astx.Identifier("item"),
        generators=[
            astx.ComprehensionClause(
                astx.Identifier("item"),
                astx.LiteralSet({astx.LiteralInt32(1), astx.LiteralInt32(2)}),
            )
        ],
    )
    dict_comprehension = astx.DictComprehension(
        key=astx.Identifier("key"),
        value=astx.Identifier("key"),
        generators=[
            astx.ComprehensionClause(
                astx.Identifier("key"),
                astx.LiteralDict({astx.LiteralInt32(1): astx.LiteralInt32(2)}),
            )
        ],
    )

    analyze(set_comprehension)
    analyze(dict_comprehension)

    set_semantic = getattr(set_comprehension, "semantic")
    dict_semantic = getattr(dict_comprehension, "semantic")
    assert isinstance(set_semantic.resolved_type, astx.SetType)
    assert isinstance(dict_semantic.resolved_type, astx.DictType)


def test_for_in_lowers_to_list_iteration_blocks() -> None:
    """
    title: For-in over lists should lower to explicit iteration blocks.
    """
    builder = Builder()
    ir_text = builder.translate(_sum_for_in_module())

    assert "for.in.cond" in ir_text
    assert "for.in.advance" in ir_text
    assert 'call i32 @"irx_list_at"' in ir_text
    assert_ir_parses(ir_text)


def test_dynamic_list_for_in_lowers() -> None:
    """
    title: For-in over runtime list variables should lower via list length.
    """
    builder = Builder()
    ir_text = builder.translate(_dynamic_for_in_module())

    assert "irx_list_iter_length_i64" in ir_text
    assert "for.in.cond" in ir_text
    assert 'call i32 @"irx_list_at"' in ir_text
    assert_ir_parses(ir_text)


@pytest.mark.skipif(
    not HAS_CLANG,
    reason="clang is required for runtime tests",
)
def test_for_in_list_builds_and_runs() -> None:
    """
    title: For-in over a list should execute with the list runtime.
    """
    expected_sum = 6
    assert_build_output(Builder(), _sum_for_in_module(), str(expected_sum))


@pytest.mark.skipif(
    not HAS_CLANG,
    reason="clang is required for runtime tests",
)
def test_dynamic_list_for_in_builds_and_runs() -> None:
    """
    title: For-in over runtime list variables should execute.
    """
    expected_sum = 9
    assert_build_output(
        Builder(),
        _dynamic_for_in_module(),
        str(expected_sum),
    )


def test_list_comprehension_lowers_to_dynamic_list_append() -> None:
    """
    title: List comprehensions should lower through dynamic list append.
    """
    builder = Builder()
    ir_text = builder.translate(_filtered_comprehension_module())

    assert "list.comp.0.cond" in ir_text
    assert 'call i32 @"irx_list_append"' in ir_text
    assert 'call i8* @"irx_list_status_message"' in ir_text
    assert 'call void @"irx_list_destroy"' in ir_text
    assert_ir_parses(ir_text)


def test_nested_list_comprehension_lowers() -> None:
    """
    title: Nested list comprehensions should lower nested clause blocks.
    """
    builder = Builder()
    ir_text = builder.translate(_nested_comprehension_module())

    assert "list.comp.0.cond" in ir_text
    assert "list.comp.1.cond" in ir_text
    assert "list.comp.1.filter.0.pass" in ir_text
    assert_ir_parses(ir_text)


@pytest.mark.skipif(
    not HAS_CLANG,
    reason="clang is required for runtime tests",
)
def test_list_comprehension_builds_and_runs() -> None:
    """
    title: Filtered list comprehension should build and execute.
    """
    expected_length = 2
    assert_build_output(
        Builder(),
        _filtered_comprehension_module(),
        str(expected_length),
    )


@pytest.mark.skipif(
    not HAS_CLANG,
    reason="clang is required for runtime tests",
)
def test_nested_list_comprehension_builds_and_runs() -> None:
    """
    title: Nested list comprehensions should preserve loop order.
    """
    expected_first = 21
    expected_second = 31
    expected_third = 32
    expected_length = 3
    expected_result = (
        expected_first + expected_second + expected_third + expected_length
    )
    assert_build_output(
        Builder(),
        _nested_comprehension_module(),
        str(expected_result),
    )


def test_set_comprehension_lowering_is_guarded() -> None:
    """
    title: Set comprehension lowering should report the runtime gap clearly.
    """
    module = _main_module(
        astx.SetComprehension(
            element=astx.Identifier("item"),
            generators=[
                astx.ComprehensionClause(
                    astx.Identifier("item"),
                    astx.LiteralSet({astx.LiteralInt32(1)}),
                )
            ],
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )

    with pytest.raises(LoweringError, match="dynamic set runtime"):
        Builder().translate(module)


def test_string_iteration_cleans_continue_and_break() -> None:
    """
    title: Iteration clones release once on both continue and break edges.
    """
    continued = astx.Block()
    continued.append(astx.ContinueStmt())
    loop = astx.Block()
    loop.append(
        astx.IfStmt(
            astx.BinaryOp(
                "==", astx.Identifier("word"), astx.LiteralString("skip")
            ),
            continued,
        )
    )
    loop.append(astx.BreakStmt())
    module = _main_module(
        astx.ForInLoopStmt(
            astx.Identifier("word"),
            astx.ListExpr(
                [astx.LiteralString("skip"), astx.LiteralString("stop")]
            ),
            loop,
        ),
        astx.FunctionReturn(astx.LiteralInt32(0)),
    )
    assert_executed_string_frees(module, expected=2)
