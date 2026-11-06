"""
title: Explicit ExpressionLiteral semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    DeclareIterationTargetCallback,
    RequireValueExpressionCallback,
    ResolveMutationTargetCallback,
)
from irx.analysis.resolved_nodes import (
    ResolvedCollectionMethod,
    ResolvedIteration,
    ResourceOwnership,
    SemanticInfo,
    SemanticSymbol,
    TextOperationKind,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionLiteralAnalysisServices:
    """
    title: Explicit dependencies for ExpressionLiteralAnalysis.
    attributes:
      declare_iteration_target:
        type: DeclareIterationTargetCallback
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      require_value_expression:
        type: RequireValueExpressionCallback
      resolve_mutation_target:
        type: ResolveMutationTargetCallback
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_assignment:
        type: Callable[[astx.AST, SemanticSymbol | None], None]
      set_collection_method:
        type: Callable[[astx.AST, ResolvedCollectionMethod | None], None]
      set_iteration:
        type: >-
          Callable[[astx.AST, ResolvedIteration | None], ResolvedIteration |
          None]
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
      free_resolve_column_index:
        type: Callable[[astx.SubscriptExpr], bool]
      free_text_error:
        type: Callable[[astx.AST, str], None]
      free_set_text_operation:
        type: >-
          Callable[[astx.AST, TextOperationKind, tuple[astx.AST, Ellipsis],
          tuple[int | None, Ellipsis]], None]
      free_resolve_text_subscript:
        type: Callable[[astx.SubscriptExpr], None]
    """

    declare_iteration_target: DeclareIterationTargetCallback
    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    require_value_expression: RequireValueExpressionCallback
    resolve_mutation_target: ResolveMutationTargetCallback
    semantic: Callable[[astx.AST], SemanticInfo]
    set_assignment: Callable[[astx.AST, SemanticSymbol | None], None]
    set_collection_method: Callable[
        [astx.AST, ResolvedCollectionMethod | None], None
    ]
    set_iteration: Callable[
        [astx.AST, ResolvedIteration | None], ResolvedIteration | None
    ]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    context: SemanticContext
    visit: Callable[[astx.AST], None]
    free_resolve_column_index: Callable[[astx.SubscriptExpr], bool]
    free_text_error: Callable[[astx.AST, str], None]
    free_set_text_operation: Callable[
        [
            astx.AST,
            TextOperationKind,
            tuple[astx.AST, ...],
            tuple[int | None, ...],
        ],
        None,
    ]
    free_resolve_text_subscript: Callable[[astx.SubscriptExpr], None]

    def __init__(
        self,
        declare_iteration_target: DeclareIterationTargetCallback,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        require_value_expression: RequireValueExpressionCallback,
        resolve_mutation_target: ResolveMutationTargetCallback,
        semantic: Callable[[astx.AST], SemanticInfo],
        set_assignment: Callable[[astx.AST, SemanticSymbol | None], None],
        set_collection_method: Callable[
            [astx.AST, ResolvedCollectionMethod | None], None
        ],
        set_iteration: Callable[
            [astx.AST, ResolvedIteration | None], ResolvedIteration | None
        ],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        context: SemanticContext,
        visit: Callable[[astx.AST], None],
        free_resolve_column_index: Callable[[astx.SubscriptExpr], bool],
        free_text_error: Callable[[astx.AST, str], None],
        free_set_text_operation: Callable[
            [
                astx.AST,
                TextOperationKind,
                tuple[astx.AST, ...],
                tuple[int | None, ...],
            ],
            None,
        ],
        free_resolve_text_subscript: Callable[[astx.SubscriptExpr], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          declare_iteration_target:
            type: DeclareIterationTargetCallback
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          require_value_expression:
            type: RequireValueExpressionCallback
          resolve_mutation_target:
            type: ResolveMutationTargetCallback
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_assignment:
            type: Callable[[astx.AST, SemanticSymbol | None], None]
          set_collection_method:
            type: Callable[[astx.AST, ResolvedCollectionMethod | None], None]
          set_iteration:
            type: >-
              Callable[[astx.AST, ResolvedIteration | None], ResolvedIteration
              | None]
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
          free_resolve_column_index:
            type: Callable[[astx.SubscriptExpr], bool]
          free_text_error:
            type: Callable[[astx.AST, str], None]
          free_set_text_operation:
            type: >-
              Callable[[astx.AST, TextOperationKind, tuple[astx.AST, Ellipsis],
              tuple[int | None, Ellipsis]], None]
          free_resolve_text_subscript:
            type: Callable[[astx.SubscriptExpr], None]
        """
        object.__setattr__(
            self, "declare_iteration_target", declare_iteration_target
        )
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self, "require_value_expression", require_value_expression
        )
        object.__setattr__(
            self, "resolve_mutation_target", resolve_mutation_target
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_assignment", set_assignment)
        object.__setattr__(
            self, "set_collection_method", set_collection_method
        )
        object.__setattr__(self, "set_iteration", set_iteration)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self, "free_resolve_column_index", free_resolve_column_index
        )
        object.__setattr__(self, "free_text_error", free_text_error)
        object.__setattr__(
            self, "free_set_text_operation", free_set_text_operation
        )
        object.__setattr__(
            self, "free_resolve_text_subscript", free_resolve_text_subscript
        )
