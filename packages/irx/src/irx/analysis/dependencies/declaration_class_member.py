"""
title: Explicit DeclarationClassMember semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.bindings import VisibleBindings
from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    MakeLoweredMethodFunctionCallback,
    MethodCallKeyFromSignatureCallback,
    MethodSignatureKeyCallback,
    RequireValueExpressionCallback,
    ResolveDeclaredTypeCallback,
)
from irx.analysis.factories import SemanticEntityFactory
from irx.analysis.registry import SemanticRegistry
from irx.analysis.resolved_nodes import (
    FunctionSignature,
    ResourceOwnership,
    SemanticClass,
    SemanticClassMember,
    SemanticFunction,
    SemanticInfo,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class DeclarationClassMemberAnalysisServices:
    """
    title: Explicit dependencies for DeclarationClassMemberAnalysis.
    attributes:
      analyze_class_method_body:
        type: Callable[[SemanticClass, SemanticClassMember], None]
      ancestor_declared_attributes:
        type: >-
          Callable[[tuple[SemanticClass, Ellipsis]], dict[str,
          tuple[SemanticClassMember, Ellipsis]]]
      ancestor_declared_method_groups:
        type: >-
          Callable[[tuple[SemanticClass, Ellipsis]], dict[str,
          tuple[SemanticClassMember, Ellipsis]]]
      attribute_is_static:
        type: Callable[[astx.VariableDeclaration], bool]
      class_resolution_stack:
        type: Callable[[], list[SemanticClass]]
      compute_class_mro:
        type: >-
          Callable[[SemanticClass, tuple[SemanticClass, Ellipsis]],
          tuple[SemanticClass, Ellipsis]]
      declared_member_tables:
        type: >-
          Callable[[tuple[SemanticClassMember, Ellipsis]], tuple[dict[str,
          SemanticClassMember], dict[str, tuple[SemanticClassMember,
          Ellipsis]]]]
      dominant_inherited_method:
        type: >-
          Callable[[tuple[SemanticClassMember, Ellipsis]], SemanticClassMember
          | None]
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      finalize_registered_class_layouts:
        type: Callable[[], None]
      make_lowered_method_function:
        type: MakeLoweredMethodFunctionCallback
      member_call_key:
        type: Callable[[SemanticClassMember], str]
      method_call_key_from_signature:
        type: MethodCallKeyFromSignatureCallback
      method_is_abstract:
        type: Callable[[astx.FunctionDef], bool]
      method_is_static:
        type: Callable[[astx.FunctionDef], bool]
      method_signature_key:
        type: MethodSignatureKeyCallback
      normalize_class_method_signature:
        type: Callable[[SemanticClass, astx.FunctionDef], FunctionSignature]
      require_value_expression:
        type: RequireValueExpressionCallback
      resolve_class_bases:
        type: Callable[[SemanticClass], tuple[SemanticClass, Ellipsis]]
      resolve_declared_type:
        type: ResolveDeclaredTypeCallback
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_class:
        type: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
      set_function:
        type: >-
          Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
          None]
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      shared_class_ancestors:
        type: >-
          Callable[[tuple[SemanticClass, Ellipsis], tuple[SemanticClass,
          Ellipsis]], tuple[SemanticClass, Ellipsis]]
      static_initializer_is_supported:
        type: Callable[[astx.AST | None], bool]
      visibility_rank:
        type: Callable[[astx.VisibilityKind], int]
      bindings:
        type: VisibleBindings
      context:
        type: SemanticContext
      factory:
        type: SemanticEntityFactory
      registry:
        type: SemanticRegistry
      visit:
        type: Callable[[astx.AST], None]
      free_validate_file_fields:
        type: Callable[[SemanticClass], None]
      free_validate_hook:
        type: Callable[[astx.FunctionDef], None]
      free_is_native_file_class:
        type: Callable[[SemanticClass], bool]
    """

    analyze_class_method_body: Callable[
        [SemanticClass, SemanticClassMember], None
    ]
    ancestor_declared_attributes: Callable[
        [tuple[SemanticClass, ...]], dict[str, tuple[SemanticClassMember, ...]]
    ]
    ancestor_declared_method_groups: Callable[
        [tuple[SemanticClass, ...]], dict[str, tuple[SemanticClassMember, ...]]
    ]
    attribute_is_static: Callable[[astx.VariableDeclaration], bool]
    class_resolution_stack: Callable[[], list[SemanticClass]]
    compute_class_mro: Callable[
        [SemanticClass, tuple[SemanticClass, ...]], tuple[SemanticClass, ...]
    ]
    declared_member_tables: Callable[
        [tuple[SemanticClassMember, ...]],
        tuple[
            dict[str, SemanticClassMember],
            dict[str, tuple[SemanticClassMember, ...]],
        ],
    ]
    dominant_inherited_method: Callable[
        [tuple[SemanticClassMember, ...]], SemanticClassMember | None
    ]
    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    finalize_registered_class_layouts: Callable[[], None]
    make_lowered_method_function: MakeLoweredMethodFunctionCallback
    member_call_key: Callable[[SemanticClassMember], str]
    method_call_key_from_signature: MethodCallKeyFromSignatureCallback
    method_is_abstract: Callable[[astx.FunctionDef], bool]
    method_is_static: Callable[[astx.FunctionDef], bool]
    method_signature_key: MethodSignatureKeyCallback
    normalize_class_method_signature: Callable[
        [SemanticClass, astx.FunctionDef], FunctionSignature
    ]
    require_value_expression: RequireValueExpressionCallback
    resolve_class_bases: Callable[[SemanticClass], tuple[SemanticClass, ...]]
    resolve_declared_type: ResolveDeclaredTypeCallback
    semantic: Callable[[astx.AST], SemanticInfo]
    set_class: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
    set_function: Callable[
        [astx.AST, SemanticFunction | None], SemanticFunction | None
    ]
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    shared_class_ancestors: Callable[
        [tuple[SemanticClass, ...], tuple[SemanticClass, ...]],
        tuple[SemanticClass, ...],
    ]
    static_initializer_is_supported: Callable[[astx.AST | None], bool]
    visibility_rank: Callable[[astx.VisibilityKind], int]
    bindings: VisibleBindings
    context: SemanticContext
    factory: SemanticEntityFactory
    registry: SemanticRegistry
    visit: Callable[[astx.AST], None]
    free_validate_file_fields: Callable[[SemanticClass], None]
    free_validate_hook: Callable[[astx.FunctionDef], None]
    free_is_native_file_class: Callable[[SemanticClass], bool]

    def __init__(
        self,
        analyze_class_method_body: Callable[
            [SemanticClass, SemanticClassMember], None
        ],
        ancestor_declared_attributes: Callable[
            [tuple[SemanticClass, ...]],
            dict[str, tuple[SemanticClassMember, ...]],
        ],
        ancestor_declared_method_groups: Callable[
            [tuple[SemanticClass, ...]],
            dict[str, tuple[SemanticClassMember, ...]],
        ],
        attribute_is_static: Callable[[astx.VariableDeclaration], bool],
        class_resolution_stack: Callable[[], list[SemanticClass]],
        compute_class_mro: Callable[
            [SemanticClass, tuple[SemanticClass, ...]],
            tuple[SemanticClass, ...],
        ],
        declared_member_tables: Callable[
            [tuple[SemanticClassMember, ...]],
            tuple[
                dict[str, SemanticClassMember],
                dict[str, tuple[SemanticClassMember, ...]],
            ],
        ],
        dominant_inherited_method: Callable[
            [tuple[SemanticClassMember, ...]], SemanticClassMember | None
        ],
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        finalize_registered_class_layouts: Callable[[], None],
        make_lowered_method_function: MakeLoweredMethodFunctionCallback,
        member_call_key: Callable[[SemanticClassMember], str],
        method_call_key_from_signature: MethodCallKeyFromSignatureCallback,
        method_is_abstract: Callable[[astx.FunctionDef], bool],
        method_is_static: Callable[[astx.FunctionDef], bool],
        method_signature_key: MethodSignatureKeyCallback,
        normalize_class_method_signature: Callable[
            [SemanticClass, astx.FunctionDef], FunctionSignature
        ],
        require_value_expression: RequireValueExpressionCallback,
        resolve_class_bases: Callable[
            [SemanticClass], tuple[SemanticClass, ...]
        ],
        resolve_declared_type: ResolveDeclaredTypeCallback,
        semantic: Callable[[astx.AST], SemanticInfo],
        set_class: Callable[
            [astx.AST, SemanticClass | None], SemanticClass | None
        ],
        set_function: Callable[
            [astx.AST, SemanticFunction | None], SemanticFunction | None
        ],
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        shared_class_ancestors: Callable[
            [tuple[SemanticClass, ...], tuple[SemanticClass, ...]],
            tuple[SemanticClass, ...],
        ],
        static_initializer_is_supported: Callable[[astx.AST | None], bool],
        visibility_rank: Callable[[astx.VisibilityKind], int],
        bindings: VisibleBindings,
        context: SemanticContext,
        factory: SemanticEntityFactory,
        registry: SemanticRegistry,
        visit: Callable[[astx.AST], None],
        free_validate_file_fields: Callable[[SemanticClass], None],
        free_validate_hook: Callable[[astx.FunctionDef], None],
        free_is_native_file_class: Callable[[SemanticClass], bool],
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          analyze_class_method_body:
            type: Callable[[SemanticClass, SemanticClassMember], None]
          ancestor_declared_attributes:
            type: >-
              Callable[[tuple[SemanticClass, Ellipsis]], dict[str,
              tuple[SemanticClassMember, Ellipsis]]]
          ancestor_declared_method_groups:
            type: >-
              Callable[[tuple[SemanticClass, Ellipsis]], dict[str,
              tuple[SemanticClassMember, Ellipsis]]]
          attribute_is_static:
            type: Callable[[astx.VariableDeclaration], bool]
          class_resolution_stack:
            type: Callable[[], list[SemanticClass]]
          compute_class_mro:
            type: >-
              Callable[[SemanticClass, tuple[SemanticClass, Ellipsis]],
              tuple[SemanticClass, Ellipsis]]
          declared_member_tables:
            type: >-
              Callable[[tuple[SemanticClassMember, Ellipsis]], tuple[dict[str,
              SemanticClassMember], dict[str, tuple[SemanticClassMember,
              Ellipsis]]]]
          dominant_inherited_method:
            type: >-
              Callable[[tuple[SemanticClassMember, Ellipsis]],
              SemanticClassMember | None]
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          finalize_registered_class_layouts:
            type: Callable[[], None]
          make_lowered_method_function:
            type: MakeLoweredMethodFunctionCallback
          member_call_key:
            type: Callable[[SemanticClassMember], str]
          method_call_key_from_signature:
            type: MethodCallKeyFromSignatureCallback
          method_is_abstract:
            type: Callable[[astx.FunctionDef], bool]
          method_is_static:
            type: Callable[[astx.FunctionDef], bool]
          method_signature_key:
            type: MethodSignatureKeyCallback
          normalize_class_method_signature:
            type: >-
              Callable[[SemanticClass, astx.FunctionDef], FunctionSignature]
          require_value_expression:
            type: RequireValueExpressionCallback
          resolve_class_bases:
            type: Callable[[SemanticClass], tuple[SemanticClass, Ellipsis]]
          resolve_declared_type:
            type: ResolveDeclaredTypeCallback
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_class:
            type: >-
              Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
          set_function:
            type: >-
              Callable[[astx.AST, SemanticFunction | None], SemanticFunction |
              None]
          set_resource_ownership:
            type: >-
              Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership
              | None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          shared_class_ancestors:
            type: >-
              Callable[[tuple[SemanticClass, Ellipsis], tuple[SemanticClass,
              Ellipsis]], tuple[SemanticClass, Ellipsis]]
          static_initializer_is_supported:
            type: Callable[[astx.AST | None], bool]
          visibility_rank:
            type: Callable[[astx.VisibilityKind], int]
          bindings:
            type: VisibleBindings
          context:
            type: SemanticContext
          factory:
            type: SemanticEntityFactory
          registry:
            type: SemanticRegistry
          visit:
            type: Callable[[astx.AST], None]
          free_validate_file_fields:
            type: Callable[[SemanticClass], None]
          free_validate_hook:
            type: Callable[[astx.FunctionDef], None]
          free_is_native_file_class:
            type: Callable[[SemanticClass], bool]
        """
        object.__setattr__(
            self, "analyze_class_method_body", analyze_class_method_body
        )
        object.__setattr__(
            self, "ancestor_declared_attributes", ancestor_declared_attributes
        )
        object.__setattr__(
            self,
            "ancestor_declared_method_groups",
            ancestor_declared_method_groups,
        )
        object.__setattr__(self, "attribute_is_static", attribute_is_static)
        object.__setattr__(
            self, "class_resolution_stack", class_resolution_stack
        )
        object.__setattr__(self, "compute_class_mro", compute_class_mro)
        object.__setattr__(
            self, "declared_member_tables", declared_member_tables
        )
        object.__setattr__(
            self, "dominant_inherited_method", dominant_inherited_method
        )
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(
            self,
            "finalize_registered_class_layouts",
            finalize_registered_class_layouts,
        )
        object.__setattr__(
            self, "make_lowered_method_function", make_lowered_method_function
        )
        object.__setattr__(self, "member_call_key", member_call_key)
        object.__setattr__(
            self,
            "method_call_key_from_signature",
            method_call_key_from_signature,
        )
        object.__setattr__(self, "method_is_abstract", method_is_abstract)
        object.__setattr__(self, "method_is_static", method_is_static)
        object.__setattr__(self, "method_signature_key", method_signature_key)
        object.__setattr__(
            self,
            "normalize_class_method_signature",
            normalize_class_method_signature,
        )
        object.__setattr__(
            self, "require_value_expression", require_value_expression
        )
        object.__setattr__(self, "resolve_class_bases", resolve_class_bases)
        object.__setattr__(
            self, "resolve_declared_type", resolve_declared_type
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(self, "set_class", set_class)
        object.__setattr__(self, "set_function", set_function)
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(
            self, "shared_class_ancestors", shared_class_ancestors
        )
        object.__setattr__(
            self,
            "static_initializer_is_supported",
            static_initializer_is_supported,
        )
        object.__setattr__(self, "visibility_rank", visibility_rank)
        object.__setattr__(self, "bindings", bindings)
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "registry", registry)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self, "free_validate_file_fields", free_validate_file_fields
        )
        object.__setattr__(self, "free_validate_hook", free_validate_hook)
        object.__setattr__(
            self, "free_is_native_file_class", free_is_native_file_class
        )
