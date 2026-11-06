# mypy: disable-error-code=no-redef

"""
title: Tests for the shared visitor base.
"""

from pathlib import Path
from typing import cast

import astx
import pytest

from astx.base import ReprStruct
from irx.analysis.api import SemanticAnalyzer
from irx.base.visitors import BaseVisitor, BaseVisitorProtocol
from irx.builder import Builder, Visitor
from irx.diagnostics import DiagnosticCodes, LoweringError, SemanticError
from llvmlite import binding as llvm
from plum import dispatch
from public import private
from typeguard import TypeCheckError


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


def test_semantic_analyzer_inherits_shared_visit_contract() -> None:
    """
    title: SemanticAnalyzer should override the shared visitor defaults.
    """
    node = astx.LiteralInt32(1)

    analyzed = SemanticAnalyzer().analyze(node)

    assert analyzed is node
    assert getattr(node, "semantic", None) is not None


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
    assert not visitor.function_state.result_stack


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
    title: Composed LLVM handlers produce isolated per-compilation values.
    """
    visitor = Visitor()

    visitor.visit(astx.LiteralInt32(1))

    assert visitor.function_state.result_stack[-1].constant == 1
    second = Visitor()
    second_value = 2
    second.visit(astx.LiteralInt32(second_value))
    assert second.function_state.result_stack[-1].constant == second_value
    assert visitor.function_state.result_stack[-1].constant == 1
    assert visitor.features.dispatch is not second.features.dispatch
    assert visitor._llvm.module is not second._llvm.module


def test_llvmlite_backend_avoids_node_specific_private_visit_trampolines() -> (
    None
):
    """
    title: Builder package should keep node lowering in visit overloads.
    """
    package_root = Path(__file__).resolve().parents[1] / "src/irx/builder"

    for path in package_root.rglob("*.py"):
        text = path.read_text()
        assert "def _visit_" not in text


def test_builder_retries_with_fresh_compilation_after_analysis_failure() -> (
    None
):
    """
    title: A failed compilation cannot retain state in a later translation.
    """
    builder = Builder()
    with pytest.raises(SemanticError):
        builder.translate(UnknownNode())
    failed = builder.translator
    expected_value = 3
    module = builder.translate(astx.LiteralInt32(expected_value))
    assert builder.translator is not failed
    actual_value = builder.translator.function_state.result_stack[-1].constant
    assert actual_value == expected_value
    llvm.parse_assembly(module).verify()
