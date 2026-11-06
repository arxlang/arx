"""
title: Explicit ExpressionClassSupport semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import ResolveClassFromTypeCallback
from irx.analysis.resolved_nodes import (
    SemanticClass,
    SemanticClassMember,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionClassSupportAnalysisServices:
    """
    title: Explicit dependencies for ExpressionClassSupportAnalysis.
    attributes:
      format_method_signature:
        type: Callable[[SemanticClassMember], str]
      member_declaring_class:
        type: Callable[[SemanticClassMember], SemanticClass | None]
      member_display_name:
        type: Callable[[SemanticClassMember], str]
      resolve_class_from_type:
        type: ResolveClassFromTypeCallback
      bindings:
        type: VisibleBindings
      context:
        type: SemanticContext
    """

    format_method_signature: Callable[[SemanticClassMember], str]
    member_declaring_class: Callable[
        [SemanticClassMember], SemanticClass | None
    ]
    member_display_name: Callable[[SemanticClassMember], str]
    resolve_class_from_type: ResolveClassFromTypeCallback
    bindings: VisibleBindings
    context: SemanticContext

    def __init__(
        self,
        format_method_signature: Callable[[SemanticClassMember], str],
        member_declaring_class: Callable[
            [SemanticClassMember], SemanticClass | None
        ],
        member_display_name: Callable[[SemanticClassMember], str],
        resolve_class_from_type: ResolveClassFromTypeCallback,
        bindings: VisibleBindings,
        context: SemanticContext,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          format_method_signature:
            type: Callable[[SemanticClassMember], str]
          member_declaring_class:
            type: Callable[[SemanticClassMember], SemanticClass | None]
          member_display_name:
            type: Callable[[SemanticClassMember], str]
          resolve_class_from_type:
            type: ResolveClassFromTypeCallback
          bindings:
            type: VisibleBindings
          context:
            type: SemanticContext
        """
        object.__setattr__(
            self, "format_method_signature", format_method_signature
        )
        object.__setattr__(
            self, "member_declaring_class", member_declaring_class
        )
        object.__setattr__(self, "member_display_name", member_display_name)
        object.__setattr__(
            self, "resolve_class_from_type", resolve_class_from_type
        )
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context", context)
