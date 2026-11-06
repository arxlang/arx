"""
title: Explicit ExpressionArray semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionArrayAnalysisServices:
    """
    title: Explicit dependencies for ExpressionArrayAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      context:
        type: SemanticContext
      visit:
        type: Callable[[astx.AST], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    context: SemanticContext
    visit: Callable[[astx.AST], None]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        context: SemanticContext,
        visit: Callable[[astx.AST], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          context:
            type: SemanticContext
          visit:
            type: Callable[[astx.AST], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
