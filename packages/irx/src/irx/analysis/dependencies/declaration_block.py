"""
title: Explicit DeclarationBlock semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    RequireValueExpressionCallback,
    ResolveDeclaredTypeCallback,
    VisitModuleCallback,
)
from irx.analysis.registry import SemanticRegistry
from irx.analysis.resolved_nodes import (
    ResourceOwnership,
    SemanticInfo,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class DeclarationBlockAnalysisServices:
    """
    title: Explicit dependencies for DeclarationBlockAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      predeclare_block_structs:
        type: Callable[[astx.Block], None]
      require_value_expression:
        type: RequireValueExpressionCallback
      resolve_declared_type:
        type: ResolveDeclaredTypeCallback
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      visit_module:
        type: VisitModuleCallback
      context:
        type: SemanticContext
      registry:
        type: SemanticRegistry
      visit:
        type: Callable[[astx.AST], None]
      free_resolve_nullable_global:
        type: >-
          Callable[[astx.VariableDeclaration | astx.InlineVariableDeclaration],
          None]
      free_arrow_local:
        type: >-
          Callable[[astx.VariableDeclaration | astx.InlineVariableDeclaration,
          SemanticSymbol], None]
      free_class_local:
        type: >-
          Callable[[astx.VariableDeclaration | astx.InlineVariableDeclaration,
          SemanticSymbol], None]
      free_resolve_file_local:
        type: >-
          Callable[[astx.VariableDeclaration | astx.InlineVariableDeclaration,
          SemanticSymbol], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    predeclare_block_structs: Callable[[astx.Block], None]
    require_value_expression: RequireValueExpressionCallback
    resolve_declared_type: ResolveDeclaredTypeCallback
    semantic: Callable[[astx.AST], SemanticInfo]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    visit_module: VisitModuleCallback
    context: SemanticContext
    registry: SemanticRegistry
    visit: Callable[[astx.AST], None]
    free_resolve_nullable_global: Callable[
        [astx.VariableDeclaration | astx.InlineVariableDeclaration], None
    ]
    free_arrow_local: Callable[
        [
            astx.VariableDeclaration | astx.InlineVariableDeclaration,
            SemanticSymbol,
        ],
        None,
    ]
    free_class_local: Callable[
        [
            astx.VariableDeclaration | astx.InlineVariableDeclaration,
            SemanticSymbol,
        ],
        None,
    ]
    free_resolve_file_local: Callable[
        [
            astx.VariableDeclaration | astx.InlineVariableDeclaration,
            SemanticSymbol,
        ],
        None,
    ]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        predeclare_block_structs: Callable[[astx.Block], None],
        require_value_expression: RequireValueExpressionCallback,
        resolve_declared_type: ResolveDeclaredTypeCallback,
        semantic: Callable[[astx.AST], SemanticInfo],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        visit_module: VisitModuleCallback,
        context: SemanticContext,
        registry: SemanticRegistry,
        visit: Callable[[astx.AST], None],
        free_resolve_nullable_global: Callable[
            [astx.VariableDeclaration | astx.InlineVariableDeclaration], None
        ],
        free_arrow_local: Callable[
            [
                astx.VariableDeclaration | astx.InlineVariableDeclaration,
                SemanticSymbol,
            ],
            None,
        ],
        free_class_local: Callable[
            [
                astx.VariableDeclaration | astx.InlineVariableDeclaration,
                SemanticSymbol,
            ],
            None,
        ],
        free_resolve_file_local: Callable[
            [
                astx.VariableDeclaration | astx.InlineVariableDeclaration,
                SemanticSymbol,
            ],
            None,
        ],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          predeclare_block_structs:
            type: Callable[[astx.Block], None]
          require_value_expression:
            type: RequireValueExpressionCallback
          resolve_declared_type:
            type: ResolveDeclaredTypeCallback
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
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
          visit_module:
            type: VisitModuleCallback
          context:
            type: SemanticContext
          registry:
            type: SemanticRegistry
          visit:
            type: Callable[[astx.AST], None]
          free_resolve_nullable_global:
            type: >-
              Callable[[astx.VariableDeclaration |
              astx.InlineVariableDeclaration], None]
          free_arrow_local:
            type: >-
              Callable[[astx.VariableDeclaration |
              astx.InlineVariableDeclaration, SemanticSymbol], None]
          free_class_local:
            type: >-
              Callable[[astx.VariableDeclaration |
              astx.InlineVariableDeclaration, SemanticSymbol], None]
          free_resolve_file_local:
            type: >-
              Callable[[astx.VariableDeclaration |
              astx.InlineVariableDeclaration, SemanticSymbol], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self, "predeclare_block_structs", predeclare_block_structs
        )
        object.__setattr__(
            self, "require_value_expression", require_value_expression
        )
        object.__setattr__(
            self, "resolve_declared_type", resolve_declared_type
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "visit_module", visit_module)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "registry", registry)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self, "free_resolve_nullable_global", free_resolve_nullable_global
        )
        object.__setattr__(self, "free_arrow_local", free_arrow_local)
        object.__setattr__(self, "free_class_local", free_class_local)
        object.__setattr__(
            self, "free_resolve_file_local", free_resolve_file_local
        )
