"""
title: Explicit DeclarationClassMethod semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.registry import SemanticRegistry
from irx.analysis.resolved_nodes import (
    SemanticFunction,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class DeclarationClassMethodAnalysisServices:
    """
    title: Explicit dependencies for DeclarationClassMethodAnalysis.
    attributes:
      analyze_function_template_specializations:
        type: Callable[[SemanticFunction], None]
      analyze_parameter_defaults:
        type: Callable[[SemanticFunction], None]
      guarantees_return:
        type: Callable[[astx.AST], bool]
      prepare_function_template_specializations:
        type: Callable[[SemanticFunction], None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      context:
        type: SemanticContext
      factory:
        type: SemanticEntityFactory
      registry:
        type: SemanticRegistry
      visit:
        type: Callable[[astx.AST], None]
      free_resolve_parameter_ownership:
        type: Callable[[astx.Argument, SemanticSymbol], None]
    """

    analyze_function_template_specializations: Callable[
        [SemanticFunction], None
    ]
    analyze_parameter_defaults: Callable[[SemanticFunction], None]
    guarantees_return: Callable[[astx.AST], bool]
    prepare_function_template_specializations: Callable[
        [SemanticFunction], None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    context: SemanticContext
    factory: SemanticEntityFactory
    registry: SemanticRegistry
    visit: Callable[[astx.AST], None]
    free_resolve_parameter_ownership: Callable[
        [astx.Argument, SemanticSymbol], None
    ]

    def __init__(
        self,
        analyze_function_template_specializations: Callable[
            [SemanticFunction], None
        ],
        analyze_parameter_defaults: Callable[[SemanticFunction], None],
        guarantees_return: Callable[[astx.AST], bool],
        prepare_function_template_specializations: Callable[
            [SemanticFunction], None
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        context: SemanticContext,
        factory: SemanticEntityFactory,
        registry: SemanticRegistry,
        visit: Callable[[astx.AST], None],
        free_resolve_parameter_ownership: Callable[
            [astx.Argument, SemanticSymbol], None
        ],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          analyze_function_template_specializations:
            type: Callable[[SemanticFunction], None]
          analyze_parameter_defaults:
            type: Callable[[SemanticFunction], None]
          guarantees_return:
            type: Callable[[astx.AST], bool]
          prepare_function_template_specializations:
            type: Callable[[SemanticFunction], None]
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
          registry:
            type: SemanticRegistry
          visit:
            type: Callable[[astx.AST], None]
          free_resolve_parameter_ownership:
            type: Callable[[astx.Argument, SemanticSymbol], None]
        """
        object.__setattr__(
            self,
            "analyze_function_template_specializations",
            analyze_function_template_specializations,
        )
        object.__setattr__(
            self, "analyze_parameter_defaults", analyze_parameter_defaults
        )
        object.__setattr__(self, "guarantees_return", guarantees_return)
        object.__setattr__(
            self,
            "prepare_function_template_specializations",
            prepare_function_template_specializations,
        )
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "registry", registry)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self,
            "free_resolve_parameter_ownership",
            free_resolve_parameter_ownership,
        )
