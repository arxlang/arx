"""
title: Explicit ExpressionBufferView semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    BufferIndexCheck,
    BufferLifetimeCheck,
)
from irx.analysis.resolved_nodes import (
    SemanticInfo,
)
from irx.buffer import BufferViewMetadata
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionBufferViewAnalysisServices:
    """
    title: Explicit dependencies for ExpressionBufferViewAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      static_buffer_view_metadata:
        type: Callable[[astx.AST], BufferViewMetadata | None]
      validate_buffer_lifetime_operation:
        type: BufferLifetimeCheck
      validate_buffer_view_index_operation:
        type: BufferIndexCheck
      context:
        type: SemanticContext
      visit:
        type: Callable[[astx.AST], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    semantic: Callable[[astx.AST], SemanticInfo]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    static_buffer_view_metadata: Callable[
        [astx.AST], BufferViewMetadata | None
    ]
    validate_buffer_lifetime_operation: BufferLifetimeCheck
    validate_buffer_view_index_operation: BufferIndexCheck
    context: SemanticContext
    visit: Callable[[astx.AST], None]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        semantic: Callable[[astx.AST], SemanticInfo],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        static_buffer_view_metadata: Callable[
            [astx.AST], BufferViewMetadata | None
        ],
        validate_buffer_lifetime_operation: BufferLifetimeCheck,
        validate_buffer_view_index_operation: BufferIndexCheck,
        context: SemanticContext,
        visit: Callable[[astx.AST], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          static_buffer_view_metadata:
            type: Callable[[astx.AST], BufferViewMetadata | None]
          validate_buffer_lifetime_operation:
            type: BufferLifetimeCheck
          validate_buffer_view_index_operation:
            type: BufferIndexCheck
          context:
            type: SemanticContext
          visit:
            type: Callable[[astx.AST], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(
            self, "static_buffer_view_metadata", static_buffer_view_metadata
        )
        object.__setattr__(
            self,
            "validate_buffer_lifetime_operation",
            validate_buffer_lifetime_operation,
        )
        object.__setattr__(
            self,
            "validate_buffer_view_index_operation",
            validate_buffer_view_index_operation,
        )
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
