# mypy: disable-error-code=no-redef

"""
title: Variable visitor mixins for llvmliteir.
"""

from typing import Any, cast

import astx

from llvmlite import ir

from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import OwnershipKind, ResourceKind
from irx.analysis.types import is_string_type
from irx.builder.core import (
    VisitorCore,
    semantic_assignment_key,
    semantic_symbol_key,
)
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
)
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.state import CleanupAction
from irx.builtins.collections.list import (
    LIST_DESTROY_SYMBOL,
    LIST_RUNTIME_FEATURE,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@typechecked
class VariableVisitorMixin(VisitorMixinBase):
    def _register_owned_list_cleanup(
        self,
        node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
        list_ptr: ir.Value,
    ) -> None:
        """
        title: Register lexical cleanup for one semantically owned list local.
        parameters:
          node:
            type: astx.VariableDeclaration | astx.InlineVariableDeclaration
          list_ptr:
            type: ir.Value
        """
        if not isinstance(node.type_, astx.ListType):
            return

        ownership = resource_ownership(node)
        if ownership is None:
            raise_lowering_internal_error(
                f"list declaration '{node.name}' is missing ownership "
                "metadata",
                node=node,
            )
        if ownership.kind is OwnershipKind.STATIC:
            return
        if ownership.kind is not OwnershipKind.OWNED:
            raise_lowering_internal_error(
                f"list declaration '{node.name}' reached lowering with "
                f"unsupported {ownership.kind.value} storage",
                node=node,
            )
        if ownership.owner_symbol_id is None:
            raise_lowering_internal_error(
                f"owned list declaration '{node.name}' is missing its "
                "semantic owner id",
                node=node,
            )
        destroy_fn = self.require_runtime_symbol(
            LIST_RUNTIME_FEATURE,
            LIST_DESTROY_SYMBOL,
        )

        def destroy_list() -> None:
            """
            title: Destroy the captured list storage.
            """
            self._llvm.ir_builder.call(destroy_fn, [list_ptr])

        self.cleanup_stack.append(
            CleanupAction(
                destroy_list,
                owner_symbol_id=ownership.owner_symbol_id,
            )
        )

    def _destroy_replaced_list(
        self,
        node: astx.AST,
        list_ptr: ir.Value,
        *,
        target_name: str,
    ) -> None:
        """
        title: Destroy owned list storage immediately before replacement.
        parameters:
          node:
            type: astx.AST
          list_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        ownership = resource_ownership(node)
        if ownership is None or ownership.kind is not OwnershipKind.OWNED:
            raise_lowering_internal_error(
                f"list assignment to '{target_name}' is missing a validated "
                "ownership transfer",
                node=node,
            )
        destroy_fn = self.require_runtime_symbol(
            LIST_RUNTIME_FEATURE,
            LIST_DESTROY_SYMBOL,
        )
        self._llvm.ir_builder.call(destroy_fn, [list_ptr])

    def _register_owned_string_cleanup(
        self,
        node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
        string_ptr: ir.Value,
    ) -> None:
        """
        title: Register lexical cleanup for one semantically owned string.
        parameters:
          node:
            type: astx.VariableDeclaration | astx.InlineVariableDeclaration
          string_ptr:
            type: ir.Value
        """
        ownership = resource_ownership(node)
        if not is_string_type(node.type_) and (
            ownership is None
            or ownership.resource_kind is not ResourceKind.STRING
        ):
            return
        if ownership is None:
            raise_lowering_internal_error(
                f"string declaration '{node.name}' is missing ownership "
                "metadata",
                node=node,
            )
        if ownership.kind in (OwnershipKind.BORROWED, OwnershipKind.STATIC):
            return
        if (
            ownership.resource_kind is not ResourceKind.STRING
            or ownership.kind is not OwnershipKind.OWNED
            or ownership.owner_symbol_id is None
        ):
            raise_lowering_internal_error(
                f"string declaration '{node.name}' reached lowering with "
                "an invalid ownership contract",
                node=node,
            )
        free_fn = self.require_runtime_symbol("libc", "free")

        def destroy_string() -> None:
            """
            title: Destroy the currently stored string pointer.
            """
            pointer = self._llvm.ir_builder.load(
                string_ptr,
                name=f"{node.name}_string_cleanup",
            )
            self._llvm.ir_builder.call(free_fn, [pointer])
            self._llvm.ir_builder.store(
                ir.Constant(pointer.type, None),
                string_ptr,
            )

        self.cleanup_stack.append(
            CleanupAction(
                destroy_string,
                owner_symbol_id=ownership.owner_symbol_id,
            )
        )

    def _destroy_replaced_string(
        self,
        node: astx.AST,
        string_ptr: ir.Value,
        *,
        target_name: str,
    ) -> None:
        """
        title: Destroy owned string storage before a validated replacement.
        parameters:
          node:
            type: astx.AST
          string_ptr:
            type: ir.Value
          target_name:
            type: str
        """
        ownership = resource_ownership(node)
        if ownership is None:
            raise_lowering_internal_error(
                f"string assignment to '{target_name}' is missing ownership "
                "metadata",
                node=node,
            )
        if ownership.kind is OwnershipKind.STATIC:
            return
        if (
            ownership.resource_kind is not ResourceKind.STRING
            or ownership.kind is not OwnershipKind.OWNED
        ):
            raise_lowering_internal_error(
                f"string assignment to '{target_name}' is missing a "
                "validated ownership transfer",
                node=node,
            )
        old_pointer = self._llvm.ir_builder.load(
            string_ptr,
            name=f"{target_name}_replaced_string",
        )
        free_fn = self.require_runtime_symbol("libc", "free")
        self._llvm.ir_builder.call(free_fn, [old_pointer])

    def _register_owned_native_resource_cleanup(
        self,
        node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
        slot: ir.Value,
    ) -> None:
        """
        title: Register lexical cleanup for one native resource local.
        parameters:
          node:
            type: astx.VariableDeclaration | astx.InlineVariableDeclaration
          slot:
            type: ir.Value
        """
        ownership = resource_ownership(node)
        if ownership is None or (
            not ownership.nullable_aggregate
            and ownership.resource_kind
            in (ResourceKind.LIST, ResourceKind.STRING)
        ):
            return
        if ownership.kind in (OwnershipKind.BORROWED, OwnershipKind.STATIC):
            return
        if (
            ownership.kind is not OwnershipKind.OWNED
            or ownership.owner_symbol_id is None
        ):
            raise_lowering_internal_error(
                f"resource declaration '{node.name}' reached lowering with "
                "an invalid ownership contract",
                node=node,
            )
        cast(Any, self)._register_resource_slot_cleanup(
            ownership,
            slot,
            owner_symbol_id=ownership.owner_symbol_id,
        )

    def _destroy_replaced_native_resource(
        self,
        node: astx.AST,
        slot: ir.Value,
        *,
        target_name: str,
    ) -> None:
        """
        title: Release an owned native token immediately before replacement.
        parameters:
          node:
            type: astx.AST
          slot:
            type: ir.Value
          target_name:
            type: str
        """
        ownership = resource_ownership(node)
        if ownership is None or ownership.kind is not OwnershipKind.OWNED:
            raise_lowering_internal_error(
                f"resource assignment to '{target_name}' is missing a "
                "validated ownership transfer",
                node=node,
            )
        if ownership.nullable_aggregate:
            cast(Any, self).release_resource_slot(ownership, slot)
            return
        if ownership.resource_kind is ResourceKind.STRING:
            self._destroy_replaced_string(node, slot, target_name=target_name)
            return
        release_fn = cast(Any, self).require_runtime_symbol_by_name(
            ownership.cleanup_intrinsic
        )
        if ownership.resource_kind is ResourceKind.BUFFER_VIEW:
            status = self._llvm.ir_builder.call(release_fn, [slot])
            ok = self._llvm.ir_builder.icmp_signed(
                "==",
                status,
                ir.Constant(self._llvm.INT32_TYPE, 0),
                name=f"{target_name}_replacement_release_ok",
            )
            cast(Any, self)._guard_runtime_condition(
                node,
                ok,
                code="ARX-RUNTIME-RESOURCE-003",
                message=(
                    f"failed to release replaced resource '{target_name}'"
                ),
                block_name=f"resource.{target_name}.replace",
            )
            return
        error_slot = self._llvm.ir_builder.alloca(
            self._llvm.OPAQUE_POINTER_TYPE,
            name=f"{target_name}_replacement_error_slot",
        )
        self._llvm.ir_builder.store(
            ir.Constant(self._llvm.OPAQUE_POINTER_TYPE, None),
            error_slot,
        )
        release_slot = slot
        if ownership.resource_kind is ResourceKind.CLASS_INSTANCE:
            release_slot = self._llvm.ir_builder.bitcast(
                slot,
                self._llvm.OPAQUE_POINTER_TYPE.as_pointer(),
                name=f"{target_name}_class_release_slot",
            )
        status = self._llvm.ir_builder.call(
            release_fn,
            [release_slot, error_slot],
        )
        ok = self._llvm.ir_builder.icmp_signed(
            "==",
            status,
            ir.Constant(self._llvm.INT32_TYPE, 0),
            name=f"{target_name}_replacement_release_ok",
        )
        cast(Any, self)._guard_runtime_condition(
            node,
            ok,
            code="ARX-RUNTIME-RESOURCE-003",
            message=f"failed to release replaced resource '{target_name}'",
            block_name=f"resource.{target_name}.replace",
        )

    @VisitorCore.visit.dispatch
    def visit(self, expr: astx.VariableAssignment) -> None:
        """
        title: Visit VariableAssignment nodes.
        parameters:
          expr:
            type: astx.VariableAssignment
        """
        var_name = expr.name
        var_key = semantic_assignment_key(expr, var_name)

        if var_key in self.const_vars:
            raise Exception(
                f"Cannot assign to '{var_name}': declared as constant"
            )

        self.visit_child(expr.value)
        llvm_value = safe_pop(self.result_stack)
        llvm_value = self._cast_ast_value(
            llvm_value,
            source_type=self._resolved_ast_type(expr.value),
            target_type=self._resolved_ast_type(expr),
        )
        llvm_value = cast(Any, self)._retain_copied_resource_value(
            expr.value,
            llvm_value,
            target_type=self._resolved_ast_type(expr),
        )

        llvm_var = self.named_values.get(var_key)
        if not llvm_var:
            raise Exception(
                f"Identifier '{var_name}' not found in the named values."
            )

        ownership = resource_ownership(expr)
        native_ownership = (
            ownership
            if ownership is not None
            and (
                ownership.nullable_aggregate
                or ownership.resource_kind
                not in (ResourceKind.LIST, ResourceKind.STRING)
            )
            else None
        )
        incoming_slot: ir.Value | None = None
        if isinstance(self._resolved_ast_type(expr), astx.ListType):
            self._destroy_replaced_list(
                expr,
                llvm_var,
                target_name=expr.name,
            )
        elif (
            ownership is not None
            and ownership.resource_kind is ResourceKind.STRING
        ):
            self._destroy_replaced_string(
                expr,
                llvm_var,
                target_name=expr.name,
            )
        elif native_ownership is not None:
            incoming_slot = self._llvm.ir_builder.alloca(
                llvm_value.type,
                name=f"{expr.name}_replacement_incoming_slot",
            )
            self._llvm.ir_builder.store(llvm_value, incoming_slot)
            cast(Any, self)._register_resource_slot_cleanup(
                native_ownership,
                incoming_slot,
            )
            self._destroy_replaced_native_resource(
                expr,
                llvm_var,
                target_name=expr.name,
            )
        self._llvm.ir_builder.store(llvm_value, llvm_var)
        if incoming_slot is not None:
            self._llvm.ir_builder.store(
                ir.Constant(llvm_value.type, None),
                incoming_slot,
            )
        self.result_stack.append(llvm_value)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.Identifier) -> None:
        """
        title: Visit Identifier nodes.
        parameters:
          node:
            type: astx.Identifier
        """
        symbol_key = semantic_symbol_key(node, node.name)
        expr_var = self.named_values.get(symbol_key)
        if expr_var:
            result = self._llvm.ir_builder.load(expr_var, node.name)
            if getattr(
                getattr(node, "semantic", None), "nullable_refined", False
            ) and isinstance(result.type, ir.LiteralStructType):
                result = self._llvm.ir_builder.extract_value(
                    result, 1, name="nullable.proven_payload"
                )
            self.result_stack.append(result)
            return

        namespace_value = self._namespace_value(node)
        if namespace_value is not None:
            self.result_stack.append(namespace_value)
            return

        raise Exception(f"Unknown variable name: {node.name}")

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.FieldAccess) -> None:
        """
        title: Visit FieldAccess nodes.
        parameters:
          node:
            type: astx.FieldAccess
        """
        namespace_value = self._namespace_value(node)
        if namespace_value is not None:
            self.visit_child(node.value)
            _ = safe_pop(self.result_stack)
            self.result_stack.append(namespace_value)
            return

        resolved_module_member_access = getattr(
            getattr(node, "semantic", None),
            "resolved_module_member_access",
            None,
        )
        if resolved_module_member_access is not None:
            raise_lowering_error(
                "module namespace member references are lowerable only when "
                "they resolve to nested namespaces or are used in call "
                "position",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
                hint=(
                    "use namespace.member(...) for callable members, or "
                    "return/bind a namespace-valued member instead"
                ),
            )

        if isinstance(node.value, astx.FieldAccess):
            parent_ptr = self._field_address(node.value)
            parent_value = self._llvm.ir_builder.load(
                parent_ptr,
                f"{node.field_name}_parent",
            )
            resolved = getattr(
                getattr(node, "semantic", None),
                "resolved_field_access",
                None,
            )
            if resolved is None:
                raise Exception("codegen: unresolved field access.")
            result = self._llvm.ir_builder.extract_value(
                parent_value,
                resolved.field.index,
                node.field_name,
            )
            self.result_stack.append(result)
            return

        field_ptr = self._field_address(node)
        result = self._llvm.ir_builder.load(field_ptr, node.field_name)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.BaseFieldAccess) -> None:
        """
        title: Visit BaseFieldAccess nodes.
        parameters:
          node:
            type: astx.BaseFieldAccess
        """
        field_ptr = self._base_class_field_address(node)
        result = self._llvm.ir_builder.load(field_ptr, node.field_name)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.StaticFieldAccess) -> None:
        """
        title: Visit StaticFieldAccess nodes.
        parameters:
          node:
            type: astx.StaticFieldAccess
        """
        field_ptr = self._static_class_field_address(node)
        result = self._llvm.ir_builder.load(field_ptr, node.field_name)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.VariableDeclaration) -> None:
        """
        title: Visit VariableDeclaration nodes.
        parameters:
          node:
            type: astx.VariableDeclaration
        """
        symbol_key = semantic_symbol_key(node, node.name)
        existing_storage = self.named_values.get(symbol_key)
        if existing_storage and self._current_generator_frame_ptr is None:
            raise Exception(f"Identifier already declared: {node.name}")

        type_str = node.type_.__class__.__name__.lower()
        llvm_type = self._llvm_type_for_ast_type(node.type_)
        if llvm_type is None:
            raise Exception(
                f"codegen: Unknown LLVM type for variable '{node.name}'."
            )
        if node.value is not None and not isinstance(
            node.value, astx.Undefined
        ):
            self.visit_child(node.value)
            init_val = safe_pop(self.result_stack)
            init_val = self._cast_ast_value(
                init_val,
                source_type=self._resolved_ast_type(node.value),
                target_type=node.type_,
            )
            init_val = cast(Any, self)._retain_copied_resource_value(
                node.value,
                init_val,
                target_type=node.type_,
            )

            if type_str == "string":
                alloca = self.create_entry_block_alloca(
                    node.name, "stringascii"
                )
            elif existing_storage is not None:
                alloca = existing_storage
            else:
                alloca = self.create_entry_block_alloca(node.name, llvm_type)
            self._llvm.ir_builder.store(init_val, alloca)
        else:
            if type_str == "string":
                empty_str_type = ir.ArrayType(self._llvm.INT8_TYPE, 1)
                empty_str_global = ir.GlobalVariable(
                    self._llvm.module,
                    empty_str_type,
                    name=self._llvm.module.get_unique_name(
                        f"empty_str_{node.name}"
                    ),
                )
                empty_str_global.linkage = "internal"
                empty_str_global.global_constant = True
                empty_str_global.initializer = ir.Constant(
                    empty_str_type, bytearray(b"\0")
                )
                init_val = self._llvm.ir_builder.gep(
                    empty_str_global,
                    [
                        ir.Constant(ir.IntType(32), 0),
                        ir.Constant(ir.IntType(32), 0),
                    ],
                    inbounds=True,
                )
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(
                        node.name, "stringascii"
                    )
                )
            elif isinstance(node.type_, astx.StructType):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(node.name, llvm_type)
                )
            elif isinstance(node.type_, astx.ListType):
                init_val = cast(
                    ir.Constant,
                    cast(Any, self)._empty_list_value_for_type(node.type_),
                )
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(node.name, llvm_type)
                )
            elif isinstance(node.type_, astx.ClassType):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(node.name, llvm_type)
                )
            elif isinstance(
                node.type_, (astx.GeneratorType, astx.NullableType)
            ):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(node.name, llvm_type)
                )
            elif isinstance(
                node.type_,
                (
                    astx.BufferViewType,
                    astx.DataFrameType,
                    astx.CDataType,
                    astx.SchemaType,
                    astx.FieldType,
                    astx.TypeDescriptorType,
                    astx.SeriesType,
                    astx.TensorType,
                ),
            ):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(node.name, llvm_type)
                )
            elif "float" in type_str:
                init_val = ir.Constant(self._llvm.get_data_type(type_str), 0.0)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(node.name, llvm_type)
                )
            else:
                init_val = ir.Constant(self._llvm.get_data_type(type_str), 0)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.create_entry_block_alloca(node.name, llvm_type)
                )

            ownership = resource_ownership(node)
            if (
                is_string_type(node.type_)
                and ownership is not None
                and ownership.kind is OwnershipKind.OWNED
            ):
                init_val = self._copy_string_to_heap(node, init_val)
            self._llvm.ir_builder.store(init_val, alloca)

        if node.mutability == astx.MutabilityKind.constant:
            self.const_vars.add(symbol_key)
        self.named_values[symbol_key] = alloca
        self._register_owned_list_cleanup(node, alloca)
        self._register_owned_string_cleanup(node, alloca)
        self._register_owned_native_resource_cleanup(node, alloca)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.InlineVariableDeclaration) -> None:
        """
        title: Visit InlineVariableDeclaration nodes.
        parameters:
          node:
            type: astx.InlineVariableDeclaration
        """
        symbol_key = semantic_symbol_key(node, node.name)
        existing_storage = self.named_values.get(symbol_key)
        if existing_storage and self._current_generator_frame_ptr is None:
            raise Exception(f"Identifier already declared: {node.name}")

        type_str = node.type_.__class__.__name__.lower()
        llvm_type = self._llvm_type_for_ast_type(node.type_)
        if llvm_type is None:
            raise Exception(
                "codegen: Unknown LLVM type for inline variable "
                f"'{node.name}'."
            )
        if node.value is not None:
            self.visit_child(node.value)
            init_val = safe_pop(self.result_stack)
            init_val = self._cast_ast_value(
                init_val,
                source_type=self._resolved_ast_type(node.value),
                target_type=node.type_,
            )
            init_val = cast(Any, self)._retain_copied_resource_value(
                node.value,
                init_val,
                target_type=node.type_,
            )
        elif isinstance(node.type_, astx.String):
            empty = cast(Any, self)._constant_c_string_pointer(
                "", name_hint="inline_default_string"
            )
            ownership = resource_ownership(node)
            init_val = (
                self._copy_string_to_heap(node, empty)
                if ownership is not None
                and ownership.kind is OwnershipKind.OWNED
                else empty
            )
        elif isinstance(node.type_, astx.StructType):
            init_val = ir.Constant(llvm_type, None)
        elif isinstance(node.type_, astx.ListType):
            init_val = cast(
                ir.Constant,
                cast(Any, self)._empty_list_value_for_type(node.type_),
            )
        elif isinstance(node.type_, astx.ClassType):
            init_val = ir.Constant(llvm_type, None)
        elif isinstance(node.type_, (astx.GeneratorType, astx.NullableType)):
            init_val = ir.Constant(llvm_type, None)
        elif isinstance(
            node.type_,
            (
                astx.BufferViewType,
                astx.DataFrameType,
                astx.CDataType,
                astx.SchemaType,
                astx.FieldType,
                astx.TypeDescriptorType,
                astx.SeriesType,
                astx.TensorType,
            ),
        ):
            init_val = ir.Constant(llvm_type, None)
        elif "float" in type_str:
            init_val = ir.Constant(self._llvm.get_data_type(type_str), 0.0)
        else:
            init_val = ir.Constant(self._llvm.get_data_type(type_str), 0)

        if type_str == "string":
            alloca = self.create_entry_block_alloca(node.name, "stringascii")
        elif existing_storage is not None:
            alloca = existing_storage
        else:
            alloca = self.create_entry_block_alloca(node.name, llvm_type)

        self._llvm.ir_builder.store(init_val, alloca)
        if node.mutability == astx.MutabilityKind.constant:
            self.const_vars.add(symbol_key)
        self.named_values[symbol_key] = alloca
        self._register_owned_list_cleanup(node, alloca)
        self._register_owned_string_cleanup(node, alloca)
        self._register_owned_native_resource_cleanup(node, alloca)
        self.result_stack.append(init_val)
