"""
title: Explicit DeclarationFunction semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import ResolveDeclaredTypeCallback
from irx.analysis.registry import SemanticRegistry
from irx.analysis.resolved_nodes import (
    ResolvedGeneratorFunction,
    SemanticFunction,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class DeclarationFunctionAnalysisServices:
    """
    title: Explicit dependencies for DeclarationFunctionAnalysis.
    attributes:
      analyze_parameter_defaults:
        type: Callable[[SemanticFunction], None]
      guarantees_return:
        type: Callable[[astx.AST], bool]
      resolve_declared_type:
        type: ResolveDeclaredTypeCallback
      set_function:
        type: >-
          Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
          None]
      set_generator_function:
        type: >-
          Callable[[astx.AST, ResolvedGeneratorFunction | None],
          ResolvedGeneratorFunction | None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      bindings:
        type: VisibleBindings
      context:
        type: SemanticContext
      registry:
        type: SemanticRegistry
      visit:
        type: Callable[[astx.AST], None]
      free_resolve_parameter_ownership:
        type: Callable[[astx.Argument, SemanticSymbol], None]
    """

    analyze_parameter_defaults: Callable[[SemanticFunction], None]
    guarantees_return: Callable[[astx.AST], bool]
    resolve_declared_type: ResolveDeclaredTypeCallback
    set_function: Callable[
        [astx.AST, SemanticFunction | None], SemanticFunction | None
    ]
    set_generator_function: Callable[
        [astx.AST, ResolvedGeneratorFunction | None],
        ResolvedGeneratorFunction | None,
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    bindings: VisibleBindings
    context: SemanticContext
    registry: SemanticRegistry
    visit: Callable[[astx.AST], None]
    free_resolve_parameter_ownership: Callable[
        [astx.Argument, SemanticSymbol], None
    ]

    def __init__(
        self,
        analyze_parameter_defaults: Callable[[SemanticFunction], None],
        guarantees_return: Callable[[astx.AST], bool],
        resolve_declared_type: ResolveDeclaredTypeCallback,
        set_function: Callable[
            [astx.AST, SemanticFunction | None], SemanticFunction | None
        ],
        set_generator_function: Callable[
            [astx.AST, ResolvedGeneratorFunction | None],
            ResolvedGeneratorFunction | None,
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        bindings: VisibleBindings,
        context: SemanticContext,
        registry: SemanticRegistry,
        visit: Callable[[astx.AST], None],
        free_resolve_parameter_ownership: Callable[
            [astx.Argument, SemanticSymbol], None
        ],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          analyze_parameter_defaults:
            type: Callable[[SemanticFunction], None]
          guarantees_return:
            type: Callable[[astx.AST], bool]
          resolve_declared_type:
            type: ResolveDeclaredTypeCallback
          set_function:
            type: >-
              Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
              None]
          set_generator_function:
            type: >-
              Callable[[astx.AST, ResolvedGeneratorFunction | None],
              ResolvedGeneratorFunction | None]
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
          registry:
            type: SemanticRegistry
          visit:
            type: Callable[[astx.AST], None]
          free_resolve_parameter_ownership:
            type: Callable[[astx.Argument, SemanticSymbol], None]
        """
        object.__setattr__(
            self, "analyze_parameter_defaults", analyze_parameter_defaults
        )
        object.__setattr__(self, "guarantees_return", guarantees_return)
        object.__setattr__(
            self, "resolve_declared_type", resolve_declared_type
        )
        object.__setattr__(self, "set_function", set_function)
        object.__setattr__(
            self, "set_generator_function", set_generator_function
        )
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "registry", registry)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self,
            "free_resolve_parameter_ownership",
            free_resolve_parameter_ownership,
        )
