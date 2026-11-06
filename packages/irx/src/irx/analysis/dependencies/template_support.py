"""
title: Explicit TemplateSupport semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from public import private

from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class TemplateSupportAnalysisServices:
    """
    title: Explicit dependencies for TemplateSupportAnalysis.
    """

    def __init__(self) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        """
