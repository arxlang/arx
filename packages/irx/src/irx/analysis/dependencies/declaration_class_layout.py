"""
title: Explicit DeclarationClassLayout semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.resolved_nodes import (
    ClassInitializationSourceKind,
    SemanticClass,
    SemanticClassMember,
    SemanticClassMemberResolution,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class DeclarationClassLayoutAnalysisServices:
    """
    title: Explicit dependencies for DeclarationClassLayoutAnalysis.
    attributes:
      class_is_declared_abstract:
        type: Callable[[SemanticClass], bool]
      class_resolution_stack:
        type: Callable[[], list[SemanticClass]]
      class_storage_ancestors:
        type: >-
          Callable[[tuple[SemanticClass, Ellipsis]], tuple[SemanticClass,
          Ellipsis]]
      declared_member_tables:
        type: >-
          Callable[[tuple[SemanticClassMember, Ellipsis]], tuple[dict[str,
          SemanticClassMember], dict[str, tuple[SemanticClassMember,
          Ellipsis]]]]
      initializer_source_kind:
        type: Callable[[astx.AST | None], ClassInitializationSourceKind]
      resolve_class_structure:
        type: Callable[[SemanticClass], SemanticClass]
      resolve_effective_class_members:
        type: >-
          Callable[[SemanticClass, tuple[SemanticClass, Ellipsis], dict[str,
          SemanticClassMember], dict[str, tuple[SemanticClassMember,
          Ellipsis]]], tuple[dict[str, SemanticClassMember], dict[str,
          tuple[SemanticClassMember, Ellipsis]], dict[str,
          SemanticClassMemberResolution], dict[str,
          tuple[SemanticClassMemberResolution, Ellipsis]]]]
      set_class:
        type: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
      bindings:
        type: VisibleBindings
      context:
        type: SemanticContext
      free_register_exception_types:
        type: Callable[[], None]
    """

    class_is_declared_abstract: Callable[[SemanticClass], bool]
    class_resolution_stack: Callable[[], list[SemanticClass]]
    class_storage_ancestors: Callable[
        [tuple[SemanticClass, ...]], tuple[SemanticClass, ...]
    ]
    declared_member_tables: Callable[
        [tuple[SemanticClassMember, ...]],
        tuple[
            dict[str, SemanticClassMember],
            dict[str, tuple[SemanticClassMember, ...]],
        ],
    ]
    initializer_source_kind: Callable[
        [astx.AST | None], ClassInitializationSourceKind
    ]
    resolve_class_structure: Callable[[SemanticClass], SemanticClass]
    resolve_effective_class_members: Callable[
        [
            SemanticClass,
            tuple[SemanticClass, ...],
            dict[str, SemanticClassMember],
            dict[str, tuple[SemanticClassMember, ...]],
        ],
        tuple[
            dict[str, SemanticClassMember],
            dict[str, tuple[SemanticClassMember, ...]],
            dict[str, SemanticClassMemberResolution],
            dict[str, tuple[SemanticClassMemberResolution, ...]],
        ],
    ]
    set_class: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
    bindings: VisibleBindings
    context: SemanticContext
    free_register_exception_types: Callable[[], None]

    def __init__(
        self,
        class_is_declared_abstract: Callable[[SemanticClass], bool],
        class_resolution_stack: Callable[[], list[SemanticClass]],
        class_storage_ancestors: Callable[
            [tuple[SemanticClass, ...]], tuple[SemanticClass, ...]
        ],
        declared_member_tables: Callable[
            [tuple[SemanticClassMember, ...]],
            tuple[
                dict[str, SemanticClassMember],
                dict[str, tuple[SemanticClassMember, ...]],
            ],
        ],
        initializer_source_kind: Callable[
            [astx.AST | None], ClassInitializationSourceKind
        ],
        resolve_class_structure: Callable[[SemanticClass], SemanticClass],
        resolve_effective_class_members: Callable[
            [
                SemanticClass,
                tuple[SemanticClass, ...],
                dict[str, SemanticClassMember],
                dict[str, tuple[SemanticClassMember, ...]],
            ],
            tuple[
                dict[str, SemanticClassMember],
                dict[str, tuple[SemanticClassMember, ...]],
                dict[str, SemanticClassMemberResolution],
                dict[str, tuple[SemanticClassMemberResolution, ...]],
            ],
        ],
        set_class: Callable[
            [astx.AST, SemanticClass | None], SemanticClass | None
        ],
        bindings: VisibleBindings,
        context: SemanticContext,
        free_register_exception_types: Callable[[], None],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          class_is_declared_abstract:
            type: Callable[[SemanticClass], bool]
          class_resolution_stack:
            type: Callable[[], list[SemanticClass]]
          class_storage_ancestors:
            type: >-
              Callable[[tuple[SemanticClass, Ellipsis]], tuple[SemanticClass,
              Ellipsis]]
          declared_member_tables:
            type: >-
              Callable[[tuple[SemanticClassMember, Ellipsis]], tuple[dict[str,
              SemanticClassMember], dict[str, tuple[SemanticClassMember,
              Ellipsis]]]]
          initializer_source_kind:
            type: Callable[[astx.AST | None], ClassInitializationSourceKind]
          resolve_class_structure:
            type: Callable[[SemanticClass], SemanticClass]
          resolve_effective_class_members:
            type: >-
              Callable[[SemanticClass, tuple[SemanticClass, Ellipsis],
              dict[str, SemanticClassMember], dict[str,
              tuple[SemanticClassMember, Ellipsis]]], tuple[dict[str,
              SemanticClassMember], dict[str, tuple[SemanticClassMember,
              Ellipsis]], dict[str, SemanticClassMemberResolution], dict[str,
              tuple[SemanticClassMemberResolution, Ellipsis]]]]
          set_class:
            type: >-
              Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
          bindings:
            type: VisibleBindings
          context:
            type: SemanticContext
          free_register_exception_types:
            type: Callable[[], None]
        """
        object.__setattr__(
            self, "class_is_declared_abstract", class_is_declared_abstract
        )
        object.__setattr__(
            self, "class_resolution_stack", class_resolution_stack
        )
        object.__setattr__(
            self, "class_storage_ancestors", class_storage_ancestors
        )
        object.__setattr__(
            self, "declared_member_tables", declared_member_tables
        )
        object.__setattr__(
            self, "initializer_source_kind", initializer_source_kind
        )
        object.__setattr__(
            self, "resolve_class_structure", resolve_class_structure
        )
        object.__setattr__(
            self,
            "resolve_effective_class_members",
            resolve_effective_class_members,
        )
        object.__setattr__(self, "set_class", set_class)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context", context)
        object.__setattr__(
            self,
            "free_register_exception_types",
            free_register_exception_types,
        )
