"""
title: Semantic analyzer orchestration over explicit feature services.
"""

from public import public

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.typecheck import typechecked


@public
@typechecked
class SemanticAnalyzer(SemanticAnalyzerCore):
    """
    title: Analyze through a compiler-local graph and scoped AST dispatcher.
    """
