# ruff: noqa: PLW0108
# Deferred callbacks resolve forward references after graph construction.
"""
title: Explicit compiler-local graph of semantic feature implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from public import private

from irx.analysis.arrow_conversion import arrow_local as free_arrow_local
from irx.analysis.arrow_conversion import (
    resolve_arrow_cast as free_resolve_arrow_cast,
)
from irx.analysis.arrow_conversion import (
    resolve_arrow_store as free_resolve_arrow_store,
)
from irx.analysis.builtin_file import (
    is_native_file_class as free_is_native_file_class,
)
from irx.analysis.builtin_file import (
    reject_native_file_cast as free_reject_native_file_cast,
)
from irx.analysis.builtin_file import (
    resolve_public_file_construction as free_resolve_public_file_construction,
)
from irx.analysis.class_lifecycle import class_local as free_class_local
from irx.analysis.class_lifecycle import (
    constructor_arguments as free_constructor_arguments,
)
from irx.analysis.class_lifecycle import (
    lifecycle_error as free_lifecycle_error,
)
from irx.analysis.class_lifecycle import (
    reject_hook_call as free_reject_hook_call,
)
from irx.analysis.class_lifecycle import resolve_store as free_resolve_store
from irx.analysis.class_lifecycle import (
    validate_file_fields as free_validate_file_fields,
)
from irx.analysis.class_lifecycle import validate_hook as free_validate_hook
from irx.analysis.dependencies.class_member_formatting import (
    ClassMemberFormattingAnalysisServices,
)
from irx.analysis.dependencies.control_flow import ControlFlowAnalysisServices
from irx.analysis.dependencies.declaration_block import (
    DeclarationBlockAnalysisServices,
)
from irx.analysis.dependencies.declaration_class_layout import (
    DeclarationClassLayoutAnalysisServices,
)
from irx.analysis.dependencies.declaration_class_member import (
    DeclarationClassMemberAnalysisServices,
)
from irx.analysis.dependencies.declaration_class_method import (
    DeclarationClassMethodAnalysisServices,
)
from irx.analysis.dependencies.declaration_class_support import (
    DeclarationClassSupportAnalysisServices,
)
from irx.analysis.dependencies.declaration_function import (
    DeclarationFunctionAnalysisServices,
)
from irx.analysis.dependencies.declaration_struct import (
    DeclarationStructAnalysisServices,
)
from irx.analysis.dependencies.exception import ExceptionAnalysisServices
from irx.analysis.dependencies.expression_array import (
    ExpressionArrayAnalysisServices,
)
from irx.analysis.dependencies.expression_buffer_view import (
    ExpressionBufferViewAnalysisServices,
)
from irx.analysis.dependencies.expression_class_access import (
    ExpressionClassAccessAnalysisServices,
)
from irx.analysis.dependencies.expression_class_support import (
    ExpressionClassSupportAnalysisServices,
)
from irx.analysis.dependencies.expression_data_frame import (
    ExpressionDataFrameAnalysisServices,
)
from irx.analysis.dependencies.expression_list import (
    ExpressionListAnalysisServices,
)
from irx.analysis.dependencies.expression_literal import (
    ExpressionLiteralAnalysisServices,
)
from irx.analysis.dependencies.expression_module import (
    ExpressionModuleAnalysisServices,
)
from irx.analysis.dependencies.expression_mutation import (
    ExpressionMutationAnalysisServices,
)
from irx.analysis.dependencies.expression_operator import (
    ExpressionOperatorAnalysisServices,
)
from irx.analysis.dependencies.expression_tensor import (
    ExpressionTensorAnalysisServices,
)
from irx.analysis.dependencies.expression_tensor_buffer_support import (
    ExpressionTensorBufferSupportAnalysisServices,
)
from irx.analysis.dependencies.imports import ImportAnalysisServices
from irx.analysis.dependencies.template_analysis import (
    TemplateAnalysisAnalysisServices,
)
from irx.analysis.dependencies.template_build import (
    TemplateBuildAnalysisServices,
)
from irx.analysis.dependencies.template_resolution import (
    TemplateResolutionAnalysisServices,
)
from irx.analysis.dependencies.template_state import (
    TemplateStateAnalysisServices,
)
from irx.analysis.dependencies.template_support import (
    TemplateSupportAnalysisServices,
)
from irx.analysis.exception_types import (
    exception_error as free_exception_error,
)
from irx.analysis.exception_types import (
    register_exception_types as free_register_exception_types,
)
from irx.analysis.exception_types import (
    resolve_exception_construction as free_resolve_exception_construction,
)
from irx.analysis.file_io import resolve_file_local as free_resolve_file_local
from irx.analysis.file_io import (
    resolve_file_method as free_resolve_file_method,
)
from irx.analysis.file_io import resolve_file_open as free_resolve_file_open
from irx.analysis.file_io import (
    validate_file_method_arguments as free_validate_file_method_arguments,
)
from irx.analysis.handlers._declarations.blocks import DeclarationBlockAnalysis
from irx.analysis.handlers._declarations.class_layout import (
    DeclarationClassLayoutAnalysis,
)
from irx.analysis.handlers._declarations.class_members import (
    DeclarationClassMemberAnalysis,
)
from irx.analysis.handlers._declarations.class_methods import (
    DeclarationClassMethodAnalysis,
)
from irx.analysis.handlers._declarations.class_support import (
    DeclarationClassSupportAnalysis,
)
from irx.analysis.handlers._declarations.functions import (
    DeclarationFunctionAnalysis,
)
from irx.analysis.handlers._declarations.structs import (
    DeclarationStructAnalysis,
)
from irx.analysis.handlers._expressions.arrays import ExpressionArrayAnalysis
from irx.analysis.handlers._expressions.buffer_views import (
    ExpressionBufferViewAnalysis,
)
from irx.analysis.handlers._expressions.class_access import (
    ExpressionClassAccessAnalysis,
)
from irx.analysis.handlers._expressions.class_support import (
    ExpressionClassSupportAnalysis,
)
from irx.analysis.handlers._expressions.dataframes import (
    ExpressionDataFrameAnalysis,
)
from irx.analysis.handlers._expressions.lists import ExpressionListAnalysis
from irx.analysis.handlers._expressions.literals import (
    ExpressionLiteralAnalysis,
)
from irx.analysis.handlers._expressions.modules import ExpressionModuleAnalysis
from irx.analysis.handlers._expressions.mutation import (
    ExpressionMutationAnalysis,
)
from irx.analysis.handlers._expressions.operators import (
    ExpressionOperatorAnalysis,
)
from irx.analysis.handlers._expressions.tensor_buffer_support import (
    ExpressionTensorBufferSupportAnalysis,
)
from irx.analysis.handlers._expressions.tensors import ExpressionTensorAnalysis
from irx.analysis.handlers._templates.analysis import TemplateAnalysisAnalysis
from irx.analysis.handlers._templates.build import TemplateBuildAnalysis
from irx.analysis.handlers._templates.resolution import (
    TemplateResolutionAnalysis,
)
from irx.analysis.handlers._templates.state import TemplateStateAnalysis
from irx.analysis.handlers._templates.support import TemplateSupportAnalysis
from irx.analysis.handlers.class_helpers import ClassMemberFormattingAnalysis
from irx.analysis.handlers.control_flow import ControlFlowAnalysis
from irx.analysis.handlers.exceptions import ExceptionAnalysis
from irx.analysis.handlers.imports import ImportAnalysis
from irx.analysis.nullable import nullable_error as free_nullable_error
from irx.analysis.nullable import (
    resolve_column_binary as free_resolve_column_binary,
)
from irx.analysis.nullable import (
    resolve_column_index as free_resolve_column_index,
)
from irx.analysis.nullable import (
    resolve_column_unary as free_resolve_column_unary,
)
from irx.analysis.nullable import (
    resolve_nullable_global as free_resolve_nullable_global,
)
from irx.analysis.nullable import (
    resolve_series_reduction as free_resolve_series_reduction,
)
from irx.analysis.nullable import set_operation as free_set_operation
from irx.analysis.parameters import (
    resolve_parameter_ownership as free_resolve_parameter_ownership,
)
from irx.analysis.sequences import (
    resolve_materialization as free_resolve_materialization,
)
from irx.analysis.text import resolve_text_call as free_resolve_text_call
from irx.analysis.text import (
    resolve_text_subscript as free_resolve_text_subscript,
)
from irx.analysis.text import set_text_operation as free_set_text_operation
from irx.analysis.text import text_error as free_text_error
from irx.extensions.nodes import (
    ScopedNodeDispatch,
)
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.analysis.handlers.base import SemanticAnalyzerCore


@private
@typechecked
class AnalysisFeatures:
    """
    title: Compose typed feature services without analyzer mixin inheritance.
    attributes:
      class_member_formatting:
        type: ClassMemberFormattingAnalysis
      exception:
        type: ExceptionAnalysis
      imports:
        type: ImportAnalysis
      control_flow:
        type: ControlFlowAnalysis
      declaration_class_support:
        type: DeclarationClassSupportAnalysis
      declaration_class_layout:
        type: DeclarationClassLayoutAnalysis
      declaration_function:
        type: DeclarationFunctionAnalysis
      declaration_class_method:
        type: DeclarationClassMethodAnalysis
      declaration_block:
        type: DeclarationBlockAnalysis
      declaration_struct:
        type: DeclarationStructAnalysis
      declaration_class_member:
        type: DeclarationClassMemberAnalysis
      template_support:
        type: TemplateSupportAnalysis
      template_build:
        type: TemplateBuildAnalysis
      template_state:
        type: TemplateStateAnalysis
      template:
        type: TemplateAnalysisAnalysis
      template_resolution:
        type: TemplateResolutionAnalysis
      expression_class_support:
        type: ExpressionClassSupportAnalysis
      expression_module:
        type: ExpressionModuleAnalysis
      expression_tensor_buffer_support:
        type: ExpressionTensorBufferSupportAnalysis
      expression_literal:
        type: ExpressionLiteralAnalysis
      expression_list:
        type: ExpressionListAnalysis
      expression_class_access:
        type: ExpressionClassAccessAnalysis
      expression_mutation:
        type: ExpressionMutationAnalysis
      expression_data_frame:
        type: ExpressionDataFrameAnalysis
      expression_buffer_view:
        type: ExpressionBufferViewAnalysis
      expression_operator:
        type: ExpressionOperatorAnalysis
      expression_tensor:
        type: ExpressionTensorAnalysis
      expression_array:
        type: ExpressionArrayAnalysis
      dispatch:
        type: ScopedNodeDispatch
    """

    class_member_formatting: ClassMemberFormattingAnalysis
    exception: ExceptionAnalysis
    imports: ImportAnalysis
    control_flow: ControlFlowAnalysis
    declaration_class_support: DeclarationClassSupportAnalysis
    declaration_class_layout: DeclarationClassLayoutAnalysis
    declaration_function: DeclarationFunctionAnalysis
    declaration_class_method: DeclarationClassMethodAnalysis
    declaration_block: DeclarationBlockAnalysis
    declaration_struct: DeclarationStructAnalysis
    declaration_class_member: DeclarationClassMemberAnalysis
    template_support: TemplateSupportAnalysis
    template_build: TemplateBuildAnalysis
    template_state: TemplateStateAnalysis
    template: TemplateAnalysisAnalysis
    template_resolution: TemplateResolutionAnalysis
    expression_class_support: ExpressionClassSupportAnalysis
    expression_module: ExpressionModuleAnalysis
    expression_tensor_buffer_support: ExpressionTensorBufferSupportAnalysis
    expression_literal: ExpressionLiteralAnalysis
    expression_list: ExpressionListAnalysis
    expression_class_access: ExpressionClassAccessAnalysis
    expression_mutation: ExpressionMutationAnalysis
    expression_data_frame: ExpressionDataFrameAnalysis
    expression_buffer_view: ExpressionBufferViewAnalysis
    expression_operator: ExpressionOperatorAnalysis
    expression_tensor: ExpressionTensorAnalysis
    expression_array: ExpressionArrayAnalysis
    dispatch: ScopedNodeDispatch

    def __init__(self, core: SemanticAnalyzerCore) -> None:
        """
        title: Bind explicit callbacks and construct fresh nominal dispatch.
        parameters:
          core:
            type: SemanticAnalyzerCore
        """
        self.class_member_formatting = ClassMemberFormattingAnalysis(
            ClassMemberFormattingAnalysisServices(
                context=core.context,
            )
        )
        self.exception = ExceptionAnalysis(
            ExceptionAnalysisServices(
                expr_type=core._expr_type,
                resolve_class_definition=(
                    lambda cls: (
                        self.declaration_class_member._resolve_class_definition(
                            cls
                        )
                    )
                ),
                semantic=core._semantic,
                set_class=core._set_class,
                set_resource_ownership=core._set_resource_ownership,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                bindings=core.bindings,
                context=core.context,
                factory=core.factory,
                visit=core.visit,
                free_exception_error=(
                    lambda node, message: free_exception_error(
                        core, node, message
                    )
                ),
            )
        )
        self.imports = ImportAnalysis(
            ImportAnalysisServices(
                current_module_key=core._current_module_key,
                imports_supported_here=core._imports_supported_here,
                set_class=core._set_class,
                set_function=core._set_function,
                set_imports=core._set_imports,
                set_module=core._set_module,
                set_struct=core._set_struct,
                set_type=core._set_type,
                bindings=core.bindings,
                context=core.context,
                factory=core.factory,
                session=core.session,
            )
        )
        self.control_flow = ControlFlowAnalysis(
            ControlFlowAnalysisServices(
                resolve_method_overload=(
                    lambda cls, name, types_, *, is_static, node: (
                        self.expression_class_support._resolve_method_overload(
                            cls, name, types_, is_static=is_static, node=node
                        )
                    )
                ),
                visible_method_function=(
                    lambda cls, member: (
                        self.expression_class_support._visible_method_function(
                            cls, member
                        )
                    )
                ),
                declare_iteration_target=core._declare_iteration_target,
                expr_type=core._expr_type,
                require_value_expression=core._require_value_expression,
                resolve_class_from_type=core._resolve_class_from_type,
                resolve_declared_type=core._resolve_declared_type,
                resolve_template_method_call_target=(
                    lambda fn, visible, types_, node: (
                        self.template_resolution._resolve_template_method_call_target(
                            fn, visible, types_, node
                        )
                    )
                ),
                semantic=core._semantic,
                set_context_manager=core._set_context_manager,
                set_iteration=core._set_iteration,
                set_operator=core._set_operator,
                set_resource_ownership=core._set_resource_ownership,
                set_return=core._set_return,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                set_yield=core._set_yield,
                specialization_bindings_map=(
                    lambda fn: (
                        self.template_support._specialization_bindings_map(fn)
                    )
                ),
                specialize_signature=(
                    lambda fn, bindings: (
                        self.template_support._specialize_signature(
                            fn, bindings
                        )
                    )
                ),
                context=core.context,
                registry=core.registry,
                visit=core.visit,
            )
        )
        self.declaration_class_support = DeclarationClassSupportAnalysis(
            DeclarationClassSupportAnalysisServices(
                member_owner_module_key=(
                    lambda member: (
                        self.class_member_formatting._member_owner_module_key(
                            member
                        )
                    )
                ),
                resolve_class_from_type=core._resolve_class_from_type,
                resolve_class_structure=(
                    lambda cls: (
                        self.declaration_class_member._resolve_class_structure(
                            cls
                        )
                    )
                ),
                context=core.context,
            )
        )
        self.declaration_class_layout = DeclarationClassLayoutAnalysis(
            DeclarationClassLayoutAnalysisServices(
                class_is_declared_abstract=(
                    lambda cls: (
                        self.declaration_class_support._class_is_declared_abstract(
                            cls
                        )
                    )
                ),
                class_resolution_stack=(
                    lambda: (
                        self.declaration_class_support._class_resolution_stack()
                    )
                ),
                class_storage_ancestors=(
                    lambda bases: (
                        self.declaration_class_support._class_storage_ancestors(
                            bases
                        )
                    )
                ),
                declared_member_tables=(
                    lambda declared_members: (
                        self.declaration_class_support._declared_member_tables(
                            declared_members
                        )
                    )
                ),
                initializer_source_kind=(
                    lambda value: (
                        self.declaration_class_support._initializer_source_kind(
                            value
                        )
                    )
                ),
                resolve_class_structure=(
                    lambda cls: (
                        self.declaration_class_member._resolve_class_structure(
                            cls
                        )
                    )
                ),
                resolve_effective_class_members=(
                    lambda cls, mro, members, groups: (
                        self.declaration_class_member._resolve_effective_class_members(
                            cls, mro, members, groups
                        )
                    )
                ),
                set_class=core._set_class,
                bindings=core.bindings,
                context=core.context,
                free_register_exception_types=(
                    lambda: free_register_exception_types(core)
                ),
            )
        )
        self.declaration_function = DeclarationFunctionAnalysis(
            DeclarationFunctionAnalysisServices(
                analyze_parameter_defaults=core._analyze_parameter_defaults,
                guarantees_return=core._guarantees_return,
                resolve_declared_type=core._resolve_declared_type,
                set_function=core._set_function,
                set_generator_function=core._set_generator_function,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                bindings=core.bindings,
                context=core.context,
                registry=core.registry,
                visit=core.visit,
                free_resolve_parameter_ownership=(
                    lambda arg_node, arg_symbol: (
                        free_resolve_parameter_ownership(
                            core, arg_node, arg_symbol
                        )
                    )
                ),
            )
        )
        self.declaration_class_method = DeclarationClassMethodAnalysis(
            DeclarationClassMethodAnalysisServices(
                analyze_function_template_specializations=(
                    lambda fn: (
                        self.template._analyze_function_template_specializations(
                            fn
                        )
                    )
                ),
                analyze_parameter_defaults=core._analyze_parameter_defaults,
                guarantees_return=core._guarantees_return,
                prepare_function_template_specializations=(
                    lambda fn: (
                        self.template._prepare_function_template_specializations(
                            fn
                        )
                    )
                ),
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                context=core.context,
                factory=core.factory,
                registry=core.registry,
                visit=core.visit,
                free_resolve_parameter_ownership=(
                    lambda arg_node, arg_symbol: (
                        free_resolve_parameter_ownership(
                            core, arg_node, arg_symbol
                        )
                    )
                ),
            )
        )
        self.declaration_block = DeclarationBlockAnalysis(
            DeclarationBlockAnalysisServices(
                expr_type=core._expr_type,
                predeclare_block_structs=core._predeclare_block_structs,
                require_value_expression=core._require_value_expression,
                resolve_declared_type=core._resolve_declared_type,
                semantic=core._semantic,
                set_resource_ownership=core._set_resource_ownership,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                visit_module=core._visit_module,
                context=core.context,
                registry=core.registry,
                visit=core.visit,
                free_resolve_nullable_global=(
                    lambda node: free_resolve_nullable_global(core, node)
                ),
                free_arrow_local=(
                    lambda node, symbol: free_arrow_local(core, node, symbol)
                ),
                free_class_local=(
                    lambda node, symbol: free_class_local(core, node, symbol)
                ),
                free_resolve_file_local=(
                    lambda node, symbol: free_resolve_file_local(
                        core, node, symbol
                    )
                ),
            )
        )
        self.declaration_struct = DeclarationStructAnalysis(
            DeclarationStructAnalysisServices(
                resolve_declared_type=core._resolve_declared_type,
                resolve_struct_from_type=core._resolve_struct_from_type,
                set_struct=core._set_struct,
                set_type=core._set_type,
                bindings=core.bindings,
                context=core.context,
                registry=core.registry,
            )
        )
        self.declaration_class_member = DeclarationClassMemberAnalysis(
            DeclarationClassMemberAnalysisServices(
                analyze_class_method_body=(
                    lambda cls, member: (
                        self.declaration_class_method._analyze_class_method_body(
                            cls, member
                        )
                    )
                ),
                ancestor_declared_attributes=(
                    lambda mro: (
                        self.declaration_class_support._ancestor_declared_attributes(
                            mro
                        )
                    )
                ),
                ancestor_declared_method_groups=(
                    lambda mro: (
                        self.declaration_class_support._ancestor_declared_method_groups(
                            mro
                        )
                    )
                ),
                attribute_is_static=(
                    lambda decl: (
                        self.declaration_class_support._attribute_is_static(
                            decl
                        )
                    )
                ),
                class_resolution_stack=(
                    lambda: (
                        self.declaration_class_support._class_resolution_stack()
                    )
                ),
                compute_class_mro=(
                    lambda cls, bases: (
                        self.declaration_class_support._compute_class_mro(
                            cls, bases
                        )
                    )
                ),
                declared_member_tables=(
                    lambda declared_members: (
                        self.declaration_class_support._declared_member_tables(
                            declared_members
                        )
                    )
                ),
                dominant_inherited_method=(
                    lambda candidates: (
                        self.declaration_class_support._dominant_inherited_method(
                            candidates
                        )
                    )
                ),
                expr_type=core._expr_type,
                finalize_registered_class_layouts=(
                    lambda: (
                        self.declaration_class_layout._finalize_registered_class_layouts()
                    )
                ),
                make_lowered_method_function=(
                    lambda cls, decl, sig, *, is_static, signature_key: (
                        self.declaration_class_method._make_lowered_method_function(
                            cls,
                            decl,
                            sig,
                            is_static=is_static,
                            signature_key=signature_key,
                        )
                    )
                ),
                member_call_key=(
                    lambda member: (
                        self.declaration_class_support._member_call_key(member)
                    )
                ),
                method_call_key_from_signature=(
                    lambda name, sig, *, is_static: (
                        self.declaration_class_support._method_call_key_from_signature(
                            name, sig, is_static=is_static
                        )
                    )
                ),
                method_is_abstract=(
                    lambda decl: (
                        self.declaration_class_support._method_is_abstract(
                            decl
                        )
                    )
                ),
                method_is_static=(
                    lambda decl: (
                        self.declaration_class_support._method_is_static(decl)
                    )
                ),
                method_signature_key=(
                    lambda name, sig, *, is_static: (
                        self.declaration_class_support._method_signature_key(
                            name, sig, is_static=is_static
                        )
                    )
                ),
                normalize_class_method_signature=(
                    lambda cls, decl: (
                        self.declaration_class_method._normalize_class_method_signature(
                            cls, decl
                        )
                    )
                ),
                require_value_expression=core._require_value_expression,
                resolve_class_bases=(
                    lambda cls: (
                        self.declaration_class_support._resolve_class_bases(
                            cls
                        )
                    )
                ),
                resolve_declared_type=core._resolve_declared_type,
                semantic=core._semantic,
                set_class=core._set_class,
                set_function=core._set_function,
                set_resource_ownership=core._set_resource_ownership,
                set_type=core._set_type,
                shared_class_ancestors=(
                    lambda bases, mro: (
                        self.declaration_class_support._shared_class_ancestors(
                            bases, mro
                        )
                    )
                ),
                static_initializer_is_supported=(
                    lambda value: (
                        self.declaration_class_support._static_initializer_is_supported(
                            value
                        )
                    )
                ),
                visibility_rank=(
                    lambda visibility: (
                        self.declaration_class_support._visibility_rank(
                            visibility
                        )
                    )
                ),
                bindings=core.bindings,
                context=core.context,
                factory=core.factory,
                registry=core.registry,
                visit=core.visit,
                free_validate_file_fields=(
                    lambda cls: free_validate_file_fields(core, cls)
                ),
                free_validate_hook=(
                    lambda decl: free_validate_hook(core, decl)
                ),
                free_is_native_file_class=(
                    lambda cls: free_is_native_file_class(core, cls)
                ),
            )
        )
        self.template_support = TemplateSupportAnalysis(
            TemplateSupportAnalysisServices()
        )
        self.template_build = TemplateBuildAnalysis(
            TemplateBuildAnalysisServices(
                clear_semantic_sidecars=(
                    lambda node: self.template_state._clear_semantic_sidecars(
                        node
                    )
                ),
                function_owner_module=(
                    lambda fn: self.template_state._function_owner_module(fn)
                ),
                set_function=core._set_function,
                set_type=core._set_type,
                substitute_declared_types=(
                    lambda node, bindings: (
                        self.template_state._substitute_declared_types(
                            node, bindings
                        )
                    )
                ),
                substitute_type=(
                    lambda type_, bindings: (
                        self.template_support._substitute_type(type_, bindings)
                    )
                ),
                template_bindings_map=(
                    lambda fn, args: (
                        self.template_support._template_bindings_map(fn, args)
                    )
                ),
                template_specialization_key=(
                    lambda fn, args: (
                        self.template_support._template_specialization_key(
                            fn, args
                        )
                    )
                ),
                template_specialization_name=(
                    lambda fn, args: (
                        self.template_support._template_specialization_name(
                            fn, args
                        )
                    )
                ),
                template_specialization_symbol_name=(
                    lambda fn, args: (
                        self.template_support._template_specialization_symbol_name(
                            fn, args
                        )
                    )
                ),
                context=core.context,
                factory=core.factory,
            )
        )
        self.template_state = TemplateStateAnalysis(
            TemplateStateAnalysisServices(
                substitute_type=(
                    lambda type_, bindings: (
                        self.template_support._substitute_type(type_, bindings)
                    )
                ),
                current_module=(lambda: core.current_ast_module),
                session=core.session,
            )
        )
        self.template = TemplateAnalysisAnalysis(
            TemplateAnalysisAnalysisServices(
                analyze_parameter_defaults=core._analyze_parameter_defaults,
                build_template_specialization=(
                    lambda fn, args: (
                        self.template_build._build_template_specialization(
                            fn, args
                        )
                    )
                ),
                current_module_key=core._current_module_key,
                format_template_bindings=(
                    lambda bindings: (
                        self.template_support._format_template_bindings(
                            bindings
                        )
                    )
                ),
                guarantees_return=core._guarantees_return,
                mark_template_specializations_prepared=(
                    lambda fn: (
                        self.template_state._mark_template_specializations_prepared(
                            fn
                        )
                    )
                ),
                resolve_declared_type=core._resolve_declared_type,
                set_function=core._set_function,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                template_param_domain=(
                    lambda param: self.template_support._template_param_domain(
                        param
                    )
                ),
                template_specializations_prepared=(
                    lambda fn: (
                        self.template_state._template_specializations_prepared(
                            fn
                        )
                    )
                ),
                context=core.context,
                visit=core.visit,
                free_resolve_parameter_ownership=(
                    lambda arg_node, arg_symbol: (
                        free_resolve_parameter_ownership(
                            core, arg_node, arg_symbol
                        )
                    )
                ),
            )
        )
        self.template_resolution = TemplateResolutionAnalysis(
            TemplateResolutionAnalysisServices(
                build_template_specialization=(
                    lambda fn, args: (
                        self.template_build._build_template_specialization(
                            fn, args
                        )
                    )
                ),
                type_within_template_bound=(
                    lambda type_, bound: (
                        self.template_support._type_within_template_bound(
                            type_, bound
                        )
                    )
                ),
                context=core.context,
            )
        )
        self.expression_class_support = ExpressionClassSupportAnalysis(
            ExpressionClassSupportAnalysisServices(
                format_method_signature=(
                    lambda member: (
                        self.class_member_formatting._format_method_signature(
                            member
                        )
                    )
                ),
                member_declaring_class=(
                    lambda member: (
                        self.class_member_formatting._member_declaring_class(
                            member
                        )
                    )
                ),
                member_display_name=(
                    lambda member: (
                        self.class_member_formatting._member_display_name(
                            member
                        )
                    )
                ),
                resolve_class_from_type=core._resolve_class_from_type,
                bindings=core.bindings,
                context=core.context,
            )
        )
        self.expression_module = ExpressionModuleAnalysis(
            ExpressionModuleAnalysisServices(
                expr_type=core._expr_type,
                resolve_class_from_type=core._resolve_class_from_type,
                resolve_template_call_target=(
                    lambda fn, types_, node: (
                        self.template_resolution._resolve_template_call_target(
                            fn, types_, node
                        )
                    )
                ),
                semantic=core._semantic,
                set_call=core._set_call,
                set_class=core._set_class,
                set_function=core._set_function,
                set_module=core._set_module,
                set_module_member_access=core._set_module_member_access,
                set_resource_ownership=core._set_resource_ownership,
                set_struct=core._set_struct,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                bindings=core.bindings,
                call_dispatch=core.call_dispatch,
                context=core.context,
                factory=core.factory,
                resolve_class_construction=(
                    lambda node, cls: (
                        self.expression_class_access.resolve_class_construction(
                            node, cls
                        )
                    )
                ),
                session=core.session,
                visit=core.visit,
                free_resolve_materialization=(
                    lambda node: free_resolve_materialization(core, node)
                ),
                free_resolve_text_call=(
                    lambda node: free_resolve_text_call(core, node)
                ),
                free_resolve_file_open=(
                    lambda node: free_resolve_file_open(core, node)
                ),
            )
        )
        self.expression_tensor_buffer_support = (
            ExpressionTensorBufferSupportAnalysis(
                ExpressionTensorBufferSupportAnalysisServices(
                    expr_type=core._expr_type,
                    semantic=core._semantic,
                    context=core.context,
                )
            )
        )
        self.expression_literal = ExpressionLiteralAnalysis(
            ExpressionLiteralAnalysisServices(
                declare_iteration_target=core._declare_iteration_target,
                expr_type=core._expr_type,
                require_value_expression=core._require_value_expression,
                resolve_mutation_target=(
                    lambda target, *, node, action, invalid_message: (
                        self.expression_mutation._resolve_mutation_target(
                            target,
                            node=node,
                            action=action,
                            invalid_message=invalid_message,
                        )
                    )
                ),
                semantic=core._semantic,
                set_assignment=core._set_assignment,
                set_collection_method=core._set_collection_method,
                set_iteration=core._set_iteration,
                set_resource_ownership=core._set_resource_ownership,
                set_type=core._set_type,
                context=core.context,
                visit=core.visit,
                free_resolve_column_index=(
                    lambda node: free_resolve_column_index(core, node)
                ),
                free_text_error=(
                    lambda node, message: free_text_error(core, node, message)
                ),
                free_set_text_operation=(
                    lambda node, kind, evaluations, indices: (
                        free_set_text_operation(
                            core, node, kind, evaluations, indices
                        )
                    )
                ),
                free_resolve_text_subscript=(
                    lambda node: free_resolve_text_subscript(core, node)
                ),
            )
        )
        self.expression_list = ExpressionListAnalysis(
            ExpressionListAnalysisServices(
                expr_type=core._expr_type,
                require_value_expression=core._require_value_expression,
                semantic=core._semantic,
                set_resource_ownership=core._set_resource_ownership,
                set_type=core._set_type,
                context=core.context,
                visit=core.visit,
            )
        )
        self.expression_class_access = ExpressionClassAccessAnalysis(
            ExpressionClassAccessAnalysisServices(
                expr_type=core._expr_type,
                member_display_name=(
                    lambda member: (
                        self.class_member_formatting._member_display_name(
                            member
                        )
                    )
                ),
                member_is_accessible=(
                    lambda member: (
                        self.expression_class_support._member_is_accessible(
                            member
                        )
                    )
                ),
                module_namespace=(
                    lambda node: self.expression_module._module_namespace(node)
                ),
                module_namespace_name=(
                    lambda node, module=None: (
                        self.expression_module._module_namespace_name(
                            node, module
                        )
                    )
                ),
                require_value_expression=core._require_value_expression,
                resolve_base_access_classes=(
                    lambda receiver, base, *, node, context: (
                        self.expression_class_support._resolve_base_access_classes(
                            receiver, base, node=node, context=context
                        )
                    )
                ),
                resolve_call_resource_ownership=(
                    lambda node, args, result: (
                        self.expression_module._resolve_call_resource_ownership(
                            node, args, result
                        )
                    )
                ),
                resolve_class_attribute_member=(
                    lambda cls, name, *, node: (
                        self.expression_class_support._resolve_class_attribute_member(
                            cls, name, node=node
                        )
                    )
                ),
                resolve_class_definition=(
                    lambda cls: (
                        self.declaration_class_member._resolve_class_definition(
                            cls
                        )
                    )
                ),
                resolve_class_field_slot=(
                    lambda cls, member, *, visible_name=None: (
                        self.expression_class_support._resolve_class_field_slot(
                            cls, member, visible_name=visible_name
                        )
                    )
                ),
                resolve_class_from_type=core._resolve_class_from_type,
                resolve_method_overload=(
                    lambda cls, name, types_, *, is_static, node: (
                        self.expression_class_support._resolve_method_overload(
                            cls, name, types_, is_static=is_static, node=node
                        )
                    )
                ),
                resolve_module_member_binding=(
                    lambda module, name, *, node, namespace_name: (
                        self.expression_module._resolve_module_member_binding(
                            module,
                            name,
                            node=node,
                            namespace_name=namespace_name,
                        )
                    )
                ),
                resolve_module_namespace_call=(
                    lambda node, module, types_: (
                        self.expression_module._resolve_module_namespace_call(
                            node, module, types_
                        )
                    )
                ),
                resolve_named_class=(
                    lambda name, *, node: (
                        self.expression_class_support._resolve_named_class(
                            name, node=node
                        )
                    )
                ),
                resolve_static_class_storage=(
                    lambda cls, member, name: (
                        self.expression_class_support._resolve_static_class_storage(
                            cls, member, name
                        )
                    )
                ),
                resolve_struct_from_type=core._resolve_struct_from_type,
                resolve_template_method_call_target=(
                    lambda fn, visible, types_, node: (
                        self.template_resolution._resolve_template_method_call_target(
                            fn, visible, types_, node
                        )
                    )
                ),
                semantic=core._semantic,
                set_base_class_field_access=core._set_base_class_field_access,
                set_call=core._set_call,
                set_class=core._set_class,
                set_class_construction=core._set_class_construction,
                set_class_field_access=core._set_class_field_access,
                set_field_access=core._set_field_access,
                set_method_call=core._set_method_call,
                set_module_member_resolution=(
                    lambda node, *, module, member_name, binding: (
                        self.expression_module._set_module_member_resolution(
                            node,
                            module=module,
                            member_name=member_name,
                            binding=binding,
                        )
                    )
                ),
                set_resource_ownership=core._set_resource_ownership,
                set_static_class_field_access=core._set_static_class_field_access,
                set_struct=core._set_struct,
                set_type=core._set_type,
                specialization_bindings_map=(
                    lambda fn: (
                        self.template_support._specialization_bindings_map(fn)
                    )
                ),
                specialize_signature=(
                    lambda fn, bindings: (
                        self.template_support._specialize_signature(
                            fn, bindings
                        )
                    )
                ),
                visible_method_function=(
                    lambda cls, member: (
                        self.expression_class_support._visible_method_function(
                            cls, member
                        )
                    )
                ),
                context=core.context,
                visit=core.visit,
                free_is_native_file_class=(
                    lambda cls: free_is_native_file_class(core, cls)
                ),
                free_constructor_arguments=(
                    lambda node, cls: free_constructor_arguments(
                        core, node, cls
                    )
                ),
                free_reject_hook_call=(
                    lambda node, name: free_reject_hook_call(core, node, name)
                ),
                free_resolve_public_file_construction=(
                    lambda node, cls: free_resolve_public_file_construction(
                        core, node, cls
                    )
                ),
                free_resolve_exception_construction=(
                    lambda node, cls: free_resolve_exception_construction(
                        core, node, cls
                    )
                ),
                free_resolve_text_call=(
                    lambda node: free_resolve_text_call(core, node)
                ),
                free_text_error=(
                    lambda node, message: free_text_error(core, node, message)
                ),
                free_resolve_file_method=(
                    lambda node: free_resolve_file_method(core, node)
                ),
                free_validate_file_method_arguments=(
                    lambda node, *, public=False: (
                        free_validate_file_method_arguments(
                            core, node, public=public
                        )
                    )
                ),
            )
        )
        self.expression_mutation = ExpressionMutationAnalysis(
            ExpressionMutationAnalysisServices(
                expr_type=core._expr_type,
                member_declaring_class=(
                    lambda member: (
                        self.class_member_formatting._member_declaring_class(
                            member
                        )
                    )
                ),
                member_display_name=(
                    lambda member: (
                        self.class_member_formatting._member_display_name(
                            member
                        )
                    )
                ),
                member_owner_module_key=(
                    lambda member: (
                        self.class_member_formatting._member_owner_module_key(
                            member
                        )
                    )
                ),
                require_value_expression=core._require_value_expression,
                root_assignment_symbol=core._root_assignment_symbol,
                set_assignment=core._set_assignment,
                set_resource_ownership=core._set_resource_ownership,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                context=core.context,
                factory=core.factory,
                visit=core.visit,
            )
        )
        self.expression_data_frame = ExpressionDataFrameAnalysis(
            ExpressionDataFrameAnalysisServices(
                expr_type=core._expr_type,
                semantic=core._semantic,
                set_resource_ownership=core._set_resource_ownership,
                set_type=core._set_type,
                context=core.context,
                visit=core.visit,
                free_set_operation=(
                    lambda node, kernel, input_type, result: (
                        free_set_operation(
                            core, node, kernel, input_type, result
                        )
                    )
                ),
                free_resolve_series_reduction=(
                    lambda node: free_resolve_series_reduction(core, node)
                ),
                free_nullable_error=(
                    lambda node, message: free_nullable_error(
                        core, node, message
                    )
                ),
                free_lifecycle_error=(
                    lambda node, message: free_lifecycle_error(
                        core, node, message
                    )
                ),
            )
        )
        self.expression_buffer_view = ExpressionBufferViewAnalysis(
            ExpressionBufferViewAnalysisServices(
                expr_type=core._expr_type,
                semantic=core._semantic,
                set_type=core._set_type,
                static_buffer_view_metadata=(
                    lambda node: (
                        self.expression_tensor_buffer_support._static_buffer_view_metadata(
                            node
                        )
                    )
                ),
                validate_buffer_lifetime_operation=(
                    lambda *, node, view, operation: (
                        self.expression_tensor_buffer_support._validate_buffer_lifetime_operation(
                            node=node, view=view, operation=operation
                        )
                    )
                ),
                validate_buffer_view_index_operation=(
                    lambda *, node, base, indices, is_store: (
                        self.expression_tensor_buffer_support._validate_buffer_view_index_operation(
                            node=node,
                            base=base,
                            indices=indices,
                            is_store=is_store,
                        )
                    )
                ),
                context=core.context,
                visit=core.visit,
            )
        )
        self.expression_operator = ExpressionOperatorAnalysis(
            ExpressionOperatorAnalysisServices(
                expr_type=core._expr_type,
                require_value_expression=core._require_value_expression,
                resolve_declared_type=core._resolve_declared_type,
                resolve_list_assignment_ownership=(
                    lambda n, v, sym, *, target_name, target_type, is_local: (
                        self.expression_mutation._resolve_list_assignment_ownership(
                            n,
                            v,
                            sym,
                            target_name=target_name,
                            target_type=target_type,
                            is_local=is_local,
                        )
                    )
                ),
                resolve_mutation_target=(
                    lambda target, *, node, action, invalid_message: (
                        self.expression_mutation._resolve_mutation_target(
                            target,
                            node=node,
                            action=action,
                            invalid_message=invalid_message,
                        )
                    )
                ),
                resolve_string_assignment_ownership=(
                    lambda n, v, sym, *, target_name, target_type, is_local: (
                        self.expression_mutation._resolve_string_assignment_ownership(
                            n,
                            v,
                            sym,
                            target_name=target_name,
                            target_type=target_type,
                            is_local=is_local,
                        )
                    )
                ),
                semantic=core._semantic,
                set_assignment=core._set_assignment,
                set_flags=core._set_flags,
                set_operator=core._set_operator,
                set_resource_ownership=core._set_resource_ownership,
                set_symbol=core._set_symbol,
                set_type=core._set_type,
                context=core.context,
                visit=core.visit,
                free_resolve_column_unary=(
                    lambda node: free_resolve_column_unary(core, node)
                ),
                free_resolve_column_binary=(
                    lambda node: free_resolve_column_binary(core, node)
                ),
                free_resolve_arrow_cast=(
                    lambda node: free_resolve_arrow_cast(core, node)
                ),
                free_reject_native_file_cast=(
                    lambda node: free_reject_native_file_cast(core, node)
                ),
                free_resolve_arrow_store=(
                    lambda node, symbol: free_resolve_arrow_store(
                        core, node, symbol
                    )
                ),
                free_resolve_store=(
                    lambda node, symbol: free_resolve_store(core, node, symbol)
                ),
            )
        )
        self.expression_tensor = ExpressionTensorAnalysis(
            ExpressionTensorAnalysisServices(
                expr_type=core._expr_type,
                semantic=core._semantic,
                set_type=core._set_type,
                static_tensor_element_type=(
                    lambda node: (
                        self.expression_tensor_buffer_support._static_tensor_element_type(
                            node
                        )
                    )
                ),
                static_tensor_flags=(
                    lambda node: (
                        self.expression_tensor_buffer_support._static_tensor_flags(
                            node
                        )
                    )
                ),
                static_tensor_layout=(
                    lambda node: (
                        self.expression_tensor_buffer_support._static_tensor_layout(
                            node
                        )
                    )
                ),
                validate_tensor_index_operation=(
                    lambda *, node, base, indices, is_store: (
                        self.expression_tensor_buffer_support._validate_tensor_index_operation(
                            node=node,
                            base=base,
                            indices=indices,
                            is_store=is_store,
                        )
                    )
                ),
                validate_tensor_lifetime_operation=(
                    lambda *, node, view, operation: (
                        self.expression_tensor_buffer_support._validate_tensor_lifetime_operation(
                            node=node, view=view, operation=operation
                        )
                    )
                ),
                context=core.context,
                visit=core.visit,
            )
        )
        self.expression_array = ExpressionArrayAnalysis(
            ExpressionArrayAnalysisServices(
                expr_type=core._expr_type,
                set_type=core._set_type,
                context=core.context,
                visit=core.visit,
            )
        )
        handlers = (
            *self.exception.node_handlers(),
            *self.imports.node_handlers(),
            *self.control_flow.node_handlers(),
            *self.declaration_function.node_handlers(),
            *self.declaration_block.node_handlers(),
            *self.declaration_struct.node_handlers(),
            *self.declaration_class_member.node_handlers(),
            *self.expression_module.node_handlers(),
            *self.expression_literal.node_handlers(),
            *self.expression_list.node_handlers(),
            *self.expression_class_access.node_handlers(),
            *self.expression_mutation.node_handlers(),
            *self.expression_data_frame.node_handlers(),
            *self.expression_buffer_view.node_handlers(),
            *self.expression_operator.node_handlers(),
            *self.expression_tensor.node_handlers(),
            *self.expression_array.node_handlers(),
        )
        self.dispatch = ScopedNodeDispatch(
            "analysis", handlers, core.reject_node
        )
