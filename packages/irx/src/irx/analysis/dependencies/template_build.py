"""
title: Explicit TemplateBuild semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.resolved_nodes import (
    SemanticFunction,
    TemplateSpecializationKey,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class TemplateBuildAnalysisServices:
    """
    title: Explicit dependencies for TemplateBuildAnalysis.
    attributes:
      clear_semantic_sidecars:
        type: Callable[[astx.AST], None]
      function_owner_module:
        type: Callable[[SemanticFunction], astx.Module | None]
      set_function:
        type: >-
          Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
          None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      substitute_declared_types:
        type: Callable[[astx.AST, dict[str, astx.DataType]], None]
      substitute_type:
        type: >-
          Callable[[astx.DataType, dict[str, astx.DataType]], astx.DataType]
      template_bindings_map:
        type: >-
          Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
          dict[str, astx.DataType]]
      template_specialization_key:
        type: >-
          Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
          TemplateSpecializationKey]
      template_specialization_name:
        type: Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]], str]
      template_specialization_symbol_name:
        type: Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]], str]
      context:
        type: SemanticContext
      factory:
        type: SemanticEntityFactory
    """

    clear_semantic_sidecars: Callable[[astx.AST], None]
    function_owner_module: Callable[[SemanticFunction], astx.Module | None]
    set_function: Callable[
        [astx.AST, SemanticFunction | None], SemanticFunction | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    substitute_declared_types: Callable[
        [astx.AST, dict[str, astx.DataType]], None
    ]
    substitute_type: Callable[
        [astx.DataType, dict[str, astx.DataType]], astx.DataType
    ]
    template_bindings_map: Callable[
        [SemanticFunction, tuple[astx.DataType, ...]], dict[str, astx.DataType]
    ]
    template_specialization_key: Callable[
        [SemanticFunction, tuple[astx.DataType, ...]],
        TemplateSpecializationKey,
    ]
    template_specialization_name: Callable[
        [SemanticFunction, tuple[astx.DataType, ...]], str
    ]
    template_specialization_symbol_name: Callable[
        [SemanticFunction, tuple[astx.DataType, ...]], str
    ]
    context: SemanticContext
    factory: SemanticEntityFactory

    def __init__(
        self,
        clear_semantic_sidecars: Callable[[astx.AST], None],
        function_owner_module: Callable[
            [SemanticFunction], astx.Module | None
        ],
        set_function: Callable[
            [astx.AST, SemanticFunction | None], SemanticFunction | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        substitute_declared_types: Callable[
            [astx.AST, dict[str, astx.DataType]], None
        ],
        substitute_type: Callable[
            [astx.DataType, dict[str, astx.DataType]], astx.DataType
        ],
        template_bindings_map: Callable[
            [SemanticFunction, tuple[astx.DataType, ...]],
            dict[str, astx.DataType],
        ],
        template_specialization_key: Callable[
            [SemanticFunction, tuple[astx.DataType, ...]],
            TemplateSpecializationKey,
        ],
        template_specialization_name: Callable[
            [SemanticFunction, tuple[astx.DataType, ...]], str
        ],
        template_specialization_symbol_name: Callable[
            [SemanticFunction, tuple[astx.DataType, ...]], str
        ],
        context: SemanticContext,
        factory: SemanticEntityFactory,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          clear_semantic_sidecars:
            type: Callable[[astx.AST], None]
          function_owner_module:
            type: Callable[[SemanticFunction], astx.Module | None]
          set_function:
            type: >-
              Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
              None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          substitute_declared_types:
            type: Callable[[astx.AST, dict[str, astx.DataType]], None]
          substitute_type:
            type: >-
              Callable[[astx.DataType, dict[str, astx.DataType]],
              astx.DataType]
          template_bindings_map:
            type: >-
              Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
              dict[str, astx.DataType]]
          template_specialization_key:
            type: >-
              Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
              TemplateSpecializationKey]
          template_specialization_name:
            type: >-
              Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]], str]
          template_specialization_symbol_name:
            type: >-
              Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]], str]
          context:
            type: SemanticContext
          factory:
            type: SemanticEntityFactory
        """
        object.__setattr__(
            self, "clear_semantic_sidecars", clear_semantic_sidecars
        )
        object.__setattr__(
            self, "function_owner_module", function_owner_module
        )
        object.__setattr__(self, "set_function", set_function)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(
            self, "substitute_declared_types", substitute_declared_types
        )
        object.__setattr__(self, "substitute_type", substitute_type)
        object.__setattr__(
            self, "template_bindings_map", template_bindings_map
        )
        object.__setattr__(
            self, "template_specialization_key", template_specialization_key
        )
        object.__setattr__(
            self, "template_specialization_name", template_specialization_name
        )
        object.__setattr__(
            self,
            "template_specialization_symbol_name",
            template_specialization_symbol_name,
        )
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "factory", factory)
