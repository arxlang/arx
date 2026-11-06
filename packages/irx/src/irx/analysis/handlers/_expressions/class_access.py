# mypy: disable-error-code=no-redef

"""
title: Expression class-access visitors.
summary: >-
  Handle class construction, method calls, and field access using the shared
  class-resolution helpers.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.analysis.call_arguments import (
    analyze_numeric_arguments,
    call_evaluations,
)
from irx.analysis.class_lifecycle import (
    INITIALIZER_HOOK,
    class_ownership,
    field_resource,
)
from irx.analysis.dependencies.expression_class_access import (
    ExpressionClassAccessAnalysisServices,
)
from irx.analysis.numeric_literals import default_numeric_literal_type
from irx.analysis.resolved_nodes import (
    MethodDispatchKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResolvedBaseClassFieldAccess,
    ResolvedClassConstruction,
    ResolvedClassFieldAccess,
    ResolvedFieldAccess,
    ResolvedFileOperation,
    ResolvedMethodCall,
    ResolvedStaticClassFieldAccess,
    ResourceKind,
    ResourceOwnership,
    SemanticClass,
    SemanticClassMember,
)
from irx.analysis.types import display_type_name, is_string_type
from irx.analysis.validation import validate_call
from irx.diagnostics import DiagnosticCodes
from irx.extensions.handlers import configuration_error
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ExpressionClassAccessAnalysis:
    """
    title: Expression class-access visitors.
    attributes:
      services:
        type: ExpressionClassAccessAnalysisServices
    """

    services: ExpressionClassAccessAnalysisServices

    def __init__(
        self, services: ExpressionClassAccessAnalysisServices
    ) -> None:
        """
        title: Bind one feature to explicit compilation-owned dependencies.
        parameters:
          services:
            type: ExpressionClassAccessAnalysisServices
        """
        self.services = services

    def _abstract_method_call_is_invalid(
        self,
        node: astx.AST,
        member: SemanticClassMember,
        *,
        allow_indirect_dispatch: bool,
    ) -> bool:
        """
        title: Diagnose one invalid abstract method call.
        parameters:
          node:
            type: astx.AST
          member:
            type: SemanticClassMember
          allow_indirect_dispatch:
            type: bool
        returns:
          type: bool
        """
        if not member.is_abstract:
            return False
        if (
            allow_indirect_dispatch
            and not member.is_static
            and member.dispatch_slot is not None
        ):
            return False
        self.services.context.diagnostics.add(
            (
                f"abstract method '{member.owner_name}.{member.name}' "
                "cannot be called directly"
            ),
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return True

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Reject an input outside this feature's explicit support.
        parameters:
          node:
            type: astx.AST
        """
        raise configuration_error(
            f"unsupported {type(node).__name__} "
            "in ExpressionClassAccessAnalysis"
        )

    @dispatch
    def visit(self, node: astx.ClassConstruct) -> None:
        """
        title: Visit ClassConstruct nodes.
        parameters:
          node:
            type: astx.ClassConstruct
        """
        self.services.semantic(node).resolved_class_construction = None
        class_ = self.services.resolve_named_class(node.class_name, node=node)
        if class_ is None:
            self.services.set_type(node, None)
            return
        self.resolve_class_construction(node, class_)

    def resolve_class_construction(
        self,
        node: astx.ClassConstruct | astx.FunctionCall | astx.MethodCall,
        class_: SemanticClass,
    ) -> None:
        """
        title: Resolve a class-valued callable after ordinary symbol lookup.
        parameters:
          node:
            type: astx.ClassConstruct | astx.FunctionCall | astx.MethodCall
          class_:
            type: SemanticClass
        """
        resolve_definition = self.services.resolve_class_definition
        if callable(resolve_definition) and not class_.is_resolved:
            class_ = resolve_definition(class_)
        if class_.is_abstract:
            abstract_method_names = ", ".join(
                f"{member.owner_name}.{member.name}"
                for member in class_.abstract_methods
            )
            suffix = (
                f"; abstract methods: {abstract_method_names}"
                if abstract_method_names
                else ""
            )
            self.services.context.diagnostics.add(
                f"abstract class '{class_.name}' cannot be constructed"
                f"{suffix}",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            self.services.set_type(node, None)
            return
        if class_.layout is None or class_.initialization is None:
            raise TypeError(
                "class construction requires resolved layout metadata"
            )
        if self.services.free_is_native_file_class(class_):
            self.services.free_resolve_public_file_construction(node, class_)
            return
        canonical = self.services.context.get_class(
            class_.module_key, class_.name
        )
        if canonical is not None:
            class_ = canonical
        if class_.exception_type is not None:
            self.services.free_resolve_exception_construction(node, class_)
            return
        assert class_.initialization is not None
        resolved_type = astx.ClassType(
            class_.name,
            resolved_name=class_.name,
            module_key=class_.module_key,
            qualified_name=class_.qualified_name,
            ancestor_qualified_names=tuple(
                ancestor.qualified_name for ancestor in class_.mro[1:]
            ),
        )
        self.services.set_class(node, class_)
        initializer = class_.declared_member_table.get(INITIALIZER_HOOK.name)
        if (
            initializer is not None
            and initializer.lowered_function is not None
            and not self.services.member_is_accessible(initializer)
        ):
            self.services.context.diagnostics.add(
                "constructor is not accessible from this context",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
        evaluations, indices, types = self.services.free_constructor_arguments(
            node, class_
        )
        self.services.set_class_construction(
            node,
            ResolvedClassConstruction(
                class_=class_,
                initialization=class_.initialization,
                evaluations=evaluations,
                argument_indices=indices,
                argument_types=types,
            ),
        )
        self.services.set_type(node, resolved_type)
        self.services.set_resource_ownership(
            node, class_ownership(OwnershipKind.OWNED)
        )

    @dispatch
    def visit(self, node: astx.MethodCall) -> None:
        """
        title: Visit MethodCall nodes.
        parameters:
          node:
            type: astx.MethodCall
        """
        info = self.services.semantic(node)
        if info.resolved_file_operation is not None:
            info.resource_ownership = None
        info.resolved_file_operation = None
        info.resolved_text_operation = None
        info.resolved_class_construction = None
        self.services.semantic(node).resource_ownership = None
        self.services.visit(node.receiver)
        module = self.services.module_namespace(node.receiver)
        if module is not None:
            self.services.resolve_module_namespace_call(node, module, [])
            return
        receiver_type = self.services.expr_type(node.receiver)
        if is_string_type(receiver_type):
            self.services.free_resolve_text_call(node)
            return
        if node.method_name in {"split", "strip"} and not isinstance(
            receiver_type, astx.ClassType
        ):
            self.services.free_text_error(
                node,
                f"{node.method_name} requires a text receiver",
            )
            return
        arg_types: list[astx.DataType | None] = []
        for arg in call_evaluations(node):
            if not isinstance(arg, (astx.LiteralInteger, astx.LiteralFloat)):
                self.services.visit(arg)
            arg_types.append(
                default_numeric_literal_type(arg)
                if isinstance(arg, (astx.LiteralInteger, astx.LiteralFloat))
                else self.services.expr_type(arg)
            )
        if not self.services.require_value_expression(
            node.receiver,
            context="Method call receiver",
        ):
            self.services.set_type(node, None)
            return
        receiver_type = self.services.expr_type(node.receiver)
        if isinstance(receiver_type, astx.FileType):
            for arg in call_evaluations(node):
                if isinstance(arg, (astx.LiteralInteger, astx.LiteralFloat)):
                    self.services.visit(arg)
            self.services.free_resolve_file_method(node)
            return
        class_ = self.services.resolve_class_from_type(
            receiver_type,
            node=node,
            unknown_message="method call requires a class value",
        )
        if class_ is None:
            if not isinstance(receiver_type, astx.ClassType):
                self.services.context.diagnostics.add(
                    "method call requires a class value, got "
                    f"{display_type_name(receiver_type)}",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
                )
            self.services.set_type(node, None)
            return
        if self.services.free_reject_hook_call(node, node.method_name):
            return
        resolved_overload = self.services.resolve_method_overload(
            class_,
            node.method_name,
            arg_types,
            is_static=False,
            node=node,
        )
        if resolved_overload is None:
            self.services.set_type(node, None)
            return
        member, candidates = resolved_overload
        if self._abstract_method_call_is_invalid(
            node,
            member,
            allow_indirect_dispatch=True,
        ):
            self.services.set_type(node, None)
            return
        function = member.lowered_function
        if function is None:
            raise TypeError("instance method must have a lowered function")
        visible_function = self.services.visible_method_function(
            class_, member
        )
        arg_types = analyze_numeric_arguments(
            node,
            visible_function,
            self.services.visit,
            self.services.expr_type,
            typed_visited=True,
        )
        if function.template_params:
            specialized_function = (
                self.services.resolve_template_method_call_target(
                    function,
                    visible_function,
                    arg_types,
                    node,
                )
            )
            if specialized_function is None:
                self.services.set_type(node, None)
                return
            visible_function = self.services.specialize_signature(
                visible_function,
                self.services.specialization_bindings_map(
                    specialized_function
                ),
            )
            function = specialized_function
        call_resolution = validate_call(
            self.services.context.diagnostics,
            function=visible_function,
            arg_types=arg_types,
            node=node,
            binding_function=function,
        )
        if self.services.free_is_native_file_class(
            class_
        ) and not self.services.free_validate_file_method_arguments(
            node, public=True
        ):
            return
        dispatch_kind = MethodDispatchKind.DIRECT
        if member.dispatch_slot is not None:
            dispatch_kind = MethodDispatchKind.INDIRECT
        self.services.set_call(node, call_resolution)
        self.services.set_method_call(
            node,
            ResolvedMethodCall(
                class_=class_,
                member=member,
                function=function,
                overload_key=(member.signature_key or member.qualified_name),
                dispatch_kind=dispatch_kind,
                call=call_resolution,
                candidates=candidates,
                receiver_type=receiver_type,
                receiver_class=class_,
                slot_index=member.dispatch_slot,
            ),
        )
        self.services.set_type(node, call_resolution.result_type)
        self.services.resolve_call_resource_ownership(
            node,
            list(call_evaluations(node)),
            call_resolution.result_type,
        )
        if self.services.free_is_native_file_class(class_):
            if class_.layout is None:
                raise TypeError(
                    "native File method requires a resolved layout"
                )
            self.services.semantic(
                node
            ).resolved_file_operation = ResolvedFileOperation(
                node.method_name, class_.layout.instance_fields[0]
            )

    @dispatch
    def visit(self, node: astx.BaseMethodCall) -> None:
        """
        title: Visit BaseMethodCall nodes.
        parameters:
          node:
            type: astx.BaseMethodCall
        """
        if self.services.free_reject_hook_call(node, node.method_name):
            return
        self.services.semantic(node).resource_ownership = None
        self.services.visit(node.receiver)
        arg_types: list[astx.DataType | None] = []
        for arg in call_evaluations(node):
            if not isinstance(arg, (astx.LiteralInteger, astx.LiteralFloat)):
                self.services.visit(arg)
            arg_types.append(
                default_numeric_literal_type(arg)
                if isinstance(arg, (astx.LiteralInteger, astx.LiteralFloat))
                else self.services.expr_type(arg)
            )
        if not self.services.require_value_expression(
            node.receiver,
            context="Base method call receiver",
        ):
            self.services.set_type(node, None)
            return
        receiver_type = self.services.expr_type(node.receiver)
        resolved_classes = self.services.resolve_base_access_classes(
            receiver_type,
            node.base_class_name,
            node=node,
            context="base method call",
        )
        if resolved_classes is None:
            self.services.set_type(node, None)
            return
        receiver_class, base_class = resolved_classes
        resolved_overload = self.services.resolve_method_overload(
            base_class,
            node.method_name,
            arg_types,
            is_static=False,
            node=node,
        )
        if resolved_overload is None:
            self.services.set_type(node, None)
            return
        member, candidates = resolved_overload
        if self._abstract_method_call_is_invalid(
            node,
            member,
            allow_indirect_dispatch=False,
        ):
            self.services.set_type(node, None)
            return
        function = member.lowered_function
        if function is None:
            raise TypeError("base method must have a lowered function")
        visible_function = self.services.visible_method_function(
            base_class, member
        )
        arg_types = analyze_numeric_arguments(
            node,
            visible_function,
            self.services.visit,
            self.services.expr_type,
            typed_visited=True,
        )
        if function.template_params:
            specialized_function = (
                self.services.resolve_template_method_call_target(
                    function,
                    visible_function,
                    arg_types,
                    node,
                )
            )
            if specialized_function is None:
                self.services.set_type(node, None)
                return
            visible_function = self.services.specialize_signature(
                visible_function,
                self.services.specialization_bindings_map(
                    specialized_function
                ),
            )
            function = specialized_function
        call_resolution = validate_call(
            self.services.context.diagnostics,
            function=visible_function,
            arg_types=arg_types,
            node=node,
            binding_function=function,
        )
        self.services.set_call(node, call_resolution)
        self.services.set_method_call(
            node,
            ResolvedMethodCall(
                class_=base_class,
                member=member,
                function=function,
                overload_key=(member.signature_key or member.qualified_name),
                dispatch_kind=MethodDispatchKind.DIRECT,
                call=call_resolution,
                candidates=candidates,
                receiver_type=receiver_type,
                receiver_class=receiver_class,
            ),
        )
        self.services.set_type(node, call_resolution.result_type)
        self.services.resolve_call_resource_ownership(
            node,
            list(call_evaluations(node)),
            call_resolution.result_type,
        )

    @dispatch
    def visit(self, node: astx.StaticMethodCall) -> None:
        """
        title: Visit StaticMethodCall nodes.
        parameters:
          node:
            type: astx.StaticMethodCall
        """
        if self.services.free_reject_hook_call(node, node.method_name):
            return
        arg_types: list[astx.DataType | None] = []
        for arg in call_evaluations(node):
            if not isinstance(arg, (astx.LiteralInteger, astx.LiteralFloat)):
                self.services.visit(arg)
            arg_types.append(
                default_numeric_literal_type(arg)
                if isinstance(arg, (astx.LiteralInteger, astx.LiteralFloat))
                else self.services.expr_type(arg)
            )
        class_ = self.services.resolve_named_class(node.class_name, node=node)
        if class_ is None:
            self.services.set_type(node, None)
            return
        resolved_overload = self.services.resolve_method_overload(
            class_,
            node.method_name,
            arg_types,
            is_static=True,
            node=node,
        )
        if resolved_overload is None:
            self.services.set_type(node, None)
            return
        member, candidates = resolved_overload
        if self._abstract_method_call_is_invalid(
            node,
            member,
            allow_indirect_dispatch=False,
        ):
            self.services.set_type(node, None)
            return
        function = member.lowered_function
        if function is None:
            raise TypeError("static method must have a lowered function")
        visible_function = self.services.visible_method_function(
            class_, member
        )
        arg_types = analyze_numeric_arguments(
            node,
            visible_function,
            self.services.visit,
            self.services.expr_type,
            typed_visited=True,
        )
        if function.template_params:
            specialized_function = (
                self.services.resolve_template_method_call_target(
                    function,
                    visible_function,
                    arg_types,
                    node,
                )
            )
            if specialized_function is None:
                self.services.set_type(node, None)
                return
            visible_function = self.services.specialize_signature(
                visible_function,
                self.services.specialization_bindings_map(
                    specialized_function
                ),
            )
            function = specialized_function
        call_resolution = validate_call(
            self.services.context.diagnostics,
            function=visible_function,
            arg_types=arg_types,
            node=node,
            binding_function=function,
        )
        self.services.set_call(node, call_resolution)
        self.services.set_method_call(
            node,
            ResolvedMethodCall(
                class_=class_,
                member=member,
                function=function,
                overload_key=(member.signature_key or member.qualified_name),
                dispatch_kind=MethodDispatchKind.DIRECT,
                call=call_resolution,
                candidates=candidates,
            ),
        )
        self.services.set_type(node, call_resolution.result_type)
        self.services.resolve_call_resource_ownership(
            node,
            list(call_evaluations(node)),
            call_resolution.result_type,
        )

    @dispatch
    def visit(self, node: astx.BaseFieldAccess) -> None:
        """
        title: Visit BaseFieldAccess nodes.
        parameters:
          node:
            type: astx.BaseFieldAccess
        """
        self.services.semantic(node).resource_ownership = None
        self.services.visit(node.receiver)
        if not self.services.require_value_expression(
            node.receiver,
            context="Base field access",
        ):
            self.services.set_type(node, None)
            return
        receiver_type = self.services.expr_type(node.receiver)
        resolved_classes = self.services.resolve_base_access_classes(
            receiver_type,
            node.base_class_name,
            node=node,
            context="base field access",
        )
        if resolved_classes is None:
            self.services.set_type(node, None)
            return
        receiver_class, base_class = resolved_classes
        member = self.services.resolve_class_attribute_member(
            base_class,
            node.field_name,
            node=node,
        )
        if member is None:
            self.services.set_type(node, None)
            return
        if member.is_static:
            self.services.context.diagnostics.add(
                (
                    f"static attribute '{base_class.name}.{node.field_name}' "
                    "must be accessed through the class"
                ),
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return
        if not self.services.member_is_accessible(member):
            self.services.context.diagnostics.add(
                (
                    "class attribute "
                    f"'{self.services.member_display_name(member)}' "
                    "is not accessible from this context"
                ),
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return
        field = self.services.resolve_class_field_slot(
            receiver_class,
            member,
        )
        self.services.set_class(node, base_class)
        self.services.set_base_class_field_access(
            node,
            ResolvedBaseClassFieldAccess(
                receiver_class=receiver_class,
                base_class=base_class,
                member=member,
                field=field,
            ),
        )
        self.services.set_type(node, member.type_)
        kind = field_resource(member.type_)
        if kind is not None:
            self.services.set_resource_ownership(
                node,
                ResourceOwnership(
                    kind,
                    (
                        OwnershipKind.OWNED
                        if kind is ResourceKind.STRING
                        else OwnershipKind.BORROWED
                    ),
                    transfer_kind=(
                        OwnershipTransferKind.NONE
                        if kind is ResourceKind.STRING
                        else OwnershipTransferKind.BORROW
                    ),
                ),
            )

    @dispatch
    def visit(self, node: astx.StaticFieldAccess) -> None:
        """
        title: Visit StaticFieldAccess nodes.
        parameters:
          node:
            type: astx.StaticFieldAccess
        """
        class_ = self.services.resolve_named_class(node.class_name, node=node)
        if class_ is None:
            self.services.set_type(node, None)
            return
        member = self.services.resolve_class_attribute_member(
            class_,
            node.field_name,
            node=node,
        )
        if member is None:
            self.services.set_type(node, None)
            return
        if not member.is_static:
            self.services.context.diagnostics.add(
                (
                    f"instance attribute '{class_.name}.{node.field_name}' "
                    "requires a receiver"
                ),
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return
        if not self.services.member_is_accessible(member):
            self.services.context.diagnostics.add(
                (
                    "class attribute "
                    f"'{self.services.member_display_name(member)}' "
                    "is not accessible from this context"
                ),
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return
        storage = self.services.resolve_static_class_storage(
            class_,
            member,
            node.field_name,
        )
        self.services.set_class(node, class_)
        self.services.set_static_class_field_access(
            node,
            ResolvedStaticClassFieldAccess(class_, member, storage),
        )
        self.services.set_type(node, member.type_)

    @dispatch
    def visit(self, node: astx.FieldAccess) -> None:
        """
        title: Visit FieldAccess nodes.
        parameters:
          node:
            type: astx.FieldAccess
        """
        self.services.semantic(node).resource_ownership = None
        self.services.visit(node.value)
        if not self.services.require_value_expression(
            node.value,
            context="Field access",
        ):
            self.services.set_type(node, None)
            return
        module = self.services.module_namespace(node.value)
        if module is not None:
            namespace_name = self.services.module_namespace_name(
                node.value, module
            )
            binding = self.services.resolve_module_member_binding(
                module,
                node.field_name,
                node=node,
                namespace_name=namespace_name,
            )
            if binding is None:
                self.services.set_type(node, None)
                return
            self.services.set_module_member_resolution(
                node,
                module=module,
                member_name=node.field_name,
                binding=binding,
            )
            return
        base_type = self.services.expr_type(node.value)
        struct = self.services.resolve_struct_from_type(
            base_type,
            node=node,
            unknown_message="field access requires a struct or class value",
        )
        if struct is not None:
            field_index = struct.field_indices.get(node.field_name)
            if field_index is None or field_index >= len(struct.fields):
                self.services.context.diagnostics.add(
                    f"struct '{struct.name}' has no field '{node.field_name}'",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
                )
                self.services.set_type(node, None)
                return
            field = struct.fields[field_index]
            self.services.set_struct(node, struct)
            self.services.set_field_access(
                node, ResolvedFieldAccess(struct, field)
            )
            self.services.set_type(node, field.type_)
            return

        class_ = self.services.resolve_class_from_type(
            base_type,
            node=node,
            unknown_message="field access requires a struct or class value",
        )
        if class_ is None:
            if not isinstance(base_type, astx.StructType | astx.ClassType):
                self.services.context.diagnostics.add(
                    "field access requires a struct or class value, got "
                    f"{display_type_name(base_type)}",
                    node=node,
                    code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
                )
            self.services.set_type(node, None)
            return

        member = self.services.resolve_class_attribute_member(
            class_,
            node.field_name,
            node=node,
        )
        if member is None:
            self.services.set_type(node, None)
            return
        if member.is_static:
            self.services.context.diagnostics.add(
                (
                    f"static attribute '{class_.name}.{node.field_name}' "
                    "must be accessed through the class"
                ),
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return
        if not self.services.member_is_accessible(member):
            self.services.context.diagnostics.add(
                (
                    "class attribute "
                    f"'{self.services.member_display_name(member)}' "
                    "is not accessible from this context"
                ),
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_FIELD_ACCESS,
            )
            self.services.set_type(node, None)
            return
        field = self.services.resolve_class_field_slot(
            class_,
            member,
            visible_name=node.field_name,
        )
        self.services.set_class(node, class_)
        self.services.set_class_field_access(
            node,
            ResolvedClassFieldAccess(class_, member, field),
        )
        self.services.set_type(node, member.type_)
        kind = field_resource(member.type_)
        if kind is not None:
            self.services.set_resource_ownership(
                node,
                ResourceOwnership(
                    kind,
                    (
                        OwnershipKind.OWNED
                        if kind is ResourceKind.STRING
                        else OwnershipKind.BORROWED
                    ),
                    transfer_kind=(
                        OwnershipTransferKind.NONE
                        if kind is ResourceKind.STRING
                        else OwnershipTransferKind.BORROW
                    ),
                ),
            )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: Export this feature's supported nominal node signatures.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return tuple(
            contribute_node(
                "irx.analysis.expression_class_access." + node_type.__name__,
                "irx.analysis.expression_class_access",
                "analysis",
                node_type,
                self.visit,
                source=__name__ + ".ExpressionClassAccessAnalysis.visit",
            )
            for node_type in (
                astx.ClassConstruct,
                astx.MethodCall,
                astx.BaseMethodCall,
                astx.StaticMethodCall,
                astx.BaseFieldAccess,
                astx.StaticFieldAccess,
                astx.FieldAccess,
            )
        )
