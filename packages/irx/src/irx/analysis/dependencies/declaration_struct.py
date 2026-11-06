"""
title: Explicit DeclarationStruct semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    ResolveDeclaredTypeCallback,
    ResolveStructFromTypeCallback,
)
from irx.analysis.registry import SemanticRegistry
from irx.analysis.resolved_nodes import (
    SemanticStruct,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class DeclarationStructAnalysisServices:
    """
    title: Explicit dependencies for DeclarationStructAnalysis.
    attributes:
      resolve_declared_type:
        type: ResolveDeclaredTypeCallback
      resolve_struct_from_type:
        type: ResolveStructFromTypeCallback
      set_struct:
        type: >-
          Callable[[astx.AST, SemanticStruct | None], SemanticStruct | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      bindings:
        type: VisibleBindings
      context:
        type: SemanticContext
      registry:
        type: SemanticRegistry
    """

    resolve_declared_type: ResolveDeclaredTypeCallback
    resolve_struct_from_type: ResolveStructFromTypeCallback
    set_struct: Callable[
        [astx.AST, SemanticStruct | None], SemanticStruct | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    bindings: VisibleBindings
    context: SemanticContext
    registry: SemanticRegistry

    def __init__(
        self,
        resolve_declared_type: ResolveDeclaredTypeCallback,
        resolve_struct_from_type: ResolveStructFromTypeCallback,
        set_struct: Callable[
            [astx.AST, SemanticStruct | None], SemanticStruct | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        bindings: VisibleBindings,
        context: SemanticContext,
        registry: SemanticRegistry,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          resolve_declared_type:
            type: ResolveDeclaredTypeCallback
          resolve_struct_from_type:
            type: ResolveStructFromTypeCallback
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
          registry:
            type: SemanticRegistry
        """
        object.__setattr__(
            self, "resolve_declared_type", resolve_declared_type
        )
        object.__setattr__(
            self, "resolve_struct_from_type", resolve_struct_from_type
        )
        object.__setattr__(self, "set_struct", set_struct)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "registry", registry)
