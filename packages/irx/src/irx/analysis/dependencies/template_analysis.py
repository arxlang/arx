"""
title: Explicit TemplateAnalysis semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import ResolveDeclaredTypeCallback
from irx.analysis.module_interfaces import ModuleKey
from irx.analysis.resolved_nodes import (
    SemanticFunction,
    SemanticSymbol,
    TemplateArgumentBinding,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class TemplateAnalysisAnalysisServices:
    """
    title: Explicit dependencies for TemplateAnalysisAnalysis.
    attributes:
      analyze_parameter_defaults:
        type: Callable[[SemanticFunction], None]
      build_template_specialization:
        type: >-
          Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
          SemanticFunction | None]
      current_module_key:
        type: Callable[[], ModuleKey]
      format_template_bindings:
        type: Callable[[Iterable[TemplateArgumentBinding]], str]
      guarantees_return:
        type: Callable[[astx.AST], bool]
      mark_template_specializations_prepared:
        type: Callable[[SemanticFunction], None]
      resolve_declared_type:
        type: ResolveDeclaredTypeCallback
      set_function:
        type: >-
          Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
          None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      template_param_domain:
        type: Callable[[astx.TemplateParam], tuple[astx.DataType, Ellipsis]]
      template_specializations_prepared:
        type: Callable[[SemanticFunction], bool]
      context:
        type: SemanticContext
      visit:
        type: Callable[[astx.AST], None]
      free_resolve_parameter_ownership:
        type: Callable[[astx.Argument, SemanticSymbol], None]
    """

    analyze_parameter_defaults: Callable[[SemanticFunction], None]
    build_template_specialization: Callable[
        [SemanticFunction, tuple[astx.DataType, ...]], SemanticFunction | None
    ]
    current_module_key: Callable[[], ModuleKey]
    format_template_bindings: Callable[
        [Iterable[TemplateArgumentBinding]], str
    ]
    guarantees_return: Callable[[astx.AST], bool]
    mark_template_specializations_prepared: Callable[[SemanticFunction], None]
    resolve_declared_type: ResolveDeclaredTypeCallback
    set_function: Callable[
        [astx.AST, SemanticFunction | None], SemanticFunction | None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    template_param_domain: Callable[
        [astx.TemplateParam], tuple[astx.DataType, ...]
    ]
    template_specializations_prepared: Callable[[SemanticFunction], bool]
    context: SemanticContext
    visit: Callable[[astx.AST], None]
    free_resolve_parameter_ownership: Callable[
        [astx.Argument, SemanticSymbol], None
    ]

    def __init__(
        self,
        analyze_parameter_defaults: Callable[[SemanticFunction], None],
        build_template_specialization: Callable[
            [SemanticFunction, tuple[astx.DataType, ...]],
            SemanticFunction | None,
        ],
        current_module_key: Callable[[], ModuleKey],
        format_template_bindings: Callable[
            [Iterable[TemplateArgumentBinding]], str
        ],
        guarantees_return: Callable[[astx.AST], bool],
        mark_template_specializations_prepared: Callable[
            [SemanticFunction], None
        ],
        resolve_declared_type: ResolveDeclaredTypeCallback,
        set_function: Callable[
            [astx.AST, SemanticFunction | None], SemanticFunction | None
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        template_param_domain: Callable[
            [astx.TemplateParam], tuple[astx.DataType, ...]
        ],
        template_specializations_prepared: Callable[[SemanticFunction], bool],
        context: SemanticContext,
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
          build_template_specialization:
            type: >-
              Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
              SemanticFunction | None]
          current_module_key:
            type: Callable[[], ModuleKey]
          format_template_bindings:
            type: Callable[[Iterable[TemplateArgumentBinding]], str]
          guarantees_return:
            type: Callable[[astx.AST], bool]
          mark_template_specializations_prepared:
            type: Callable[[SemanticFunction], None]
          resolve_declared_type:
            type: ResolveDeclaredTypeCallback
          set_function:
            type: >-
              Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
              None]
          set_symbol:
            type: >-
              Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol |
              None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          template_param_domain:
            type: >-
              Callable[[astx.TemplateParam], tuple[astx.DataType, Ellipsis]]
          template_specializations_prepared:
            type: Callable[[SemanticFunction], bool]
          context:
            type: SemanticContext
          visit:
            type: Callable[[astx.AST], None]
          free_resolve_parameter_ownership:
            type: Callable[[astx.Argument, SemanticSymbol], None]
        """
        object.__setattr__(
            self, "analyze_parameter_defaults", analyze_parameter_defaults
        )
        object.__setattr__(
            self,
            "build_template_specialization",
            build_template_specialization,
        )
        object.__setattr__(self, "current_module_key", current_module_key)
        object.__setattr__(
            self, "format_template_bindings", format_template_bindings
        )
        object.__setattr__(self, "guarantees_return", guarantees_return)
        object.__setattr__(
            self,
            "mark_template_specializations_prepared",
            mark_template_specializations_prepared,
        )
        object.__setattr__(
            self, "resolve_declared_type", resolve_declared_type
        )
        object.__setattr__(self, "set_function", set_function)
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(
            self, "template_param_domain", template_param_domain
        )
        object.__setattr__(
            self,
            "template_specializations_prepared",
            template_specializations_prepared,
        )
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self,
            "free_resolve_parameter_ownership",
            free_resolve_parameter_ownership,
        )
