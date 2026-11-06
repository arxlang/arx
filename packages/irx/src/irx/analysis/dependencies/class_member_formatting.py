"""
title: Explicit ClassMemberFormatting semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from public import private

from irx.analysis.context import SemanticContext
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ClassMemberFormattingAnalysisServices:
    """
    title: Explicit dependencies for ClassMemberFormattingAnalysis.
    attributes:
      context:
        type: SemanticContext
    """

    context: SemanticContext

    def __init__(self, context: SemanticContext) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          context:
            type: SemanticContext
        """
        object.__setattr__(self, "context", context)
