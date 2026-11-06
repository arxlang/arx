"""
title: Explicit Exception semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.resolved_nodes import (
    ResourceOwnership,
    SemanticClass,
    SemanticInfo,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExceptionAnalysisServices:
    """
    title: Explicit dependencies for ExceptionAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      resolve_class_definition:
        type: Callable[[SemanticClass], SemanticClass]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_class:
        type: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      bindings:
        type: VisibleBindings
      context:
        type: SemanticContext
      factory:
        type: SemanticEntityFactory
      visit:
        type: Callable[[astx.AST], None]
      free_exception_error:
        type: Callable[[astx.AST, str], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    resolve_class_definition: Callable[[SemanticClass], SemanticClass]
    semantic: Callable[[astx.AST], SemanticInfo]
    set_class: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    bindings: VisibleBindings
    context: SemanticContext
    factory: SemanticEntityFactory
    visit: Callable[[astx.AST], None]
    free_exception_error: Callable[[astx.AST, str], None]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        resolve_class_definition: Callable[[SemanticClass], SemanticClass],
        semantic: Callable[[astx.AST], SemanticInfo],
        set_class: Callable[
            [astx.AST, SemanticClass | None], SemanticClass | None
        ],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        bindings: VisibleBindings,
        context: SemanticContext,
        factory: SemanticEntityFactory,
        visit: Callable[[astx.AST], None],
        free_exception_error: Callable[[astx.AST, str], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          resolve_class_definition:
            type: Callable[[SemanticClass], SemanticClass]
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_class:
            type: >-
              Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
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
          bindings:
            type: VisibleBindings
          context:
            type: SemanticContext
          factory:
            type: SemanticEntityFactory
          visit:
            type: Callable[[astx.AST], None]
          free_exception_error:
            type: Callable[[astx.AST, str], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self, "resolve_class_definition", resolve_class_definition
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_class", set_class)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(self, "free_exception_error", free_exception_error)
