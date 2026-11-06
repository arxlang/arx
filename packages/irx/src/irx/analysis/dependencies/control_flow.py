"""
title: Explicit ControlFlow semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    DeclareIterationTargetCallback,
    RequireValueExpressionCallback,
    ResolveClassFromTypeCallback,
    ResolveDeclaredTypeCallback,
    ResolveMethodOverloadCallback,
)
from irx.analysis.registry import SemanticRegistry
from irx.analysis.resolved_nodes import (
    ResolvedContextManager,
    ResolvedIteration,
    ResolvedOperator,
    ResolvedYield,
    ResourceOwnership,
    ReturnResolution,
    SemanticClass,
    SemanticClassMember,
    SemanticFunction,
    SemanticInfo,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ControlFlowAnalysisServices:
    """
    title: Explicit dependencies for ControlFlowAnalysis.
    attributes:
      declare_iteration_target:
        type: DeclareIterationTargetCallback
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      require_value_expression:
        type: RequireValueExpressionCallback
      resolve_class_from_type:
        type: ResolveClassFromTypeCallback
      resolve_declared_type:
        type: ResolveDeclaredTypeCallback
      resolve_template_method_call_target:
        type: >-
          Callable[[SemanticFunction, SemanticFunction, list[astx.DataType |
          None], astx.AST], SemanticFunction | None]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_context_manager:
        type: Callable[[astx.AST, ResolvedContextManager | None], None]
      set_iteration:
        type: >-
          Callable[[astx.AST, ResolvedIteration | None], ResolvedIteration |
          None]
      set_operator:
        type: Callable[[astx.AST, ResolvedOperator | None], None]
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_return:
        type: >-
          Callable[[astx.AST, ReturnResolution | None], ReturnResolution |
          None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      set_yield:
        type: Callable[[astx.AST, ResolvedYield | None], ResolvedYield | None]
      specialization_bindings_map:
        type: Callable[[SemanticFunction], dict[str, astx.DataType]]
      specialize_signature:
        type: >-
          Callable[[SemanticFunction, dict[str, astx.DataType]],
          SemanticFunction]
      resolve_method_overload:
        type: ResolveMethodOverloadCallback
      visible_method_function:
        type: Callable[[SemanticClass, SemanticClassMember], SemanticFunction]
      context:
        type: SemanticContext
      registry:
        type: SemanticRegistry
      visit:
        type: Callable[[astx.AST], None]
    """

    declare_iteration_target: DeclareIterationTargetCallback
    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    require_value_expression: RequireValueExpressionCallback
    resolve_class_from_type: ResolveClassFromTypeCallback
    resolve_declared_type: ResolveDeclaredTypeCallback
    resolve_template_method_call_target: Callable[
        [
            SemanticFunction,
            SemanticFunction,
            list[astx.DataType | None],
            astx.AST,
        ],
        SemanticFunction | None,
    ]
    semantic: Callable[[astx.AST], SemanticInfo]
    set_context_manager: Callable[
        [astx.AST, ResolvedContextManager | None], None
    ]
    set_iteration: Callable[
        [astx.AST, ResolvedIteration | None], ResolvedIteration | None
    ]
    set_operator: Callable[[astx.AST, ResolvedOperator | None], None]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_return: Callable[
        [astx.AST, ReturnResolution | None], ReturnResolution | None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    set_yield: Callable[[astx.AST, ResolvedYield | None], ResolvedYield | None]
    specialization_bindings_map: Callable[
        [SemanticFunction], dict[str, astx.DataType]
    ]
    specialize_signature: Callable[
        [SemanticFunction, dict[str, astx.DataType]], SemanticFunction
    ]
    resolve_method_overload: ResolveMethodOverloadCallback
    visible_method_function: Callable[
        [SemanticClass, SemanticClassMember], SemanticFunction
    ]
    context: SemanticContext
    registry: SemanticRegistry
    visit: Callable[[astx.AST], None]

    def __init__(
        self,
        declare_iteration_target: DeclareIterationTargetCallback,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        require_value_expression: RequireValueExpressionCallback,
        resolve_class_from_type: ResolveClassFromTypeCallback,
        resolve_declared_type: ResolveDeclaredTypeCallback,
        resolve_template_method_call_target: Callable[
            [
                SemanticFunction,
                SemanticFunction,
                list[astx.DataType | None],
                astx.AST,
            ],
            SemanticFunction | None,
        ],
        semantic: Callable[[astx.AST], SemanticInfo],
        set_context_manager: Callable[
            [astx.AST, ResolvedContextManager | None], None
        ],
        set_iteration: Callable[
            [astx.AST, ResolvedIteration | None], ResolvedIteration | None
        ],
        set_operator: Callable[[astx.AST, ResolvedOperator | None], None],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_return: Callable[
            [astx.AST, ReturnResolution | None], ReturnResolution | None
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        set_yield: Callable[
            [astx.AST, ResolvedYield | None], ResolvedYield | None
        ],
        specialization_bindings_map: Callable[
            [SemanticFunction], dict[str, astx.DataType]
        ],
        specialize_signature: Callable[
            [SemanticFunction, dict[str, astx.DataType]], SemanticFunction
        ],
        resolve_method_overload: ResolveMethodOverloadCallback,
        visible_method_function: Callable[
            [SemanticClass, SemanticClassMember], SemanticFunction
        ],
        context: SemanticContext,
        registry: SemanticRegistry,
        visit: Callable[[astx.AST], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          declare_iteration_target:
            type: DeclareIterationTargetCallback
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          require_value_expression:
            type: RequireValueExpressionCallback
          resolve_class_from_type:
            type: ResolveClassFromTypeCallback
          resolve_declared_type:
            type: ResolveDeclaredTypeCallback
          resolve_template_method_call_target:
            type: >-
              Callable[[SemanticFunction, SemanticFunction, list[astx.DataType
              | None], astx.AST], SemanticFunction | None]
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_context_manager:
            type: Callable[[astx.AST, ResolvedContextManager | None], None]
          set_iteration:
            type: >-
              Callable[[astx.AST, ResolvedIteration | None], ResolvedIteration
              | None]
          set_operator:
            type: Callable[[astx.AST, ResolvedOperator | None], None]
          set_resource_ownership:
            type: >-
              Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership
              | None]
          set_return:
            type: >-
              Callable[[astx.AST, ReturnResolution | None], ReturnResolution |
              None]
          set_symbol:
            type: >-
              Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol |
              None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          set_yield:
            type: >-
              Callable[[astx.AST, ResolvedYield | None], ResolvedYield | None]
          specialization_bindings_map:
            type: Callable[[SemanticFunction], dict[str, astx.DataType]]
          specialize_signature:
            type: >-
              Callable[[SemanticFunction, dict[str, astx.DataType]],
              SemanticFunction]
          resolve_method_overload:
            type: ResolveMethodOverloadCallback
          visible_method_function:
            type: >-
              Callable[[SemanticClass, SemanticClassMember], SemanticFunction]
          context:
            type: SemanticContext
          registry:
            type: SemanticRegistry
          visit:
            type: Callable[[astx.AST], None]
        """
        object.__setattr__(
            self, "declare_iteration_target", declare_iteration_target
        )
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self, "require_value_expression", require_value_expression
        )
        object.__setattr__(
            self, "resolve_class_from_type", resolve_class_from_type
        )
        object.__setattr__(
            self, "resolve_declared_type", resolve_declared_type
        )
        object.__setattr__(
            self,
            "resolve_template_method_call_target",
            resolve_template_method_call_target,
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_context_manager", set_context_manager)
        object.__setattr__(self, "set_iteration", set_iteration)
        object.__setattr__(self, "set_operator", set_operator)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_return", set_return)
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "set_yield", set_yield)
        object.__setattr__(
            self, "specialization_bindings_map", specialization_bindings_map
        )
        object.__setattr__(self, "specialize_signature", specialize_signature)
        object.__setattr__(
            self, "resolve_method_overload", resolve_method_overload
        )
        object.__setattr__(
            self, "visible_method_function", visible_method_function
        )
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "registry", registry)
        object.__setattr__(self, "visit", visit)
