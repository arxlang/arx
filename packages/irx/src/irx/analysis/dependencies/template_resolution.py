"""
title: Explicit TemplateResolution semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.resolved_nodes import (
    SemanticFunction,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class TemplateResolutionAnalysisServices:
    """
    title: Explicit dependencies for TemplateResolutionAnalysis.
    attributes:
      build_template_specialization:
        type: >-
          Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
          SemanticFunction | None]
      type_within_template_bound:
        type: Callable[[astx.DataType, astx.DataType], bool]
      context:
        type: SemanticContext
    """

    build_template_specialization: Callable[
        [SemanticFunction, tuple[astx.DataType, ...]], SemanticFunction | None
    ]
    type_within_template_bound: Callable[[astx.DataType, astx.DataType], bool]
    context: SemanticContext

    def __init__(
        self,
        build_template_specialization: Callable[
            [SemanticFunction, tuple[astx.DataType, ...]],
            SemanticFunction | None,
        ],
        type_within_template_bound: Callable[
            [astx.DataType, astx.DataType], bool
        ],
        context: SemanticContext,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          build_template_specialization:
            type: >-
              Callable[[SemanticFunction, tuple[astx.DataType, Ellipsis]],
              SemanticFunction | None]
          type_within_template_bound:
            type: Callable[[astx.DataType, astx.DataType], bool]
          context:
            type: SemanticContext
        """
        object.__setattr__(
            self,
            "build_template_specialization",
            build_template_specialization,
        )
        object.__setattr__(
            self, "type_within_template_bound", type_within_template_bound
        )
        object.__setattr__(self, "context", context)
