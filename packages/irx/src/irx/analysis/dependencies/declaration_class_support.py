"""
title: Explicit DeclarationClassSupport semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from public import private

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
class DeclarationClassSupportAnalysisServices:
    """
    title: Explicit dependencies for DeclarationClassSupportAnalysis.
    attributes:
      member_owner_module_key:
        type: Callable[[SemanticClassMember], str]
      resolve_class_from_type:
        type: ResolveClassFromTypeCallback
      resolve_class_structure:
        type: Callable[[SemanticClass], SemanticClass]
      context:
        type: SemanticContext
    """

    member_owner_module_key: Callable[[SemanticClassMember], str]
    resolve_class_from_type: ResolveClassFromTypeCallback
    resolve_class_structure: Callable[[SemanticClass], SemanticClass]
    context: SemanticContext

    def __init__(
        self,
        member_owner_module_key: Callable[[SemanticClassMember], str],
        resolve_class_from_type: ResolveClassFromTypeCallback,
        resolve_class_structure: Callable[[SemanticClass], SemanticClass],
        context: SemanticContext,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          member_owner_module_key:
            type: Callable[[SemanticClassMember], str]
          resolve_class_from_type:
            type: ResolveClassFromTypeCallback
          resolve_class_structure:
            type: Callable[[SemanticClass], SemanticClass]
          context:
            type: SemanticContext
        """
        object.__setattr__(
            self, "member_owner_module_key", member_owner_module_key
        )
        object.__setattr__(
            self, "resolve_class_from_type", resolve_class_from_type
        )
        object.__setattr__(
            self, "resolve_class_structure", resolve_class_structure
        )
        object.__setattr__(self, "context", context)
