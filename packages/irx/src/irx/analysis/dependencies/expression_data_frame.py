"""
title: Explicit ExpressionDataFrame semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.resolved_nodes import (
    ResourceOwnership,
    SemanticInfo,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionDataFrameAnalysisServices:
    """
    title: Explicit dependencies for ExpressionDataFrameAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      context:
        type: SemanticContext
      visit:
        type: Callable[[astx.AST], None]
      free_set_operation:
        type: >-
          Callable[[astx.AST, str, astx.DataType | None, astx.DataType], None]
      free_resolve_series_reduction:
        type: Callable[[astx.SeriesReduction], None]
      free_nullable_error:
        type: Callable[[astx.AST, str], None]
      free_lifecycle_error:
        type: Callable[[astx.AST, str], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    semantic: Callable[[astx.AST], SemanticInfo]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    context: SemanticContext
    visit: Callable[[astx.AST], None]
    free_set_operation: Callable[
        [astx.AST, str, astx.DataType | None, astx.DataType], None
    ]
    free_resolve_series_reduction: Callable[[astx.SeriesReduction], None]
    free_nullable_error: Callable[[astx.AST, str], None]
    free_lifecycle_error: Callable[[astx.AST, str], None]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        semantic: Callable[[astx.AST], SemanticInfo],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        context: SemanticContext,
        visit: Callable[[astx.AST], None],
        free_set_operation: Callable[
            [astx.AST, str, astx.DataType | None, astx.DataType], None
        ],
        free_resolve_series_reduction: Callable[[astx.SeriesReduction], None],
        free_nullable_error: Callable[[astx.AST, str], None],
        free_lifecycle_error: Callable[[astx.AST, str], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_resource_ownership:
            type: >-
              Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership
              | None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          context:
            type: SemanticContext
          visit:
            type: Callable[[astx.AST], None]
          free_set_operation:
            type: >-
              Callable[[astx.AST, str, astx.DataType | None, astx.DataType],
              None]
          free_resolve_series_reduction:
            type: Callable[[astx.SeriesReduction], None]
          free_nullable_error:
            type: Callable[[astx.AST, str], None]
          free_lifecycle_error:
            type: Callable[[astx.AST, str], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(self, "free_set_operation", free_set_operation)
        object.__setattr__(
            self,
            "free_resolve_series_reduction",
            free_resolve_series_reduction,
        )
        object.__setattr__(self, "free_nullable_error", free_nullable_error)
        object.__setattr__(self, "free_lifecycle_error", free_lifecycle_error)
