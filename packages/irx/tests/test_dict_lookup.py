"""
title: Dict key lookup tests (SubscriptExpr on LiteralDict).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import astx
import pytest

from irx.analysis import SemanticError, analyze
from irx.analysis.extensions.literals import DICTIONARY_LOOKUP
from irx.builder import Builder as LLVMBuilder
from irx.builder import Visitor as LLVMVisitor
from irx.builder.base import Builder
from irx.system import PrintExpr
from llvmlite import ir

from .conftest import check_result

HAS_LITERAL_TIME = hasattr(astx, "LiteralTime")


def _make_int_dict() -> astx.LiteralDict:
    """
    title: Make int dict.
    returns:
      type: astx.LiteralDict
    """
    return astx.LiteralDict(
        elements={
            astx.LiteralInt32(1): astx.LiteralInt32(10),
            astx.LiteralInt32(2): astx.LiteralInt32(20),
        }
    )


def _make_float_dict() -> astx.LiteralDict:
    """
    title: Make float dict.
    returns:
      type: astx.LiteralDict
    """
    return astx.LiteralDict(
        elements={
            astx.LiteralFloat32(1.5): astx.LiteralInt32(10),
            astx.LiteralFloat32(2.5): astx.LiteralInt32(20),
        }
    )


def _make_lookup_module(
    lookup: astx.SubscriptExpr, *setup_nodes: astx.AST
) -> astx.Module:
    """
    title: Make lookup module.
    parameters:
      lookup:
        type: astx.SubscriptExpr
      setup_nodes:
        type: astx.AST
        variadic: positional
    returns:
      type: astx.Module
    """
    module = astx.Module()

    proto = astx.FunctionPrototype(
        name="main", args=astx.Arguments(), return_type=astx.Int32()
    )
    block = astx.Block()
    for setup_node in setup_nodes:
        block.append(setup_node)
    block.append(PrintExpr(lookup))
    block.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    fn = astx.FunctionDef(prototype=proto, body=block)
    module.block.append(fn)

    return module


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_dict_lookup_hit(builder_class: type[Builder]) -> None:
    """
    title: SubscriptExpr constant key returns the correct value.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.SubscriptExpr(
        value=_make_int_dict(), index=astx.LiteralInt32(2)
    )
    visitor.visit(analyze(expr))
    result = visitor.function_state.result_stack.pop()

    assert isinstance(result, ir.Constant)
    EXPECTED_VAL_FOR_KEY_2 = 20
    assert result.constant == EXPECTED_VAL_FOR_KEY_2


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_dict_lookup_miss(builder_class: type[Builder]) -> None:
    """
    title: SubscriptExpr constant key raises KeyError for a missing key.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    visitor = cast(LLVMVisitor, builder.translator)
    visitor.function_state.result_stack.clear()

    expr = astx.SubscriptExpr(
        value=_make_int_dict(), index=astx.LiteralInt32(99)
    )
    with pytest.raises(KeyError, match="not found in dict"):
        visitor.visit(analyze(expr))


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_dict_lookup_build(builder_class: type[Builder]) -> None:
    """
    title: SubscriptExpr constant key compiles and prints the correct value.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()
    lookup = astx.SubscriptExpr(
        value=_make_int_dict(), index=astx.LiteralInt32(1)
    )
    module = _make_lookup_module(lookup)

    check_result("build", builder, module, expected_output="10")


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_dict_lookup_runtime_variable_key(
    builder_class: type[Builder],
) -> None:
    """
    title: >-
      SubscriptExpr variable integer key does runtime lookup and returns the
      correct value.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()

    key_decl = astx.InlineVariableDeclaration(
        name="k",
        type_=astx.Int32(),
        value=astx.LiteralInt32(2),
    )
    lookup = astx.SubscriptExpr(
        value=_make_int_dict(), index=astx.Identifier("k")
    )
    module = _make_lookup_module(lookup, key_decl)

    check_result("build", builder, module, expected_output="20")


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_dict_lookup_runtime_variable_key_miss_exits(
    builder_class: type[Builder],
) -> None:
    """
    title: SubscriptExpr runtime miss lowers to an explicit exit path.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()

    key_decl = astx.InlineVariableDeclaration(
        name="k",
        type_=astx.Int32(),
        value=astx.LiteralInt32(99),
    )
    lookup = astx.SubscriptExpr(
        value=_make_int_dict(), index=astx.Identifier("k")
    )
    module = _make_lookup_module(lookup, key_decl)

    ir_text = builder.translate(module)

    assert 'call void @"exit"(i32 1)' in ir_text
    assert "switch i32" in ir_text


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_dict_lookup_empty_dict_runtime_key_raises_keyerror(
    builder_class: type[Builder],
) -> None:
    """
    title: Empty dict lookup with a runtime key fails during compilation.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()

    key_decl = astx.InlineVariableDeclaration(
        name="k",
        type_=astx.Int32(),
        value=astx.LiteralInt32(1),
    )
    lookup = astx.SubscriptExpr(
        value=astx.LiteralDict(elements={}),
        index=astx.Identifier("k"),
    )
    module = _make_lookup_module(lookup, key_decl)

    with pytest.raises(SemanticError, match="empty dict"):
        builder.translate(module)


@pytest.mark.parametrize(
    "key_literal,index_type,index_literal,comparison_type,instruction",
    [
        (
            astx.LiteralInt32,
            astx.Int16,
            astx.LiteralInt16,
            astx.Int32,
            "sext i16",
        ),
        (
            astx.LiteralInt8,
            astx.UInt8,
            astx.LiteralUInt8,
            astx.Int16,
            "zext i8",
        ),
    ],
    ids=["signed-width", "mixed-signedness"],
)
def test_dict_lookup_runtime_variable_key_mismatched_integer_widths(
    key_literal: Callable[[int], astx.Literal],
    index_type: type[astx.DataType],
    index_literal: Callable[[int], astx.Literal],
    comparison_type: type[astx.DataType],
    instruction: str,
) -> None:
    """
    title: Dictionary comparison consumes resolved widths and signedness.
    parameters:
      key_literal:
        type: Callable[[int], astx.Literal]
      index_type:
        type: type[astx.DataType]
      index_literal:
        type: Callable[[int], astx.Literal]
      comparison_type:
        type: type[astx.DataType]
      instruction:
        type: str
    """
    builder = LLVMBuilder()
    key_decl = astx.InlineVariableDeclaration(
        name="k", type_=index_type(), value=index_literal(2)
    )
    lookup = astx.SubscriptExpr(
        value=astx.LiteralDict(
            elements={
                key_literal(1): astx.LiteralInt32(10),
                key_literal(2): astx.LiteralInt32(20),
            }
        ),
        index=astx.Identifier("k"),
    )
    module = _make_lookup_module(lookup, key_decl)
    ir_text = builder.translate(module)
    plan = lookup.semantic.facts.require(DICTIONARY_LOOKUP)
    assert isinstance(plan.comparison_type, comparison_type)
    assert isinstance(plan.index_conversion.source_type, index_type)
    assert isinstance(plan.key_conversion.target_type, comparison_type)
    assert isinstance(plan.index_conversion.target_type, comparison_type)
    assert plan.key_conversion.numeric is not None
    assert plan.index_conversion.numeric is not None
    assert plan.key_conversion.numeric.implicit
    assert plan.index_conversion.numeric.implicit
    assert instruction in ir_text
    llvm_type = builder.translator.types.llvm_type(plan.comparison_type)
    assert f"switch {llvm_type}" in ir_text


def test_dict_lookup_rejects_incompatible_constant_key_type() -> None:
    """
    title: SubscriptExpr rejects incompatible constant key categories.
    """
    expr = astx.SubscriptExpr(
        value=_make_int_dict(), index=astx.LiteralFloat32(2.0)
    )
    with pytest.raises(SemanticError, match="dict key"):
        analyze(expr)


@pytest.mark.skipif(
    not HAS_LITERAL_TIME, reason="astx.LiteralTime not available"
)
def test_dict_lookup_rejects_unsupported_constant_time_keys() -> None:
    """
    title: SubscriptExpr rejects unsupported non-numeric constant key types.
    """
    expr = astx.SubscriptExpr(
        value=astx.LiteralDict(
            elements={
                astx.LiteralTime("12:34:56"): astx.LiteralInt32(7),
            }
        ),
        index=astx.LiteralTime("12:34:56"),
    )
    with pytest.raises(
        SemanticError,
        match="only integer and floating-point dict keys are supported",
    ):
        analyze(expr)


@pytest.mark.parametrize("builder_class", [LLVMBuilder])
def test_dict_lookup_runtime_float_variable_key(
    builder_class: type[Builder],
) -> None:
    """
    title: SubscriptExpr runtime float key lowers to float comparisons.
    parameters:
      builder_class:
        type: type[Builder]
    """
    builder = builder_class()

    key_decl = astx.InlineVariableDeclaration(
        name="k",
        type_=astx.Float32(),
        value=astx.LiteralFloat32(2.5),
    )
    lookup = astx.SubscriptExpr(
        value=_make_float_dict(), index=astx.Identifier("k")
    )
    module = _make_lookup_module(lookup, key_decl)

    ir_text = builder.translate(module)

    assert "fcmp oeq float" in ir_text
    assert 'call void @"exit"(i32 1)' in ir_text
