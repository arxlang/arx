"""
title: Explicit ExpressionTensorBufferSupport semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.resolved_nodes import (
    SemanticInfo,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionTensorBufferSupportAnalysisServices:
    """
    title: Explicit dependencies for ExpressionTensorBufferSupportAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      context:
        type: SemanticContext
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    semantic: Callable[[astx.AST], SemanticInfo]
    context: SemanticContext

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        semantic: Callable[[astx.AST], SemanticInfo],
        context: SemanticContext,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          context:
            type: SemanticContext
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "context", context)
