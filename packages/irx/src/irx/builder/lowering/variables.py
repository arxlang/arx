# mypy: disable-error-code=no-redef

"""
title: Variable lowering implementations for llvmliteir.
"""

from typing import cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import OwnershipKind, ResourceKind
from irx.analysis.types import is_string_type
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import VariableServices
from irx.builder.runtime import safe_pop
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builder.services.representations import (
    semantic_assignment_key,
    semantic_info,
    semantic_symbol_key,
)
from irx.builder.state import CleanupAction
from irx.builtins.collections.list import (
    LIST_DESTROY_SYMBOL,
    LIST_RUNTIME_FEATURE,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class VariableLowering:
    """
    title: Lower variable declarations and references to LLVM.
    attributes:
      services:
        type: VariableServices
    """

    services: VariableServices

    def __init__(self, services: VariableServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: VariableServices
        """
        self.services = services

    @dispatch
    def visit(self, node: astx.AST) -> None:
        """
        title: Fail closed for nodes not exported by this feature family.
        parameters:
          node:
            type: astx.AST
        """
        raise_lowering_internal_error(
            f"no variables handler for {type(node).__name__}", node=node
        )

    def node_handlers(self) -> tuple[NodeHandler, ...]:
        """
        title: >-
          Export explicit concrete signatures without mutating a shared
          dispatcher.
        returns:
          type: tuple[NodeHandler, Ellipsis]
        """
        return (
            contribute_node(
                "llvm.variables.VariableAssignment",
                "irx.variables",
                "lowering",
                astx.VariableAssignment,
                self.visit,
                source="irx.builder.lowering.variables.VariableLowering.visit",
            ),
            contribute_node(
                "llvm.variables.Identifier",
                "irx.variables",
                "lowering",
                astx.Identifier,
                self.visit,
                source="irx.builder.lowering.variables.VariableLowering.visit",
            ),
            contribute_node(
                "llvm.variables.FieldAccess",
                "irx.variables",
                "lowering",
                astx.FieldAccess,
                self.visit,
                source="irx.builder.lowering.variables.VariableLowering.visit",
            ),
            contribute_node(
                "llvm.variables.BaseFieldAccess",
                "irx.variables",
                "lowering",
                astx.BaseFieldAccess,
                self.visit,
                source="irx.builder.lowering.variables.VariableLowering.visit",
            ),
            contribute_node(
                "llvm.variables.StaticFieldAccess",
                "irx.variables",
                "lowering",
                astx.StaticFieldAccess,
                self.visit,
                source="irx.builder.lowering.variables.VariableLowering.visit",
            ),
            contribute_node(
                "llvm.variables.VariableDeclaration",
                "irx.variables",
                "lowering",
                astx.VariableDeclaration,
                self.visit,
                source="irx.builder.lowering.variables.VariableLowering.visit",
            ),
            contribute_node(
                "llvm.variables.InlineVariableDeclaration",
                "irx.variables",
                "lowering",
                astx.InlineVariableDeclaration,
                self.visit,
                source="irx.builder.lowering.variables.VariableLowering.visit",
            ),
        )

    @private
    def register_generator_cleanup(
        self,
        node: astx.VariableDeclaration | astx.InlineVariableDeclaration,
        storage: ir.Value,
    ) -> None:
        """
        title: Release one validated lexical owner of scalar iterator state.
        parameters:
          node:
            type: astx.VariableDeclaration | astx.InlineVariableDeclaration
          storage:
            type: ir.Value
        """
        if not isinstance(node.type_, astx.GeneratorType):
            return
        ownership = require_semantic_metadata(
            resource_ownership(node),
            node=node,
            metadata="resource_ownership",
            context="generator local cleanup",
        )
        owner = require_semantic_metadata(
            ownership.owner_symbol_id,
            node=node,
            metadata="owner_symbol_id",
            context="generator local cleanup",
        )
        free = self.services.require_runtime_symbol("libc", "free")

        def release_iterator() -> None:
            """
            title: Drop the lexical owner of a scalar-only generator.
            """
            value = self.services.llvm.ir_builder.load(storage)
            frame = self.services.llvm.ir_builder.extract_value(value, 0)
            self.services.llvm.ir_builder.call(free, [frame])

        self.services.exit_state.cleanup_stack.append(
            CleanupAction(
                release_iterator,
                owner_symbol_id=owner,
                fallible=False,
            )
        )

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
        if not isinstance(node.type_, (astx.ListType, astx.Bytes)):
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
        if self.services.generator_frame_state.frame_ptr is not None:
            raise_lowering_internal_error(
                "owned list locals in generator frames require generator "
                "lifecycle cleanup",
                node=node,
            )

        destroy_fn = self.services.require_runtime_symbol(
            LIST_RUNTIME_FEATURE,
            LIST_DESTROY_SYMBOL,
        )

        def destroy_list() -> None:
            """
            title: Destroy the captured list storage.
            """
            self.services.llvm.ir_builder.call(destroy_fn, [list_ptr])

        self.services.exit_state.cleanup_stack.append(
            CleanupAction(
                destroy_list,
                owner_symbol_id=ownership.owner_symbol_id,
                fallible=False,
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
        destroy_fn = self.services.require_runtime_symbol(
            LIST_RUNTIME_FEATURE,
            LIST_DESTROY_SYMBOL,
        )
        self.services.llvm.ir_builder.call(destroy_fn, [list_ptr])

    def _register_owned_string_cleanup(
        self,
        node: astx.AST,
        string_ptr: ir.Value,
    ) -> None:
        """
        title: Register lexical cleanup for one semantically owned string.
        parameters:
          node:
            type: astx.AST
          string_ptr:
            type: ir.Value
        """
        if not isinstance(
            node,
            (
                astx.VariableDeclaration,
                astx.InlineVariableDeclaration,
                astx.Identifier,
            ),
        ):
            raise_lowering_internal_error(
                "owned string cleanup requires a resolved binding target",
                node=node,
            )
        if not is_string_type(resolved_ast_type(node)):
            return
        ownership = resource_ownership(node)
        if ownership is None:
            raise_lowering_internal_error(
                f"string declaration '{node.name}' is missing ownership "
                "metadata",
                node=node,
            )
        if ownership.kind is OwnershipKind.STATIC:
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
        if self.services.generator_frame_state.frame_ptr is not None:
            raise_lowering_internal_error(
                "owned string locals in generator frames require generator "
                "lifecycle cleanup",
                node=node,
            )

        free_fn = self.services.require_runtime_symbol("libc", "free")

        def destroy_string() -> None:
            """
            title: Destroy the currently stored string pointer.
            """
            pointer = self.services.llvm.ir_builder.load(
                string_ptr,
                name=f"{node.name}_string_cleanup",
            )
            self.services.llvm.ir_builder.call(free_fn, [pointer])

        self.services.exit_state.cleanup_stack.append(
            CleanupAction(
                destroy_string,
                owner_symbol_id=ownership.owner_symbol_id,
                fallible=False,
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
        old_pointer = self.services.llvm.ir_builder.load(
            string_ptr,
            name=f"{target_name}_replaced_string",
        )
        free_fn = self.services.require_runtime_symbol("libc", "free")
        self.services.llvm.ir_builder.call(free_fn, [old_pointer])

    @dispatch
    def visit(self, expr: astx.VariableAssignment) -> None:
        """
        title: Visit VariableAssignment nodes.
        parameters:
          expr:
            type: astx.VariableAssignment
        """
        var_name = expr.name
        var_key = semantic_assignment_key(expr)

        if var_key in self.services.function_state.const_vars:
            raise_lowering_internal_error(
                f"Cannot assign to '{var_name}': declared as constant",
                node=expr,
            )

        self.services.visit_child(expr.value)
        llvm_value = safe_pop(self.services.function_state.result_stack)
        if llvm_value is None:
            raise_lowering_internal_error(
                "codegen: Invalid value in VariableAssignment.", node=expr
            )
        llvm_value = self.services.numeric.cast_scalar(
            llvm_value,
            source_type=resolved_ast_type(expr.value),
            target_type=resolved_ast_type(expr),
        )

        llvm_var = self.services.function_state.named_values.get(var_key)
        if not llvm_var:
            raise_lowering_internal_error(
                f"Identifier '{var_name}' not found in the named values.",
                node=expr,
            )

        if isinstance(resolved_ast_type(expr), (astx.ListType, astx.Bytes)):
            self._destroy_replaced_list(
                expr,
                llvm_var,
                target_name=expr.name,
            )
        elif is_string_type(resolved_ast_type(expr)):
            self._destroy_replaced_string(
                expr,
                llvm_var,
                target_name=expr.name,
            )
        self.services.llvm.ir_builder.store(llvm_value, llvm_var)
        self.services.function_state.result_stack.append(llvm_value)

    @dispatch
    def visit(self, node: astx.Identifier) -> None:
        """
        title: Visit Identifier nodes.
        parameters:
          node:
            type: astx.Identifier
        """
        # Namespace references have module identities, not local symbols.
        if semantic_info(node).resolved_symbol is None:
            namespace_value = self.services.layout.namespace_value(node)
            if namespace_value is not None:
                self.services.function_state.result_stack.append(
                    namespace_value
                )
                return

        symbol_key = semantic_symbol_key(node)
        expr_var = self.services.function_state.named_values.get(symbol_key)
        if expr_var:
            result = self.services.llvm.ir_builder.load(expr_var, node.name)
            self.services.function_state.result_stack.append(result)
            return

        namespace_value = self.services.layout.namespace_value(node)
        if namespace_value is not None:
            self.services.function_state.result_stack.append(namespace_value)
            return

        raise_lowering_internal_error(
            f"Unknown variable name: {node.name}", node=node
        )

    @dispatch
    def visit(self, node: astx.FieldAccess) -> None:
        """
        title: Visit FieldAccess nodes.
        parameters:
          node:
            type: astx.FieldAccess
        """
        namespace_value = self.services.layout.namespace_value(node)
        if namespace_value is not None:
            self.services.visit_child(node.value)
            _ = safe_pop(self.services.function_state.result_stack)
            self.services.function_state.result_stack.append(namespace_value)
            return

        resolved_module_member_access = getattr(
            getattr(node, "semantic", None),
            "resolved_module_member_access",
            None,
        )
        if resolved_module_member_access is not None:
            raise_lowering_error(
                (
                    "module namespace member references are lowerable only"
                    " when they resolve to nested namespaces or are used "
                    "in call position"
                ),
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
                hint=(
                    "use namespace.member(...) for callable members, or "
                    "return/bind a namespace-valued member instead"
                ),
            )

        if (
            isinstance(node.value, astx.FieldAccess)
            and getattr(
                getattr(node, "semantic", None),
                "resolved_class_field_access",
                None,
            )
            is None
        ):
            parent_ptr = self.services.layout.field_address(node.value)
            parent_value = self.services.llvm.ir_builder.load(
                parent_ptr,
                f"{node.field_name}_parent",
            )
            resolved = getattr(
                getattr(node, "semantic", None),
                "resolved_field_access",
                None,
            )
            if resolved is None:
                raise_lowering_internal_error(
                    "codegen: unresolved field access.", node=node
                )
            result = self.services.llvm.ir_builder.extract_value(
                parent_value,
                resolved.field.index,
                node.field_name,
            )
            self.services.function_state.result_stack.append(result)
            return

        field_ptr = self.services.layout.field_address(node)
        result = self.services.llvm.ir_builder.load(field_ptr, node.field_name)
        self.services.function_state.result_stack.append(
            self.services.class_field_value(node, result)
        )

    @dispatch
    def visit(self, node: astx.BaseFieldAccess) -> None:
        """
        title: Visit BaseFieldAccess nodes.
        parameters:
          node:
            type: astx.BaseFieldAccess
        """
        field_ptr = self.services.layout.base_class_field_address(node)
        result = self.services.llvm.ir_builder.load(field_ptr, node.field_name)
        self.services.function_state.result_stack.append(
            self.services.class_field_value(node, result)
        )

    @dispatch
    def visit(self, node: astx.StaticFieldAccess) -> None:
        """
        title: Visit StaticFieldAccess nodes.
        parameters:
          node:
            type: astx.StaticFieldAccess
        """
        field_ptr = self.services.layout.static_class_field_address(node)
        result = self.services.llvm.ir_builder.load(field_ptr, node.field_name)
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: astx.VariableDeclaration) -> None:
        """
        title: Visit VariableDeclaration nodes.
        parameters:
          node:
            type: astx.VariableDeclaration
        """
        symbol_key = semantic_symbol_key(node)
        existing_storage = self.services.function_state.named_values.get(
            symbol_key
        )
        if (
            existing_storage
            and self.services.generator_frame_state.frame_ptr is None
        ):
            raise_lowering_internal_error(
                f"Identifier already declared: {node.name}", node=node
            )

        type_str = node.type_.__class__.__name__.lower()
        llvm_type = self.services.types.llvm_type(node.type_)
        if llvm_type is None:
            raise_lowering_internal_error(
                f"codegen: Unknown LLVM type for variable '{node.name}'.",
                node=node,
            )
        if node.value is not None and not isinstance(
            node.value, astx.Undefined
        ):
            self.services.visit_child(node.value)
            init_val = safe_pop(self.services.function_state.result_stack)
            if init_val is None:
                raise_lowering_internal_error(
                    "Initializer code generation failed.", node=node
                )
            init_val = self.services.numeric.cast_scalar(
                init_val,
                source_type=resolved_ast_type(node.value),
                target_type=node.type_,
            )

            if type_str == "string":
                alloca = self.services.create_entry_block_alloca(
                    node.name, "stringascii"
                )
            elif existing_storage is not None:
                alloca = existing_storage
            else:
                alloca = self.services.create_entry_block_alloca(
                    node.name, llvm_type
                )
            self.services.llvm.ir_builder.store(init_val, alloca)
        else:
            if type_str == "string":
                empty_str_type = ir.ArrayType(self.services.llvm.INT8_TYPE, 1)
                empty_str_global = ir.GlobalVariable(
                    self.services.llvm.module,
                    empty_str_type,
                    name=f"empty_str_{node.name}",
                )
                empty_str_global.linkage = "internal"
                empty_str_global.global_constant = True
                empty_str_global.initializer = ir.Constant(
                    empty_str_type, bytearray(b"\0")
                )
                init_val = self.services.llvm.ir_builder.gep(
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
                    else self.services.create_entry_block_alloca(
                        node.name, "stringascii"
                    )
                )
            elif isinstance(node.type_, astx.StructType):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.services.create_entry_block_alloca(
                        node.name, llvm_type
                    )
                )
            elif isinstance(node.type_, (astx.ListType, astx.Bytes)):
                init_val = cast(
                    ir.Constant,
                    self.services.empty_list_value_for_type(node.type_),
                )
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.services.create_entry_block_alloca(
                        node.name, llvm_type
                    )
                )
            elif isinstance(
                node.type_,
                (astx.ClassType, astx.DataFrameType, astx.SeriesType),
            ):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.services.create_entry_block_alloca(
                        node.name, llvm_type
                    )
                )
            elif isinstance(node.type_, astx.GeneratorType):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.services.create_entry_block_alloca(
                        node.name, llvm_type
                    )
                )
            elif isinstance(node.type_, astx.DataFrameType | astx.SeriesType):
                init_val = ir.Constant(llvm_type, None)
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.services.create_entry_block_alloca(
                        node.name, llvm_type
                    )
                )
            elif "float" in type_str:
                init_val = ir.Constant(
                    self.services.llvm.get_data_type(type_str), 0.0
                )
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.services.create_entry_block_alloca(
                        node.name, llvm_type
                    )
                )
            else:
                init_val = ir.Constant(
                    self.services.llvm.get_data_type(type_str), 0
                )
                alloca = (
                    existing_storage
                    if existing_storage is not None
                    else self.services.create_entry_block_alloca(
                        node.name, llvm_type
                    )
                )

            self.services.llvm.ir_builder.store(init_val, alloca)

        if node.mutability == astx.MutabilityKind.constant:
            self.services.function_state.const_vars.add(symbol_key)
        self.services.function_state.named_values[symbol_key] = alloca
        if isinstance(node.type_, astx.FileType):
            ownership = resource_ownership(node)
            if ownership is None or ownership.owner_symbol_id is None:
                raise_lowering_internal_error(
                    "file local is missing ownership", node=node
                )
            self.services.file_cleanup(
                node, init_val, ownership.owner_symbol_id
            )
        if isinstance(
            node.type_, (astx.ClassType, astx.DataFrameType, astx.SeriesType)
        ):
            acquired = self.services.class_acquire(node, init_val)
            self.services.llvm.ir_builder.store(acquired, alloca)
            ownership = resource_ownership(node)
            assert ownership is not None
            self.services.class_cleanup(
                node, alloca, ownership.owner_symbol_id, storage=True
            )
        self._register_owned_list_cleanup(node, alloca)
        self.register_generator_cleanup(node, alloca)
        self._register_owned_string_cleanup(node, alloca)

    @dispatch
    def visit(self, node: astx.InlineVariableDeclaration) -> None:
        """
        title: Visit InlineVariableDeclaration nodes.
        parameters:
          node:
            type: astx.InlineVariableDeclaration
        """
        symbol_key = semantic_symbol_key(node)
        existing_storage = self.services.function_state.named_values.get(
            symbol_key
        )
        if (
            existing_storage
            and self.services.generator_frame_state.frame_ptr is None
        ):
            raise_lowering_internal_error(
                f"Identifier already declared: {node.name}", node=node
            )

        type_str = node.type_.__class__.__name__.lower()
        llvm_type = self.services.types.llvm_type(node.type_)
        if llvm_type is None:
            raise_lowering_internal_error(
                (
                    "codegen: Unknown LLVM type for inline "
                    "variable '"
                    f"{node.name}"
                    "'."
                ),
                node=node,
            )
        if node.value is not None:
            self.services.visit_child(node.value)
            init_val = safe_pop(self.services.function_state.result_stack)
            if init_val is None:
                raise_lowering_internal_error(
                    "Initializer code generation failed.", node=node
                )
            init_val = self.services.numeric.cast_scalar(
                init_val,
                source_type=resolved_ast_type(node.value),
                target_type=node.type_,
            )
        elif isinstance(node.type_, astx.StructType):
            init_val = ir.Constant(llvm_type, None)
        elif isinstance(node.type_, (astx.ListType, astx.Bytes)):
            init_val = cast(
                ir.Constant,
                self.services.empty_list_value_for_type(node.type_),
            )
        elif isinstance(
            node.type_, (astx.ClassType, astx.DataFrameType, astx.SeriesType)
        ):
            init_val = ir.Constant(llvm_type, None)
        elif isinstance(node.type_, astx.GeneratorType):
            init_val = ir.Constant(llvm_type, None)
        elif isinstance(node.type_, astx.DataFrameType | astx.SeriesType):
            init_val = ir.Constant(llvm_type, None)
        elif "float" in type_str:
            init_val = ir.Constant(
                self.services.llvm.get_data_type(type_str), 0.0
            )
        else:
            init_val = ir.Constant(
                self.services.llvm.get_data_type(type_str), 0
            )

        if type_str == "string":
            alloca = self.services.create_entry_block_alloca(
                node.name, "stringascii"
            )
        elif existing_storage is not None:
            alloca = existing_storage
        else:
            alloca = self.services.create_entry_block_alloca(
                node.name, llvm_type
            )

        self.services.llvm.ir_builder.store(init_val, alloca)
        if node.mutability == astx.MutabilityKind.constant:
            self.services.function_state.const_vars.add(symbol_key)
        self.services.function_state.named_values[symbol_key] = alloca
        if isinstance(node.type_, astx.FileType):
            ownership = resource_ownership(node)
            if ownership is None or ownership.owner_symbol_id is None:
                raise_lowering_internal_error(
                    "file local is missing ownership", node=node
                )
            self.services.file_cleanup(
                node, init_val, ownership.owner_symbol_id
            )
        if isinstance(
            node.type_, (astx.ClassType, astx.DataFrameType, astx.SeriesType)
        ):
            acquired = self.services.class_acquire(node, init_val)
            self.services.llvm.ir_builder.store(acquired, alloca)
            ownership = resource_ownership(node)
            assert ownership is not None
            self.services.class_cleanup(
                node, alloca, ownership.owner_symbol_id, storage=True
            )
        self._register_owned_list_cleanup(node, alloca)
        self.register_generator_cleanup(node, alloca)
        self._register_owned_string_cleanup(node, alloca)
        self.services.function_state.result_stack.append(init_val)
