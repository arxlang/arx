"""
title: Explicit TemplateState semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.session import CompilationSession
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class TemplateStateAnalysisServices:
    """
    title: Explicit dependencies for TemplateStateAnalysis.
    attributes:
      substitute_type:
        type: >-
          Callable[[astx.DataType, dict[str, astx.DataType]], astx.DataType]
      current_module:
        type: Callable[[], astx.Module | None]
      session:
        type: CompilationSession | None
    """

    substitute_type: Callable[
        [astx.DataType, dict[str, astx.DataType]], astx.DataType
    ]
    current_module: Callable[[], astx.Module | None]
    session: CompilationSession | None

    def __init__(
        self,
        substitute_type: Callable[
            [astx.DataType, dict[str, astx.DataType]], astx.DataType
        ],
        current_module: Callable[[], astx.Module | None],
        session: CompilationSession | None,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          substitute_type:
            type: >-
              Callable[[astx.DataType, dict[str, astx.DataType]],
              astx.DataType]
          current_module:
            type: Callable[[], astx.Module | None]
          session:
            type: CompilationSession | None
        """
        object.__setattr__(self, "substitute_type", substitute_type)
        object.__setattr__(self, "current_module", current_module)
        object.__setattr__(self, "session", session)
