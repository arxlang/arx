"""
title: Semantic analyzer orchestration.
summary: >-
  Compose the specialized semantic visitor mixins around a shared analyzer core
  so traversal, registration, bindings, and rule logic live in smaller modules.
"""

from __future__ import annotations

from public import public

from irx.analysis.handlers.array_values import ArrayValueVisitorMixin
from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.handlers.control_flow import ControlFlowVisitorMixin
from irx.analysis.handlers.declarations import DeclarationVisitorMixin
from irx.analysis.handlers.descriptors import DescriptorVisitorMixin
from irx.analysis.handlers.expressions import ExpressionVisitorMixin
from irx.analysis.handlers.imports import ImportVisitorMixin
from irx.analysis.handlers.nullable import NullableVisitorMixin
from irx.analysis.handlers.scalar_values import ScalarValueVisitorMixin
from irx.analysis.handlers.tabular import TabularVisitorMixin
from irx.analysis.handlers.templates import TemplateVisitorMixin
from irx.typecheck import typechecked


@public
@typechecked
class SemanticAnalyzer(
    ArrayValueVisitorMixin,
    ScalarValueVisitorMixin,
    TabularVisitorMixin,
    NullableVisitorMixin,
    DescriptorVisitorMixin,
    ImportVisitorMixin,
    TemplateVisitorMixin,
    DeclarationVisitorMixin,
    ExpressionVisitorMixin,
    ControlFlowVisitorMixin,
    SemanticAnalyzerCore,
):
    """
    title: Concrete semantic analyzer.
    summary: >-
      Walk AST nodes, attach semantic sidecars, and delegate reusable policy to
      the extracted factories, registries, and binding tables.
    """
