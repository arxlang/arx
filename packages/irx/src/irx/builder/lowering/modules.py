# mypy: disable-error-code=no-redef

"""
title: Module-level visitor mixins for llvmliteir.
"""

from typing import Any, cast

import astx

from llvmlite import ir

from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    ClassHeaderFieldKind,
    OwnershipKind,
    ResourceOwnership,
)
from irx.builder.core import (
    VisitorCore,
    semantic_class_key,
    semantic_class_name,
    semantic_struct_key,
    semantic_struct_name,
)
from irx.builder.protocols import VisitorMixinBase
from irx.builder.types import is_fp_type, is_int_type
from irx.typecheck import typechecked


@typechecked
class ModuleVisitorMixin(VisitorMixinBase):
    def _class_header_llvm_type(
        self,
        kind: ClassHeaderFieldKind,
    ) -> ir.Type:
        """
        title: Return the storage type for one common class header field.
        parameters:
          kind:
            type: ClassHeaderFieldKind
        returns:
          type: ir.Type
        """
        if kind is ClassHeaderFieldKind.REFERENCE_COUNT:
            return self._llvm.INT64_TYPE
        return self._llvm.OPAQUE_POINTER_TYPE

    def _emit_aggregate_field_cleanup(
        self,
        field_name: str,
        slot: ir.Value,
        ownership: ResourceOwnership,
    ) -> None:
        """
        title: Emit fail-closed destructor cleanup for one aggregate field.
        parameters:
          field_name:
            type: str
          slot:
            type: ir.Value
          ownership:
            type: ResourceOwnership
        """
        if ownership.kind is not OwnershipKind.OWNED:
            return
        cast(Any, self).release_resource_slot(ownership, slot)

    def _emit_class_destructor(self, node: astx.ClassDefStmt) -> ir.Function:
        """
        title: Emit reverse-order cleanup and storage release for one class.
        parameters:
          node:
            type: astx.ClassDefStmt
        returns:
          type: ir.Function
        """
        semantic = getattr(node, "semantic", None)
        resolved_class = getattr(semantic, "resolved_class", None)
        layout = getattr(resolved_class, "layout", None)
        if layout is None:
            raise TypeError("class destructor requires resolved layout")
        existing = self._llvm.module.globals.get(layout.destructor_name)
        if existing is not None:
            if not isinstance(existing, ir.Function):
                raise TypeError("class destructor name is not a function")
            return existing

        destructor = ir.Function(
            self._llvm.module,
            ir.FunctionType(
                self._llvm.VOID_TYPE,
                [self._llvm.OPAQUE_POINTER_TYPE],
            ),
            layout.destructor_name,
        )
        destructor.linkage = "internal"
        destructor.args[0].name = "object"
        entry = destructor.append_basic_block("entry")
        previous_builder = self._llvm.ir_builder
        self._llvm.ir_builder = ir.IRBuilder(entry)
        try:
            class_key = semantic_class_key(node, node.name)
            class_type = self.struct_types.get(class_key)
            if not isinstance(class_type, ir.IdentifiedStructType):
                raise TypeError("class destructor requires an LLVM class type")
            object_ptr = self._llvm.ir_builder.bitcast(
                destructor.args[0],
                class_type.as_pointer(),
                name="typed_object",
            )
            for field in reversed(layout.instance_fields):
                ownership = resource_ownership(field.member.declaration)
                if ownership is None:
                    continue
                field_addr = self._llvm.ir_builder.gep(
                    object_ptr,
                    [
                        ir.Constant(self._llvm.INT32_TYPE, 0),
                        ir.Constant(
                            self._llvm.INT32_TYPE,
                            field.storage_index,
                        ),
                    ],
                    inbounds=True,
                    name=f"{field.member.name}_destroy_addr",
                )
                self._emit_aggregate_field_cleanup(
                    field.member.name,
                    field_addr,
                    ownership,
                )
            free = self.require_runtime_symbol("libc", "free")
            self._llvm.ir_builder.call(free, [destructor.args[0]])
            self._llvm.ir_builder.ret_void()
        finally:
            self._llvm.ir_builder = previous_builder
        return destructor

    def _default_global_initializer(self, llvm_type: ir.Type) -> ir.Constant:
        """
        title: Return one zero or null global initializer.
        parameters:
          llvm_type:
            type: ir.Type
        returns:
          type: ir.Constant
        """
        if is_int_type(llvm_type):
            return ir.Constant(llvm_type, 0)
        if is_fp_type(llvm_type):
            return ir.Constant(llvm_type, 0.0)
        return ir.Constant(llvm_type, None)

    def _literal_global_initializer(
        self,
        value: astx.AST | None,
        llvm_type: ir.Type,
    ) -> ir.Constant:
        """
        title: Return one constant initializer for a static class attribute.
        parameters:
          value:
            type: astx.AST | None
          llvm_type:
            type: ir.Type
        returns:
          type: ir.Constant
        """
        if value is None or isinstance(value, astx.Undefined):
            return self._default_global_initializer(llvm_type)
        if isinstance(value, astx.LiteralBoolean):
            return ir.Constant(llvm_type, int(value.value))
        if isinstance(
            value,
            (
                astx.LiteralInt8,
                astx.LiteralInt16,
                astx.LiteralInt32,
                astx.LiteralInt64,
                astx.LiteralUInt8,
                astx.LiteralUInt16,
                astx.LiteralUInt32,
                astx.LiteralUInt64,
                astx.LiteralUInt128,
            ),
        ):
            return ir.Constant(llvm_type, int(value.value))
        if isinstance(
            value,
            (
                astx.LiteralFloat16,
                astx.LiteralFloat32,
                astx.LiteralFloat64,
            ),
        ):
            return ir.Constant(llvm_type, float(value.value))
        if isinstance(value, astx.LiteralNone):
            return ir.Constant(llvm_type, None)
        raise Exception(
            "codegen: static class attribute initializers must be literal "
            "constants in phase 6"
        )

    def _dispatch_table_initializer(
        self,
        node: astx.ClassDefStmt,
    ) -> tuple[ir.ArrayType, ir.Constant] | None:
        """
        title: Return one constant dispatch-table initializer when needed.
        parameters:
          node:
            type: astx.ClassDefStmt
        returns:
          type: tuple[ir.ArrayType, ir.Constant] | None
        """
        semantic = getattr(node, "semantic", None)
        resolved_class = getattr(semantic, "resolved_class", None)
        layout = getattr(resolved_class, "layout", None)
        if layout is None or layout.dispatch_table_size == 0:
            return None
        dispatch_type = ir.ArrayType(
            self._llvm.OPAQUE_POINTER_TYPE,
            layout.dispatch_table_size,
        )
        entries: list[ir.Constant] = []
        for slot_index in range(layout.dispatch_table_size):
            entry = layout.dispatch_slots.get(slot_index)
            if entry is None:
                entries.append(
                    ir.Constant(self._llvm.OPAQUE_POINTER_TYPE, None)
                )
                continue
            function = self._declare_semantic_function(entry.function)
            entries.append(function.bitcast(self._llvm.OPAQUE_POINTER_TYPE))
        return dispatch_type, ir.Constant(dispatch_type, entries)

    def _ensure_identified_type(
        self,
        type_key: str,
        llvm_name: str,
        field_types: list[ir.Type],
    ) -> ir.IdentifiedStructType:
        """
        title: Ensure one identified LLVM type has a body.
        parameters:
          type_key:
            type: str
          llvm_name:
            type: str
          field_types:
            type: list[ir.Type]
        returns:
          type: ir.IdentifiedStructType
        """
        composite_type = self._llvm.module.context.get_identified_type(
            llvm_name
        )
        self.struct_types[type_key] = composite_type
        self.llvm_structs_by_qualified_name[type_key] = composite_type
        if composite_type.is_opaque:
            composite_type.set_body(*field_types)
        return composite_type

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.Module) -> None:
        """
        title: Visit Module nodes.
        parameters:
          node:
            type: astx.Module
        """
        self._translate_modules([node])

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.StructDefStmt) -> None:
        """
        title: Visit StructDefStmt nodes.
        parameters:
          node:
            type: astx.StructDefStmt
        """
        struct_key = semantic_struct_key(node, node.name)
        semantic = getattr(node, "semantic", None)
        resolved_struct = getattr(semantic, "resolved_struct", None)
        fields = (
            resolved_struct.fields
            if resolved_struct is not None and resolved_struct.fields
            else ()
        )
        field_types: list[ir.Type] = []
        for field in fields:
            llvm_type = self._llvm_type_for_ast_type(field.type_)
            if llvm_type is None:
                raise Exception(
                    f"codegen: Unknown LLVM type for struct field "
                    f"'{field.name}'."
                )
            field_types.append(llvm_type)

        self._ensure_identified_type(
            struct_key,
            semantic_struct_name(node, node.name),
            field_types,
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ClassDefStmt) -> None:
        """
        title: Visit ClassDefStmt nodes.
        parameters:
          node:
            type: astx.ClassDefStmt
        """
        class_key = semantic_class_key(node, node.name)
        semantic = getattr(node, "semantic", None)
        resolved_class = getattr(semantic, "resolved_class", None)
        layout = getattr(resolved_class, "layout", None)
        initialization = getattr(resolved_class, "initialization", None)
        if layout is None:
            raise Exception("codegen: unresolved class layout.")
        if initialization is None:
            raise Exception("codegen: unresolved class initialization.")

        field_types: list[ir.Type] = [
            self._class_header_llvm_type(field.kind)
            for field in layout.header_fields
        ]
        for field in layout.instance_fields:
            llvm_type = self._llvm_type_for_ast_type(field.member.type_)
            if llvm_type is None:
                raise Exception(
                    f"codegen: Unknown LLVM type for class field "
                    f"'{field.member.name}'."
                )
            field_types.append(llvm_type)

        self._ensure_identified_type(
            class_key,
            semantic_class_name(node, node.name),
            field_types,
        )
        self._emit_class_destructor(node)

        for static_initializer in initialization.static_initializers:
            storage = static_initializer.storage
            llvm_type = self._llvm_type_for_ast_type(storage.member.type_)
            if llvm_type is None:
                raise Exception(
                    f"codegen: Unknown LLVM type for static class field "
                    f"'{storage.member.name}'."
                )
            initializer = self._literal_global_initializer(
                static_initializer.value,
                llvm_type,
            )
            existing = self._llvm.module.globals.get(storage.global_name)
            if existing is None:
                global_var = ir.GlobalVariable(
                    self._llvm.module,
                    llvm_type,
                    name=storage.global_name,
                )
            else:
                global_var = existing
            global_var.linkage = "internal"
            global_var.global_constant = storage.member.is_constant
            global_var.initializer = initializer

        dispatch_table = self._dispatch_table_initializer(node)
        if dispatch_table is not None:
            dispatch_type, dispatch_initializer = dispatch_table
            dispatch_global = self._llvm.module.globals.get(
                layout.dispatch_global_name
            )
            if dispatch_global is None:
                dispatch_global = ir.GlobalVariable(
                    self._llvm.module,
                    dispatch_type,
                    name=layout.dispatch_global_name,
                )
            dispatch_global.linkage = "internal"
            dispatch_global.global_constant = True
            dispatch_global.initializer = dispatch_initializer

        for method in node.methods:
            if (
                astx.is_template_node(method.prototype)
                or bool(getattr(method.prototype, "is_abstract", False))
                or bool(getattr(method, "is_abstract", False))
            ):
                continue
            self.visit(method)
