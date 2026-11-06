"""
title: Explicit ExpressionTensor semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    TensorLifetimeCheck,
    ValidateTensorIndexOperationCallback,
)
from irx.analysis.resolved_nodes import (
    SemanticInfo,
)
from irx.builtins.collections.tensor import TensorLayout
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionTensorAnalysisServices:
    """
    title: Explicit dependencies for ExpressionTensorAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      static_tensor_element_type:
        type: Callable[[astx.AST], astx.DataType | None]
      static_tensor_flags:
        type: Callable[[astx.AST], int | None]
      static_tensor_layout:
        type: Callable[[astx.AST], TensorLayout | None]
      validate_tensor_index_operation:
        type: ValidateTensorIndexOperationCallback
      validate_tensor_lifetime_operation:
        type: TensorLifetimeCheck
      context:
        type: SemanticContext
      visit:
        type: Callable[[astx.AST], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    semantic: Callable[[astx.AST], SemanticInfo]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    static_tensor_element_type: Callable[[astx.AST], astx.DataType | None]
    static_tensor_flags: Callable[[astx.AST], int | None]
    static_tensor_layout: Callable[[astx.AST], TensorLayout | None]
    validate_tensor_index_operation: ValidateTensorIndexOperationCallback
    validate_tensor_lifetime_operation: TensorLifetimeCheck
    context: SemanticContext
    visit: Callable[[astx.AST], None]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        semantic: Callable[[astx.AST], SemanticInfo],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        static_tensor_element_type: Callable[[astx.AST], astx.DataType | None],
        static_tensor_flags: Callable[[astx.AST], int | None],
        static_tensor_layout: Callable[[astx.AST], TensorLayout | None],
        validate_tensor_index_operation: ValidateTensorIndexOperationCallback,
        validate_tensor_lifetime_operation: TensorLifetimeCheck,
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
          static_tensor_element_type:
            type: Callable[[astx.AST], astx.DataType | None]
          static_tensor_flags:
            type: Callable[[astx.AST], int | None]
          static_tensor_layout:
            type: Callable[[astx.AST], TensorLayout | None]
          validate_tensor_index_operation:
            type: ValidateTensorIndexOperationCallback
          validate_tensor_lifetime_operation:
            type: TensorLifetimeCheck
          context:
            type: SemanticContext
          visit:
            type: Callable[[astx.AST], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(
            self, "static_tensor_element_type", static_tensor_element_type
        )
        object.__setattr__(self, "static_tensor_flags", static_tensor_flags)
        object.__setattr__(self, "static_tensor_layout", static_tensor_layout)
        object.__setattr__(
            self,
            "validate_tensor_index_operation",
            validate_tensor_index_operation,
        )
        object.__setattr__(
            self,
            "validate_tensor_lifetime_operation",
            validate_tensor_lifetime_operation,
        )
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
