"""
title: Explicit ExpressionClassAccess semantic dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import astx

from public import private

from irx.analysis.context import SemanticContext
from irx.analysis.dependencies.callbacks import (
    FileArgumentCheck,
    ModuleNamespaceNameCallback,
    RequireValueExpressionCallback,
    ResolveBaseAccessClassesCallback,
    ResolveClassAttributeMemberCallback,
    ResolveClassFieldSlotCallback,
    ResolveClassFromTypeCallback,
    ResolveMethodOverloadCallback,
    ResolveModuleMemberBindingCallback,
    ResolveNamedClassCallback,
    ResolveStructFromTypeCallback,
    SetModuleMemberResolutionCallback,
)
from irx.analysis.resolved_nodes import (
    CallResolution,
    ResolvedBaseClassFieldAccess,
    ResolvedClassConstruction,
    ResolvedClassFieldAccess,
    ResolvedFieldAccess,
    ResolvedMethodCall,
    ResolvedStaticClassFieldAccess,
    ResourceOwnership,
    SemanticClass,
    SemanticClassMember,
    SemanticClassStaticStorage,
    SemanticFunction,
    SemanticInfo,
    SemanticModule,
    SemanticStruct,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass(frozen=True, init=False)
class ExpressionClassAccessAnalysisServices:
    """
    title: Explicit dependencies for ExpressionClassAccessAnalysis.
    attributes:
      expr_type:
        type: Callable[[astx.AST | None], astx.DataType | None]
      member_display_name:
        type: Callable[[SemanticClassMember], str]
      member_is_accessible:
        type: Callable[[SemanticClassMember], bool]
      module_namespace:
        type: Callable[[astx.AST], SemanticModule | None]
      module_namespace_name:
        type: ModuleNamespaceNameCallback
      require_value_expression:
        type: RequireValueExpressionCallback
      resolve_base_access_classes:
        type: ResolveBaseAccessClassesCallback
      resolve_call_resource_ownership:
        type: Callable[[astx.AST, list[astx.AST], astx.DataType | None], None]
      resolve_class_attribute_member:
        type: ResolveClassAttributeMemberCallback
      resolve_class_definition:
        type: Callable[[SemanticClass], SemanticClass]
      resolve_class_field_slot:
        type: ResolveClassFieldSlotCallback
      resolve_class_from_type:
        type: ResolveClassFromTypeCallback
      resolve_method_overload:
        type: ResolveMethodOverloadCallback
      resolve_module_member_binding:
        type: ResolveModuleMemberBindingCallback
      resolve_module_namespace_call:
        type: >-
          Callable[[astx.MethodCall, SemanticModule, list[astx.DataType |
          None]], None]
      resolve_named_class:
        type: ResolveNamedClassCallback
      resolve_static_class_storage:
        type: >-
          Callable[[SemanticClass, SemanticClassMember, str],
          SemanticClassStaticStorage]
      resolve_struct_from_type:
        type: ResolveStructFromTypeCallback
      resolve_template_method_call_target:
        type: >-
          Callable[[SemanticFunction, SemanticFunction, list[astx.DataType |
          None], astx.AST], SemanticFunction | None]
      semantic:
        type: Callable[[astx.AST], SemanticInfo]
      set_base_class_field_access:
        type: Callable[[astx.AST, ResolvedBaseClassFieldAccess | None], None]
      set_call:
        type: >-
          Callable[[astx.AST, CallResolution | None], CallResolution | None]
      set_class:
        type: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
      set_class_construction:
        type: Callable[[astx.AST, ResolvedClassConstruction | None], None]
      set_class_field_access:
        type: Callable[[astx.AST, ResolvedClassFieldAccess | None], None]
      set_field_access:
        type: Callable[[astx.AST, ResolvedFieldAccess | None], None]
      set_method_call:
        type: Callable[[astx.AST, ResolvedMethodCall | None], None]
      set_module_member_resolution:
        type: SetModuleMemberResolutionCallback
      set_resource_ownership:
        type: >-
          Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership |
          None]
      set_static_class_field_access:
        type: Callable[[astx.AST, ResolvedStaticClassFieldAccess | None], None]
      set_struct:
        type: >-
          Callable[[astx.AST, SemanticStruct | None], SemanticStruct | None]
      set_type:
        type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
      specialization_bindings_map:
        type: Callable[[SemanticFunction], dict[str, astx.DataType]]
      specialize_signature:
        type: >-
          Callable[[SemanticFunction, dict[str, astx.DataType]],
          SemanticFunction]
      visible_method_function:
        type: Callable[[SemanticClass, SemanticClassMember], SemanticFunction]
      context:
        type: SemanticContext
      visit:
        type: Callable[[astx.AST], None]
      free_is_native_file_class:
        type: Callable[[SemanticClass], bool]
      free_constructor_arguments:
        type: >-
          Callable[[astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
          SemanticClass], tuple[tuple[astx.DataType, Ellipsis], tuple[int,
          Ellipsis], tuple[astx.DataType, Ellipsis]]]
      free_reject_hook_call:
        type: Callable[[astx.AST, str], bool]
      free_resolve_public_file_construction:
        type: >-
          Callable[[astx.FunctionCall | astx.ClassConstruct | astx.MethodCall,
          SemanticClass], None]
      free_resolve_exception_construction:
        type: >-
          Callable[[astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
          SemanticClass], None]
      free_resolve_text_call:
        type: Callable[[astx.FunctionCall | astx.MethodCall], None]
      free_text_error:
        type: Callable[[astx.AST, str], None]
      free_resolve_file_method:
        type: Callable[[astx.MethodCall], None]
      free_validate_file_method_arguments:
        type: FileArgumentCheck
    """

    expr_type: Callable[[astx.AST | None], astx.DataType | None]
    member_display_name: Callable[[SemanticClassMember], str]
    member_is_accessible: Callable[[SemanticClassMember], bool]
    module_namespace: Callable[[astx.AST], SemanticModule | None]
    module_namespace_name: ModuleNamespaceNameCallback
    require_value_expression: RequireValueExpressionCallback
    resolve_base_access_classes: ResolveBaseAccessClassesCallback
    resolve_call_resource_ownership: Callable[
        [astx.AST, list[astx.AST], astx.DataType | None], None
    ]
    resolve_class_attribute_member: ResolveClassAttributeMemberCallback
    resolve_class_definition: Callable[[SemanticClass], SemanticClass]
    resolve_class_field_slot: ResolveClassFieldSlotCallback
    resolve_class_from_type: ResolveClassFromTypeCallback
    resolve_method_overload: ResolveMethodOverloadCallback
    resolve_module_member_binding: ResolveModuleMemberBindingCallback
    resolve_module_namespace_call: Callable[
        [astx.MethodCall, SemanticModule, list[astx.DataType | None]], None
    ]
    resolve_named_class: ResolveNamedClassCallback
    resolve_static_class_storage: Callable[
        [SemanticClass, SemanticClassMember, str], SemanticClassStaticStorage
    ]
    resolve_struct_from_type: ResolveStructFromTypeCallback
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
    set_base_class_field_access: Callable[
        [astx.AST, ResolvedBaseClassFieldAccess | None], None
    ]
    set_call: Callable[
        [astx.AST, CallResolution | None], CallResolution | None
    ]
    set_class: Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
    set_class_construction: Callable[
        [astx.AST, ResolvedClassConstruction | None], None
    ]
    set_class_field_access: Callable[
        [astx.AST, ResolvedClassFieldAccess | None], None
    ]
    set_field_access: Callable[[astx.AST, ResolvedFieldAccess | None], None]
    set_method_call: Callable[[astx.AST, ResolvedMethodCall | None], None]
    set_module_member_resolution: SetModuleMemberResolutionCallback
    set_resource_ownership: Callable[
        [astx.AST, ResourceOwnership | None], ResourceOwnership | None
    ]
    set_static_class_field_access: Callable[
        [astx.AST, ResolvedStaticClassFieldAccess | None], None
    ]
    set_struct: Callable[
        [astx.AST, SemanticStruct | None], SemanticStruct | None
    ]
    set_type: Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
    specialization_bindings_map: Callable[
        [SemanticFunction], dict[str, astx.DataType]
    ]
    specialize_signature: Callable[
        [SemanticFunction, dict[str, astx.DataType]], SemanticFunction
    ]
    visible_method_function: Callable[
        [SemanticClass, SemanticClassMember], SemanticFunction
    ]
    context: SemanticContext
    visit: Callable[[astx.AST], None]
    free_is_native_file_class: Callable[[SemanticClass], bool]
    free_constructor_arguments: Callable[
        [
            astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
            SemanticClass,
        ],
        tuple[
            tuple[astx.DataType, ...],
            tuple[int, ...],
            tuple[astx.DataType, ...],
        ],
    ]
    free_reject_hook_call: Callable[[astx.AST, str], bool]
    free_resolve_public_file_construction: Callable[
        [
            astx.FunctionCall | astx.ClassConstruct | astx.MethodCall,
            SemanticClass,
        ],
        None,
    ]
    free_resolve_exception_construction: Callable[
        [
            astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
            SemanticClass,
        ],
        None,
    ]
    free_resolve_text_call: Callable[
        [astx.FunctionCall | astx.MethodCall], None
    ]
    free_text_error: Callable[[astx.AST, str], None]
    free_resolve_file_method: Callable[[astx.MethodCall], None]
    free_validate_file_method_arguments: FileArgumentCheck

    def __init__(
        self,
        expr_type: Callable[[astx.AST | None], astx.DataType | None],
        member_display_name: Callable[[SemanticClassMember], str],
        member_is_accessible: Callable[[SemanticClassMember], bool],
        module_namespace: Callable[[astx.AST], SemanticModule | None],
        module_namespace_name: ModuleNamespaceNameCallback,
        require_value_expression: RequireValueExpressionCallback,
        resolve_base_access_classes: ResolveBaseAccessClassesCallback,
        resolve_call_resource_ownership: Callable[
            [astx.AST, list[astx.AST], astx.DataType | None], None
        ],
        resolve_class_attribute_member: ResolveClassAttributeMemberCallback,
        resolve_class_definition: Callable[[SemanticClass], SemanticClass],
        resolve_class_field_slot: ResolveClassFieldSlotCallback,
        resolve_class_from_type: ResolveClassFromTypeCallback,
        resolve_method_overload: ResolveMethodOverloadCallback,
        resolve_module_member_binding: ResolveModuleMemberBindingCallback,
        resolve_module_namespace_call: Callable[
            [astx.MethodCall, SemanticModule, list[astx.DataType | None]], None
        ],
        resolve_named_class: ResolveNamedClassCallback,
        resolve_static_class_storage: Callable[
            [SemanticClass, SemanticClassMember, str],
            SemanticClassStaticStorage,
        ],
        resolve_struct_from_type: ResolveStructFromTypeCallback,
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
        set_base_class_field_access: Callable[
            [astx.AST, ResolvedBaseClassFieldAccess | None], None
        ],
        set_call: Callable[
            [astx.AST, CallResolution | None], CallResolution | None
        ],
        set_class: Callable[
            [astx.AST, SemanticClass | None], SemanticClass | None
        ],
        set_class_construction: Callable[
            [astx.AST, ResolvedClassConstruction | None], None
        ],
        set_class_field_access: Callable[
            [astx.AST, ResolvedClassFieldAccess | None], None
        ],
        set_field_access: Callable[
            [astx.AST, ResolvedFieldAccess | None], None
        ],
        set_method_call: Callable[[astx.AST, ResolvedMethodCall | None], None],
        set_module_member_resolution: SetModuleMemberResolutionCallback,
        set_resource_ownership: Callable[
            [astx.AST, ResourceOwnership | None], ResourceOwnership | None
        ],
        set_static_class_field_access: Callable[
            [astx.AST, ResolvedStaticClassFieldAccess | None], None
        ],
        set_struct: Callable[
            [astx.AST, SemanticStruct | None], SemanticStruct | None
        ],
        set_type: Callable[
            [astx.AST, astx.DataType | None], astx.DataType | None
        ],
        specialization_bindings_map: Callable[
            [SemanticFunction], dict[str, astx.DataType]
        ],
        specialize_signature: Callable[
            [SemanticFunction, dict[str, astx.DataType]], SemanticFunction
        ],
        visible_method_function: Callable[
            [SemanticClass, SemanticClassMember], SemanticFunction
        ],
        context: SemanticContext,
        visit: Callable[[astx.AST], None],
        free_is_native_file_class: Callable[[SemanticClass], bool],
        free_constructor_arguments: Callable[
            [
                astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
                SemanticClass,
            ],
            tuple[
                tuple[astx.DataType, ...],
                tuple[int, ...],
                tuple[astx.DataType, ...],
            ],
        ],
        free_reject_hook_call: Callable[[astx.AST, str], bool],
        free_resolve_public_file_construction: Callable[
            [
                astx.FunctionCall | astx.ClassConstruct | astx.MethodCall,
                SemanticClass,
            ],
            None,
        ],
        free_resolve_exception_construction: Callable[
            [
                astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
                SemanticClass,
            ],
            None,
        ],
        free_resolve_text_call: Callable[
            [astx.FunctionCall | astx.MethodCall], None
        ],
        free_text_error: Callable[[astx.AST, str], None],
        free_resolve_file_method: Callable[[astx.MethodCall], None],
        free_validate_file_method_arguments: FileArgumentCheck,
    ) -> None:
        """
        title: Validate and bind this feature's explicit dependencies.
        parameters:
          expr_type:
            type: Callable[[astx.AST | None], astx.DataType | None]
          member_display_name:
            type: Callable[[SemanticClassMember], str]
          member_is_accessible:
            type: Callable[[SemanticClassMember], bool]
          module_namespace:
            type: Callable[[astx.AST], SemanticModule | None]
          module_namespace_name:
            type: ModuleNamespaceNameCallback
          require_value_expression:
            type: RequireValueExpressionCallback
          resolve_base_access_classes:
            type: ResolveBaseAccessClassesCallback
          resolve_call_resource_ownership:
            type: >-
              Callable[[astx.AST, list[astx.AST], astx.DataType | None], None]
          resolve_class_attribute_member:
            type: ResolveClassAttributeMemberCallback
          resolve_class_definition:
            type: Callable[[SemanticClass], SemanticClass]
          resolve_class_field_slot:
            type: ResolveClassFieldSlotCallback
          resolve_class_from_type:
            type: ResolveClassFromTypeCallback
          resolve_method_overload:
            type: ResolveMethodOverloadCallback
          resolve_module_member_binding:
            type: ResolveModuleMemberBindingCallback
          resolve_module_namespace_call:
            type: >-
              Callable[[astx.MethodCall, SemanticModule, list[astx.DataType |
              None]], None]
          resolve_named_class:
            type: ResolveNamedClassCallback
          resolve_static_class_storage:
            type: >-
              Callable[[SemanticClass, SemanticClassMember, str],
              SemanticClassStaticStorage]
          resolve_struct_from_type:
            type: ResolveStructFromTypeCallback
          resolve_template_method_call_target:
            type: >-
              Callable[[SemanticFunction, SemanticFunction, list[astx.DataType
              | None], astx.AST], SemanticFunction | None]
          semantic:
            type: Callable[[astx.AST], SemanticInfo]
          set_base_class_field_access:
            type: >-
              Callable[[astx.AST, ResolvedBaseClassFieldAccess | None], None]
          set_call:
            type: >-
              Callable[[astx.AST, CallResolution | None], CallResolution |
              None]
          set_class:
            type: >-
              Callable[[astx.AST, SemanticClass | None], SemanticClass | None]
          set_class_construction:
            type: Callable[[astx.AST, ResolvedClassConstruction | None], None]
          set_class_field_access:
            type: Callable[[astx.AST, ResolvedClassFieldAccess | None], None]
          set_field_access:
            type: Callable[[astx.AST, ResolvedFieldAccess | None], None]
          set_method_call:
            type: Callable[[astx.AST, ResolvedMethodCall | None], None]
          set_module_member_resolution:
            type: SetModuleMemberResolutionCallback
          set_resource_ownership:
            type: >-
              Callable[[astx.AST, ResourceOwnership | None], ResourceOwnership
              | None]
          set_static_class_field_access:
            type: >-
              Callable[[astx.AST, ResolvedStaticClassFieldAccess | None], None]
          set_struct:
            type: >-
              Callable[[astx.AST, SemanticStruct | None], SemanticStruct |
              None]
          set_type:
            type: >-
              Callable[[astx.AST, astx.DataType | None], astx.DataType | None]
          specialization_bindings_map:
            type: Callable[[SemanticFunction], dict[str, astx.DataType]]
          specialize_signature:
            type: >-
              Callable[[SemanticFunction, dict[str, astx.DataType]],
              SemanticFunction]
          visible_method_function:
            type: >-
              Callable[[SemanticClass, SemanticClassMember], SemanticFunction]
          context:
            type: SemanticContext
          visit:
            type: Callable[[astx.AST], None]
          free_is_native_file_class:
            type: Callable[[SemanticClass], bool]
          free_constructor_arguments:
            type: >-
              Callable[[astx.ClassConstruct | astx.FunctionCall |
              astx.MethodCall, SemanticClass], tuple[tuple[astx.DataType,
              Ellipsis], tuple[int, Ellipsis], tuple[astx.DataType, Ellipsis]]]
          free_reject_hook_call:
            type: Callable[[astx.AST, str], bool]
          free_resolve_public_file_construction:
            type: >-
              Callable[[astx.FunctionCall | astx.ClassConstruct |
              astx.MethodCall, SemanticClass], None]
          free_resolve_exception_construction:
            type: >-
              Callable[[astx.ClassConstruct | astx.FunctionCall |
              astx.MethodCall, SemanticClass], None]
          free_resolve_text_call:
            type: Callable[[astx.FunctionCall | astx.MethodCall], None]
          free_text_error:
            type: Callable[[astx.AST, str], None]
          free_resolve_file_method:
            type: Callable[[astx.MethodCall], None]
          free_validate_file_method_arguments:
            type: FileArgumentCheck
        """
        object.__setattr__(self, "expr_type", expr_type)
        object.__setattr__(self, "member_display_name", member_display_name)
        object.__setattr__(self, "member_is_accessible", member_is_accessible)
        object.__setattr__(self, "module_namespace", module_namespace)
        object.__setattr__(
            self, "module_namespace_name", module_namespace_name
        )
        object.__setattr__(
            self, "require_value_expression", require_value_expression
        )
        object.__setattr__(
            self, "resolve_base_access_classes", resolve_base_access_classes
        )
        object.__setattr__(
            self,
            "resolve_call_resource_ownership",
            resolve_call_resource_ownership,
        )
        object.__setattr__(
            self,
            "resolve_class_attribute_member",
            resolve_class_attribute_member,
        )
        object.__setattr__(
            self, "resolve_class_definition", resolve_class_definition
        )
        object.__setattr__(
            self, "resolve_class_field_slot", resolve_class_field_slot
        )
        object.__setattr__(
            self, "resolve_class_from_type", resolve_class_from_type
        )
        object.__setattr__(
            self, "resolve_method_overload", resolve_method_overload
        )
        object.__setattr__(
            self,
            "resolve_module_member_binding",
            resolve_module_member_binding,
        )
        object.__setattr__(
            self,
            "resolve_module_namespace_call",
            resolve_module_namespace_call,
        )
        object.__setattr__(self, "resolve_named_class", resolve_named_class)
        object.__setattr__(
            self, "resolve_static_class_storage", resolve_static_class_storage
        )
        object.__setattr__(
            self, "resolve_struct_from_type", resolve_struct_from_type
        )
        object.__setattr__(
            self,
            "resolve_template_method_call_target",
            resolve_template_method_call_target,
        )
        object.__setattr__(self, "semantic", semantic)
        object.__setattr__(
            self, "set_base_class_field_access", set_base_class_field_access
        )
        object.__setattr__(self, "set_call", set_call)
        object.__setattr__(self, "set_class", set_class)
        object.__setattr__(
            self, "set_class_construction", set_class_construction
        )
        object.__setattr__(
            self, "set_class_field_access", set_class_field_access
        )
        object.__setattr__(self, "set_field_access", set_field_access)
        object.__setattr__(self, "set_method_call", set_method_call)
        object.__setattr__(
            self, "set_module_member_resolution", set_module_member_resolution
        )
        object.__setattr__(
            self, "set_resource_ownership", set_resource_ownership
        )
        object.__setattr__(
            self,
            "set_static_class_field_access",
            set_static_class_field_access,
        )
        object.__setattr__(self, "set_struct", set_struct)
        object.__setattr__(self, "set_type", set_type)
        object.__setattr__(
            self, "specialization_bindings_map", specialization_bindings_map
        )
        object.__setattr__(self, "specialize_signature", specialize_signature)
        object.__setattr__(
            self, "visible_method_function", visible_method_function
        )
        object.__setattr__(self, "context", context)
        object.__setattr__(self, "visit", visit)
        object.__setattr__(
            self, "free_is_native_file_class", free_is_native_file_class
        )
        object.__setattr__(
            self, "free_constructor_arguments", free_constructor_arguments
        )
        object.__setattr__(
            self, "free_reject_hook_call", free_reject_hook_call
        )
        object.__setattr__(
            self,
            "free_resolve_public_file_construction",
            free_resolve_public_file_construction,
        )
        object.__setattr__(
            self,
            "free_resolve_exception_construction",
            free_resolve_exception_construction,
        )
        object.__setattr__(
            self, "free_resolve_text_call", free_resolve_text_call
        )
        object.__setattr__(self, "free_text_error", free_text_error)
        object.__setattr__(
            self, "free_resolve_file_method", free_resolve_file_method
        )
        object.__setattr__(
            self,
            "free_validate_file_method_arguments",
            free_validate_file_method_arguments,
        )
