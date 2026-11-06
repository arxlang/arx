"""
title: Explicit Import semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.module_interfaces import ModuleKey
from irx.analysis.resolved_nodes import (
    ResolvedImportBinding,
    SemanticClass,
    SemanticFunction,
    SemanticModule,
    SemanticStruct,
)
from irx.analysis.session import CompilationSession
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ImportAnalysisServices:
    """
    title: Explicit dependencies for ImportAnalysis.
    attributes:
      current_module_key:
        type: Callable[[], ModuleKey]
      imports_supported_here:
        type: Callable[[astx.AST], bool]
      set_class:
        type: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
      set_function:
        type: >-
          Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
          None]
      set_imports:
        type: >-
          Callable[[astx.AST, tuple[ResolvedImportBinding, Ellipsis]], None]
      set_module:
        type: >-
          Callable[[astx.AST, SemanticModule | None], SemanticModule | None]
      set_struct:
        type: >-
          Callable[[astx.AST, SemanticStruct | None], SemanticStruct | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      bindings:
        type: VisibleBindings
      context:
        type: SemanticContext
      factory:
        type: SemanticEntityFactory
      session:
        type: CompilationSession | None
    """

    current_module_key: Callable[[], ModuleKey]
    imports_supported_here: Callable[[astx.AST], bool]
    set_class: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
    set_function: Callable[
        [astx.AST, SemanticFunction | None], SemanticFunction | None
    ]
    set_imports: Callable[[astx.AST, tuple[ResolvedImportBinding, ...]], None]
    set_module: Callable[
        [astx.AST, SemanticModule | None], SemanticModule | None
    ]
    set_struct: Callable[
        [astx.AST, SemanticStruct | None], SemanticStruct | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    bindings: VisibleBindings
    context: SemanticContext
    factory: SemanticEntityFactory
    session: CompilationSession | None

    def __init__(
        self,
        current_module_key: Callable[[], ModuleKey],
        imports_supported_here: Callable[[astx.AST], bool],
        set_class: Callable[
            [astx.AST, SemanticClass | None], SemanticClass | None
        ],
        set_function: Callable[
            [astx.AST, SemanticFunction | None], SemanticFunction | None
        ],
        set_imports: Callable[
            [astx.AST, tuple[ResolvedImportBinding, ...]], None
        ],
        set_module: Callable[
            [astx.AST, SemanticModule | None], SemanticModule | None
        ],
        set_struct: Callable[
            [astx.AST, SemanticStruct | None], SemanticStruct | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        bindings: VisibleBindings,
        context: SemanticContext,
        factory: SemanticEntityFactory,
        session: CompilationSession | None,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          current_module_key:
            type: Callable[[], ModuleKey]
          imports_supported_here:
            type: Callable[[astx.AST], bool]
          set_class:
            type: >-
              Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
          set_function:
            type: >-
              Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
              None]
          set_imports:
            type: >-
              Callable[[astx.AST, tuple[ResolvedImportBinding, Ellipsis]],
              None]
          set_module:
            type: >-
              Callable[[astx.AST, SemanticModule | None], SemanticModule |
              None]
          set_struct:
            type: >-
              Callable[[astx.AST, SemanticStruct | None], SemanticStruct |
              None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          bindings:
            type: VisibleBindings
          context:
            type: SemanticContext
          factory:
            type: SemanticEntityFactory
          session:
            type: CompilationSession | None
        """
        object.__setattr__(self, "current_module_key", current_module_key)
        object.__setattr__(
            self, "imports_supported_here", imports_supported_here
        )
        object.__setattr__(self, "set_class", set_class)
        object.__setattr__(self, "set_function", set_function)
        object.__setattr__(self, "set_imports", set_imports)
        object.__setattr__(self, "set_module", set_module)
        object.__setattr__(self, "set_struct", set_struct)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "session", session)
