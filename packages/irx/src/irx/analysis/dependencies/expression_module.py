"""
title: Explicit ExpressionModule semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import ResolveClassFromTypeCallback
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.resolved_nodes import (
    CallResolution,
    ResolvedModuleMemberAccess,
    ResourceOwnership,
    SemanticClass,
    SemanticFunction,
    SemanticInfo,
    SemanticModule,
    SemanticStruct,
    SemanticSymbol,
)
from irx.analysis.session import CompilationSession
from irx.extensions import ScopedDispatch
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionModuleAnalysisServices:
    """
    title: Explicit dependencies for ExpressionModuleAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      resolve_class_from_type:
        type: ResolveClassFromTypeCallback
      resolve_template_call_target:
        type: >-
          Callable[[SemanticFunction, list[astx.DataType | None], astx.AST],
          SemanticFunction | None]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_call:
        type: >-
          Callable[[astx.AST, CallResolution | None], CallResolution | None]
      set_class:
        type: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
      set_function:
        type: >-
          Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
          None]
      set_module:
        type: >-
          Callable[[astx.AST, SemanticModule | None], SemanticModule | None]
      set_module_member_access:
        type: Callable[[astx.AST, ResolvedModuleMemberAccess | None], None]
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_struct:
        type: >-
          Callable[[astx.AST, SemanticStruct | None], SemanticStruct | None]
      set_symbol:
        type: >-
          Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      bindings:
        type: VisibleBindings
      call_dispatch:
        type: ScopedDispatch
      context:
        type: SemanticContext
      factory:
        type: SemanticEntityFactory
      resolve_class_construction:
        type: >-
          Callable[[astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
          SemanticClass], None]
      session:
        type: CompilationSession | None
      visit:
        type: Callable[[astx.AST], None]
      free_resolve_materialization:
        type: Callable[[astx.FunctionCall], None]
      free_resolve_text_call:
        type: Callable[[astx.FunctionCall | astx.MethodCall], None]
      free_resolve_file_open:
        type: Callable[[astx.FunctionCall], None]
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    resolve_class_from_type: ResolveClassFromTypeCallback
    resolve_template_call_target: Callable[
        [SemanticFunction, list[astx.DataType | None], astx.AST],
        SemanticFunction | None,
    ]
    semantic: Callable[[astx.AST], SemanticInfo]
    set_call: Callable[
        [astx.AST, CallResolution | None], CallResolution | None
    ]
    set_class: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
    set_function: Callable[
        [astx.AST, SemanticFunction | None], SemanticFunction | None
    ]
    set_module: Callable[
        [astx.AST, SemanticModule | None], SemanticModule | None
    ]
    set_module_member_access: Callable[
        [astx.AST, ResolvedModuleMemberAccess | None], None
    ]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_struct: Callable[
        [astx.AST, SemanticStruct | None], SemanticStruct | None
    ]
    set_symbol: Callable[
        [astx.AST, SemanticSymbol | None], SemanticSymbol | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    bindings: VisibleBindings
    call_dispatch: ScopedDispatch
    context: SemanticContext
    factory: SemanticEntityFactory
    resolve_class_construction: Callable[
        [
            astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
            SemanticClass,
        ],
        None,
    ]
    session: CompilationSession | None
    visit: Callable[[astx.AST], None]
    free_resolve_materialization: Callable[[astx.FunctionCall], None]
    free_resolve_text_call: Callable[
        [astx.FunctionCall | astx.MethodCall], None
    ]
    free_resolve_file_open: Callable[[astx.FunctionCall], None]

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        resolve_class_from_type: ResolveClassFromTypeCallback,
        resolve_template_call_target: Callable[
            [SemanticFunction, list[astx.DataType | None], astx.AST],
            SemanticFunction | None,
        ],
        semantic: Callable[[astx.AST], SemanticInfo],
        set_call: Callable[
            [astx.AST, CallResolution | None], CallResolution | None
        ],
        set_class: Callable[
            [astx.AST, SemanticClass | None], SemanticClass | None
        ],
        set_function: Callable[
            [astx.AST, SemanticFunction | None], SemanticFunction | None
        ],
        set_module: Callable[
            [astx.AST, SemanticModule | None], SemanticModule | None
        ],
        set_module_member_access: Callable[
            [astx.AST, ResolvedModuleMemberAccess | None], None
        ],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_struct: Callable[
            [astx.AST, SemanticStruct | None], SemanticStruct | None
        ],
        set_symbol: Callable[
            [astx.AST, SemanticSymbol | None], SemanticSymbol | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        bindings: VisibleBindings,
        call_dispatch: ScopedDispatch,
        context: SemanticContext,
        factory: SemanticEntityFactory,
        resolve_class_construction: Callable[
            [
                astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
                SemanticClass,
            ],
            None,
        ],
        session: CompilationSession | None,
        visit: Callable[[astx.AST], None],
        free_resolve_materialization: Callable[[astx.FunctionCall], None],
        free_resolve_text_call: Callable[
            [astx.FunctionCall | astx.MethodCall], None
        ],
        free_resolve_file_open: Callable[[astx.FunctionCall], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          resolve_class_from_type:
            type: ResolveClassFromTypeCallback
          resolve_template_call_target:
            type: >-
              Callable[[SemanticFunction, list[astx.DataType | None],
              astx.AST], SemanticFunction | None]
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_call:
            type: >-
              Callable[[astx.AST, CallResolution | None], CallResolution |
              None]
          set_class:
            type: >-
              Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
          set_function:
            type: >-
              Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
              None]
          set_module:
            type: >-
              Callable[[astx.AST, SemanticModule | None], SemanticModule |
              None]
          set_module_member_access:
            type: Callable[[astx.AST, ResolvedModuleMemberAccess | None], None]
          set_resource_ownership:
            type: >-
              Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership
              | None]
          set_struct:
            type: >-
              Callable[[astx.AST, SemanticStruct | None], SemanticStruct |
              None]
          set_symbol:
            type: >-
              Callable[[astx.AST, SemanticSymbol | None], SemanticSymbol |
              None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          bindings:
            type: VisibleBindings
          call_dispatch:
            type: ScopedDispatch
          context:
            type: SemanticContext
          factory:
            type: SemanticEntityFactory
          resolve_class_construction:
            type: >-
              Callable[[astx.ClassConstruct | astx.FunctionCall |
              astx.MethodCall, SemanticClass], None]
          session:
            type: CompilationSession | None
          visit:
            type: Callable[[astx.AST], None]
          free_resolve_materialization:
            type: Callable[[astx.FunctionCall], None]
          free_resolve_text_call:
            type: Callable[[astx.FunctionCall | astx.MethodCall], None]
          free_resolve_file_open:
            type: Callable[[astx.FunctionCall], None]
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self, "resolve_class_from_type", resolve_class_from_type
        )
        object.__setattr__(
            self, "resolve_template_call_target", resolve_template_call_target
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_call", set_call)
        object.__setattr__(self, "set_class", set_class)
        object.__setattr__(self, "set_function", set_function)
        object.__setattr__(self, "set_module", set_module)
        object.__setattr__(
            self, "set_module_member_access", set_module_member_access
        )
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_struct", set_struct)
        object.__setattr__(self, "set_symbol", set_symbol)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "call_dispatch", call_dispatch)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(
            self, "resolve_class_construction", resolve_class_construction
        )
        object.__setattr__(self, "session", session)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self, "free_resolve_materialization", free_resolve_materialization
        )
        object.__setattr__(
            self, "free_resolve_text_call", free_resolve_text_call
        )
        object.__setattr__(
            self, "free_resolve_file_open", free_resolve_file_open
        )
