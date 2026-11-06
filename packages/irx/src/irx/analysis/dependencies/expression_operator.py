"""
title: Explicit ExpressionOperator semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    ListAssignmentOwnership,
    RequireValueExpressionCallback,
    ResolveDeclaredTypeCallback,
    ResolveMutationTargetCallback,
    StringAssignmentOwnership,
)
from irx.analysis.resolved_nodes import (
    ResolvedOperator,
    ResourceOwnership,
    SemanticFlags,
    SemanticInfo,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionOperatorAnalysisServices:
    """
    title: Explicit dependencies for ExpressionOperatorAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      require_value_expression:
        type: RequireValueExpressionCallback
      resolve_declared_type:
        type: ResolveDeclaredTypeCallback
      resolve_list_assignment_ownership:
        type: ListAssignmentOwnership
      resolve_mutation_target:
        type: ResolveMutationTargetCallback
      resolve_string_assignment_ownership:
        type: StringAssignmentOwnership
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_assignment:
        type: Callable[[astx.AST, SemanticSymbol | None], None]
      set_flags:
        type: Callable[[astx.AST, SemanticFlags], None]
      set_operator:
        type: Callable[[astx.AST, ResolvedOperator | None], None]
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      context:
        type: SemanticContext
      visit:
        type: Callable[[astx.AST], None]
      free_resolve_column_unary:
        type: Callable[[astx.UnaryOp], bool]
      free_resolve_column_binary:
        type: Callable[[astx.BinaryOp], bool]
      free_resolve_arrow_cast:
        type: Callable[[astx.Cast], bool]
      free_reject_native_file_cast:
        type: Callable[[astx.Cast], bool]
      free_resolve_arrow_store:
        type: Callable[[astx.BinaryOp, SemanticSymbol], bool]
      free_resolve_store:
        type: Callable[[astx.BinaryOp, SemanticSymbol], bool]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    require_value_expression: RequireValueExpressionCallback
    resolve_declared_type: ResolveDeclaredTypeCallback
    resolve_list_assignment_ownership: ListAssignmentOwnership
    resolve_mutation_target: ResolveMutationTargetCallback
    resolve_string_assignment_ownership: StringAssignmentOwnership
    semantic: Callable[[astx.AST], SemanticInfo]
    set_assignment: Callable[[astx.AST, SemanticSymbol | None], None]
    set_flags: Callable[[astx.AST, SemanticFlags], None]
    set_operator: Callable[[astx.AST, ResolvedOperator | None], None]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    context: SemanticContext
    visit: Callable[[astx.AST], None]
    free_resolve_column_unary: Callable[[astx.UnaryOp], bool]
    free_resolve_column_binary: Callable[[astx.BinaryOp], bool]
    free_resolve_arrow_cast: Callable[[astx.Cast], bool]
    free_reject_native_file_cast: Callable[[astx.Cast], bool]
    free_resolve_arrow_store: Callable[[astx.BinaryOp, SemanticSymbol], bool]
    free_resolve_store: Callable[[astx.BinaryOp, SemanticSymbol], bool]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        require_value_expression: RequireValueExpressionCallback,
        resolve_declared_type: ResolveDeclaredTypeCallback,
        resolve_list_assignment_ownership: ListAssignmentOwnership,
        resolve_mutation_target: ResolveMutationTargetCallback,
        resolve_string_assignment_ownership: StringAssignmentOwnership,
        semantic: Callable[[astx.AST], SemanticInfo],
        set_assignment: Callable[[astx.AST, SemanticSymbol | None], None],
        set_flags: Callable[[astx.AST, SemanticFlags], None],
        set_operator: Callable[[astx.AST, ResolvedOperator | None], None],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        context: SemanticContext,
        visit: Callable[[astx.AST], None],
        free_resolve_column_unary: Callable[[astx.UnaryOp], bool],
        free_resolve_column_binary: Callable[[astx.BinaryOp], bool],
        free_resolve_arrow_cast: Callable[[astx.Cast], bool],
        free_reject_native_file_cast: Callable[[astx.Cast], bool],
        free_resolve_arrow_store: Callable[
            [astx.BinaryOp, SemanticSymbol], bool
        ],
        free_resolve_store: Callable[[astx.BinaryOp, SemanticSymbol], bool],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          require_value_expression:
            type: RequireValueExpressionCallback
          resolve_declared_type:
            type: ResolveDeclaredTypeCallback
          resolve_list_assignment_ownership:
            type: ListAssignmentOwnership
          resolve_mutation_target:
            type: ResolveMutationTargetCallback
          resolve_string_assignment_ownership:
            type: StringAssignmentOwnership
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_assignment:
            type: Callable[[astx.AST, SemanticSymbol | None], None]
          set_flags:
            type: Callable[[astx.AST, SemanticFlags], None]
          set_operator:
            type: Callable[[astx.AST, ResolvedOperator | None], None]
          set_resource_ownership:
            type: >-
              Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership
              | None]
          set_symbol:
            type: >-
              Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol |
              None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          context:
            type: SemanticContext
          visit:
            type: Callable[[astx.AST], None]
          free_resolve_column_unary:
            type: Callable[[astx.UnaryOp], bool]
          free_resolve_column_binary:
            type: Callable[[astx.BinaryOp], bool]
          free_resolve_arrow_cast:
            type: Callable[[astx.Cast], bool]
          free_reject_native_file_cast:
            type: Callable[[astx.Cast], bool]
          free_resolve_arrow_store:
            type: Callable[[astx.BinaryOp, SemanticSymbol], bool]
          free_resolve_store:
            type: Callable[[astx.BinaryOp, SemanticSymbol], bool]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self, "require_value_expression", require_value_expression
        )
        object.__setattr__(
            self, "resolve_declared_type", resolve_declared_type
        )
        object.__setattr__(
            self,
            "resolve_list_assignment_ownership",
            resolve_list_assignment_ownership,
        )
        object.__setattr__(
            self, "resolve_mutation_target", resolve_mutation_target
        )
        object.__setattr__(
            self,
            "resolve_string_assignment_ownership",
            resolve_string_assignment_ownership,
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_assignment", set_assignment)
        object.__setattr__(self, "set_flags", set_flags)
        object.__setattr__(self, "set_operator", set_operator)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self, "free_resolve_column_unary", free_resolve_column_unary
        )
        object.__setattr__(
            self, "free_resolve_column_binary", free_resolve_column_binary
        )
        object.__setattr__(
            self, "free_resolve_arrow_cast", free_resolve_arrow_cast
        )
        object.__setattr__(
            self, "free_reject_native_file_cast", free_reject_native_file_cast
        )
        object.__setattr__(
            self, "free_resolve_arrow_store", free_resolve_arrow_store
        )
        object.__setattr__(self, "free_resolve_store", free_resolve_store)
