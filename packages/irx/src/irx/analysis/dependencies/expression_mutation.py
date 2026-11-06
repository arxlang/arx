"""
title: Explicit ExpressionMutation semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import RequireValueExpressionCallback
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.resolved_nodes import (
    ResourceOwnership,
    SemanticClass,
    SemanticClassMember,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionMutationAnalysisServices:
    """
    title: Explicit dependencies for ExpressionMutationAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      member_declaring_class:
        type: Callable[[SemanticClassMember], SemanticClass | None]
      member_display_name:
        type: Callable[[SemanticClassMember], str]
      member_owner_module_key:
        type: Callable[[SemanticClassMember], str]
      require_value_expression:
        type: RequireValueExpressionCallback
      root_assignment_symbol:
        type: Callable[[astx.AST | None], SemanticSymbol | None]
      set_assignment:
        type: Callable[[astx.AST, SemanticSymbol | None], None]
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
      factory:
        type: SemanticEntityFactory
      visit:
        type: Callable[[astx.AST], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    member_declaring_class: Callable[
        [SemanticClassMember], SemanticClass | None
    ]
    member_display_name: Callable[[SemanticClassMember], str]
    member_owner_module_key: Callable[[SemanticClassMember], str]
    require_value_expression: RequireValueExpressionCallback
    root_assignment_symbol: Callable[[astx.AST | None], SemanticSymbol | None]
    set_assignment: Callable[[astx.AST, SemanticSymbol | None], None]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    context: SemanticContext
    factory: SemanticEntityFactory
    visit: Callable[[astx.AST], None]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        member_declaring_class: Callable[
            [SemanticClassMember], SemanticClass | None
        ],
        member_display_name: Callable[[SemanticClassMember], str],
        member_owner_module_key: Callable[[SemanticClassMember], str],
        require_value_expression: RequireValueExpressionCallback,
        root_assignment_symbol: Callable[
            [astx.AST | None], SemanticSymbol | None
        ],
        set_assignment: Callable[[astx.AST, SemanticSymbol | None], None],
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
        factory: SemanticEntityFactory,
        visit: Callable[[astx.AST], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          member_declaring_class:
            type: Callable[[SemanticClassMember], SemanticClass | None]
          member_display_name:
            type: Callable[[SemanticClassMember], str]
          member_owner_module_key:
            type: Callable[[SemanticClassMember], str]
          require_value_expression:
            type: RequireValueExpressionCallback
          root_assignment_symbol:
            type: Callable[[astx.AST | None], SemanticSymbol | None]
          set_assignment:
            type: Callable[[astx.AST, SemanticSymbol | None], None]
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
          factory:
            type: SemanticEntityFactory
          visit:
            type: Callable[[astx.AST], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self, "member_declaring_class", member_declaring_class
        )
        object.__setattr__(self, "member_display_name", member_display_name)
        object.__setattr__(
            self, "member_owner_module_key", member_owner_module_key
        )
        object.__setattr__(
            self, "require_value_expression", require_value_expression
        )
        object.__setattr__(
            self, "root_assignment_symbol", root_assignment_symbol
        )
        object.__setattr__(self, "set_assignment", set_assignment)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "visit", visit)
