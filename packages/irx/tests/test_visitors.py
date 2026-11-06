# mypy: disable-error-code=no-redef

"""
title: Tests for the shared visitor base.
"""

import gc
import weakref

from typing import cast

import astx
import pytest

from astx.base import ReprStruct
from irx.analysis.api import SemanticAnalyzer
from irx.analysis.resolved_nodes import SemanticInfo
from irx.base.visitors import BaseVisitor, BaseVisitorProtocol
from irx.builder import Visitor
from irx.diagnostics import DiagnosticCodes, LoweringError, SemanticError
from irx.typecheck import copy_type, typechecked
from llvmlite import ir
from plum import Dispatcher, Function, dispatch
from public import private
from typeguard import TypeCheckError

from .conftest import make_main_module
from .visitor_mixins import (
    LiteralProbeMixin,
    MixinVisitorCore,
    visit_overloads,
)


@private
@typechecked
class BlockProbeMixin(MixinVisitorCore):
    """
    title: Recurse into overloads contributed by another module.
    """

    @copy_type(MixinVisitorCore.visit)
    @visit_overloads.dispatch
    def visit(self, node: astx.Block) -> None:
        """
        title: Traverse supported block children through shared dispatch.
        parameters:
          node:
            type: astx.Block
        """
        for child in node.nodes:
            self.visit(child)


@private
class LiteralFirstVisitor(LiteralProbeMixin, BlockProbeMixin):
    """
    title: Assemble literal and structural mixins in one order.
    """


@private
class BlockFirstVisitor(BlockProbeMixin, LiteralProbeMixin):
    """
    title: Reverse independent mixins without changing specificity.
    """


class _SpecializedVisitor(BaseVisitor):
    """
    title: Minimal visitor used to validate shared dispatch behavior.
    attributes:
      calls:
        type: list[str]
    """

    calls: list[str]

    def __init__(self) -> None:
        """
        title: Initialize _SpecializedVisitor.
        """
        self.calls = []

    @dispatch
    def visit(self, node: astx.LiteralInt32) -> None:
        """
        title: Visit LiteralInt32 nodes.
        parameters:
          node:
            type: astx.LiteralInt32
        """
        self.calls.append(type(node).__name__)


@private
class UnknownNode(astx.AST):
    """
    title: Unregistered node used to exercise the failing visitor fallback.
    """

    def get_struct(self, simplified: bool = False) -> ReprStruct:
        """
        title: Supply the AST representation contract without a visit handler.
        parameters:
          simplified:
            type: bool
        returns:
          type: ReprStruct
        """
        return {"UnknownNode": {}}


@private
class IntegerSubtype(astx.LiteralInt32):
    """
    title: Nominal subtype without its own visitor registration.
    """


@private
class InheritedVisitor(_SpecializedVisitor):
    """
    title: Add one overload without replacing the inherited integer handler.
    attributes:
      calls:
        type: list[str]
    """

    @dispatch
    # Plum extends the inherited overload set; mypy sees a replacement method.
    def visit(self, node: astx.LiteralString) -> None:  # type: ignore[override]
        """
        title: Record string visits alongside inherited integer visits.
        parameters:
          node:
            type: astx.LiteralString
        """
        self.calls.append(type(node).__name__)


@pytest.mark.parametrize(
    "node", [astx.LiteralInt32(1), astx.Block(), UnknownNode()]
)
def test_base_visitor_raises_not_implemented(node: astx.AST) -> None:
    """
    title: BaseVisitor should raise a consistent error for ASTx nodes.
    parameters:
      node:
        type: astx.AST
    """
    visitor = BaseVisitor()
    name = type(node).__name__
    with pytest.raises(
        NotImplementedError,
        match=rf"BaseVisitor\.visit\({name}\) is not implemented",
    ):
        visitor.visit(node)


def test_specialized_visitor_dispatch_overrides_base_default() -> None:
    """
    title: Specialized visit overloads should win over base defaults.
    """
    visitor = _SpecializedVisitor()

    visitor.visit(astx.LiteralInt32(1))

    assert visitor.calls == ["LiteralInt32"]


def test_inherited_dispatch_preserves_subtypes_and_parent_isolation() -> None:
    """
    title: Child overloads preserve inherited specificity and parent rejection.
    """
    parent = _SpecializedVisitor()
    child = InheritedVisitor()
    for visitor in (child, parent, InheritedVisitor()):
        visitor.visit(IntegerSubtype(1))
        assert visitor.calls == ["IntegerSubtype"]
        with pytest.raises(NotImplementedError, match="UnknownNode"):
            cast(BaseVisitorProtocol, visitor).visit(UnknownNode())
    child.visit(astx.LiteralString("child"))
    assert child.calls == ["IntegerSubtype", "LiteralString"]
    with pytest.raises(NotImplementedError, match="LiteralString"):
        cast(BaseVisitorProtocol, parent).visit(astx.LiteralString("parent"))
    assert parent.calls == ["IntegerSubtype"]


@pytest.mark.parametrize(
    "visitor_class", [LiteralFirstVisitor, BlockFirstVisitor]
)
def test_shared_mixin_dispatch_recurses_without_retaining_instances(
    visitor_class: type[MixinVisitorCore],
) -> None:
    """
    title: Cross-module overloads preserve specificity and instance state.
    parameters:
      visitor_class:
        type: type[MixinVisitorCore]
    """
    inner = astx.Block()
    inner.append(IntegerSubtype(7))
    outer = astx.Block()
    outer.append(inner)
    outer.append(astx.LiteralInt64(8))
    first, second = visitor_class(), visitor_class()

    first.visit(outer)
    assert first.calls == ["int32", "literal"]
    assert second.calls == []
    second.visit(IntegerSubtype(9))
    assert second.calls == ["int32"]
    assert first.calls == ["int32", "literal"]

    reference = weakref.ref(first)
    del first
    gc.collect()
    assert reference() is None


def test_plum_can_warn_about_exact_visit_redefinitions() -> None:
    """
    title: Opt-in redefinition warnings expose import-order overwrites.
    """
    registration = Dispatcher(warn_redefinition=True)

    @registration
    def visit(node: astx.LiteralInt32) -> str:
        """
        title: Supply the original exact signature.
        parameters:
          node:
            type: astx.LiteralInt32
        returns:
          type: str
        """
        del node
        return "original"

    def replacement(node: astx.LiteralInt32) -> str:
        """
        title: Accidentally contribute the same signature again.
        parameters:
          node:
            type: astx.LiteralInt32
        returns:
          type: str
        """
        del node
        return "replacement"

    cast(Function, visit).dispatch(replacement)
    with pytest.warns(Warning):
        assert visit(astx.LiteralInt32(1)) == "replacement"


def test_semantic_analyzer_inherits_shared_visit_contract() -> None:
    """
    title: SemanticAnalyzer should override the shared visitor defaults.
    """
    node = astx.LiteralInt32(1)

    analyzed = SemanticAnalyzer().analyze(node)

    assert analyzed is node
    assert getattr(node, "semantic", None) is not None


def test_analyzers_keep_same_named_declarations_independent() -> None:
    """
    title: Analyzers cannot replace another compilation's function records.
    """
    first, second = SemanticAnalyzer(), SemanticAnalyzer()
    first_module = make_main_module(astx.FunctionReturn(astx.LiteralInt32(0)))
    second_module = make_main_module(astx.FunctionReturn(astx.LiteralInt32(0)))
    first.analyze(first_module)
    second.analyze(second_module)
    first_function = cast(
        SemanticInfo, first_module.nodes[0].semantic
    ).resolved_function
    second_function = cast(
        SemanticInfo, second_module.nodes[0].semantic
    ).resolved_function

    assert first_function is not None and second_function is not None
    assert first_function.symbol_id == second_function.symbol_id
    assert first_function is not second_function
    assert (
        first.context.get_function(
            first_function.module_key, first_function.name
        )
        is first_function
    )
    assert (
        second.context.get_function(
            second_function.module_key, second_function.name
        )
        is second_function
    )


@pytest.mark.parametrize("typed", [False, True])
def test_unknown_nodes_fail_at_the_responsible_phase(typed: bool) -> None:
    """
    title: A type annotation cannot grant unknown syntax compiler support.
    parameters:
      typed:
        type: bool
    """
    node = UnknownNode()
    if typed:
        node.type_ = astx.Int32()
    with pytest.raises(SemanticError) as caught:
        SemanticAnalyzer().analyze(node)
    diagnostic = caught.value.diagnostics.diagnostics[0]
    assert diagnostic.code == DiagnosticCodes.SEMANTIC_UNSUPPORTED_NODE
    assert diagnostic.phase == "semantic"
    assert diagnostic.resolved_source() is None
    visitor = Visitor()
    with pytest.raises(LoweringError) as lowering:
        visitor.visit(node)
    assert (
        lowering.value.diagnostic.code
        == DiagnosticCodes.LOWERING_MISSING_HANDLER
    )
    assert not visitor.result_stack


def test_structural_traversal_and_scalar_subtypes_are_explicit() -> None:
    """
    title: >-
      Supported blocks traverse children while unregistered containers fail.
    """
    scalar = IntegerSubtype(7)
    block = astx.Block()
    block.append(scalar)
    SemanticAnalyzer().analyze(block)
    assert isinstance(scalar.semantic.resolved_type, astx.Int32)
    container: astx.ASTNodes[astx.AST] = astx.ASTNodes()
    container.append(UnknownNode())
    with pytest.raises(SemanticError, match="ASTNodes"):
        SemanticAnalyzer().analyze(container)
    with pytest.raises(TypeCheckError):
        SemanticAnalyzer().analyze("not an AST")  # type: ignore[arg-type]


def test_llvmlite_visitor_inherits_shared_visit_contract() -> None:
    """
    title: LLVM visitor mixins should override the shared visitor defaults.
    """
    visitor, second = Visitor(), Visitor()

    visitor.visit(astx.LiteralInt32(1))

    assert second.result_stack == []
    expected_second = 2
    second.visit(astx.LiteralInt32(expected_second))
    first_value, second_value = (
        visitor.result_stack[-1],
        second.result_stack[-1],
    )
    assert isinstance(first_value, ir.Constant)
    assert isinstance(second_value, ir.Constant)
    assert first_value.constant == 1
    assert second_value.constant == expected_second
