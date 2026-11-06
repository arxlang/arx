"""
title: Address emission from resolved semantic layouts and storage identities.
summary: >-
  This service never searches source names or rechecks accessibility,
  inheritance, indexing, or mutability. Expression evaluation and class
  lifetime operations are explicit dependencies. Arrow objects remain opaque;
  class descriptors use the existing registered native lifetime contract.
"""

from collections.abc import Callable

import astx

from llvmlite import ir
from public import private

from irx.analysis.module_symbols import mangle_namespace_name
from irx.analysis.resolved_nodes import (
    ClassHeaderFieldKind,
    SemanticClassLayout,
    SemanticClassLayoutField,
)
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.services.representations import (
    TypeLowering,
    resolved_type,
    semantic_info,
)
from irx.typecheck import typechecked


@private
@typechecked
class LayoutEmission:
    """
    title: Narrow field and lvalue addressing for one emitted LLVM module.
    summary: >-
      The service owns no symbol table, expression stack, or class lifetime
      state. Storage lookup uses resolved symbol IDs; evaluated receiver values
      are required and pinned through the injected lifetime operations.
    attributes:
      module:
        type: ir.Module
      builder:
        type: Callable[[], ir.IRBuilder]
      types:
        type: TypeLowering
      evaluate:
        type: Callable[[astx.AST], ir.Value]
      storage:
        type: Callable[[str], ir.Value | None]
      alloca:
        type: Callable[[str, ir.Type], ir.Value]
      require_class:
        type: Callable[[astx.AST, ir.Value], None]
      pin_class:
        type: Callable[[astx.AST, ir.Value], None]
      raw_class:
        type: Callable[[ir.Value], ir.Value]
      namespace_globals:
        type: dict[tuple[str, str], ir.GlobalVariable]
    """

    module: ir.Module
    builder: Callable[[], ir.IRBuilder]
    types: TypeLowering
    evaluate: Callable[[astx.AST], ir.Value]
    storage: Callable[[str], ir.Value | None]
    alloca: Callable[[str, ir.Type], ir.Value]
    require_class: Callable[[astx.AST, ir.Value], None]
    pin_class: Callable[[astx.AST, ir.Value], None]
    raw_class: Callable[[ir.Value], ir.Value]
    namespace_globals: dict[tuple[str, str], ir.GlobalVariable]

    def __init__(
        self,
        module: ir.Module,
        builder: Callable[[], ir.IRBuilder],
        types: TypeLowering,
        evaluate: Callable[[astx.AST], ir.Value],
        storage: Callable[[str], ir.Value | None],
        alloca: Callable[[str, ir.Type], ir.Value],
        require_class: Callable[[astx.AST, ir.Value], None],
        pin_class: Callable[[astx.AST, ir.Value], None],
        raw_class: Callable[[ir.Value], ir.Value],
    ) -> None:
        """
        title: Bind only emission, storage, and class-lifetime dependencies.
        parameters:
          module:
            type: ir.Module
          builder:
            type: Callable[[], ir.IRBuilder]
          types:
            type: TypeLowering
          evaluate:
            type: Callable[[astx.AST], ir.Value]
          storage:
            type: Callable[[str], ir.Value | None]
          alloca:
            type: Callable[[str, ir.Type], ir.Value]
          require_class:
            type: Callable[[astx.AST, ir.Value], None]
          pin_class:
            type: Callable[[astx.AST, ir.Value], None]
          raw_class:
            type: Callable[[ir.Value], ir.Value]
        """
        self.module = module
        self.builder = builder
        self.types = types
        self.evaluate = evaluate
        self.storage = storage
        self.alloca = alloca
        self.require_class = require_class
        self.pin_class = pin_class
        self.raw_class = raw_class
        self.namespace_globals = {}

    def namespace_global(
        self, namespace_type: astx.NamespaceType
    ) -> ir.GlobalVariable:
        """
        title: >-
          Intern the already resolved identity of a module or class namespace.
        parameters:
          namespace_type:
            type: astx.NamespaceType
        returns:
          type: ir.GlobalVariable
        """
        key = (
            namespace_type.namespace_key,
            namespace_type.namespace_kind.value,
        )
        existing = self.namespace_globals.get(key)
        if existing is not None:
            return existing
        name = mangle_namespace_name(*key)
        value = self.module.globals.get(name)
        if value is not None:
            if not isinstance(value, ir.GlobalVariable):
                raise_lowering_internal_error(
                    f"namespace storage collides with non-global '{name}'",
                    node=namespace_type,
                )
            self.namespace_globals[key] = value
            return value
        storage = ir.GlobalVariable(self.module, ir.IntType(8), name=name)
        storage.linkage = "internal"
        storage.global_constant = True
        storage.initializer = ir.Constant(ir.IntType(8), 0)
        self.namespace_globals[key] = storage
        return storage

    def namespace_value_for_type(
        self, namespace_type: astx.NamespaceType
    ) -> ir.Value:
        """
        title: >-
          Lower a namespace handle without importing or looking up a module.
        parameters:
          namespace_type:
            type: astx.NamespaceType
        returns:
          type: ir.Value
        """
        return self.namespace_global(namespace_type).bitcast(
            ir.IntType(8).as_pointer()
        )

    def namespace_value(self, node: astx.AST) -> ir.Value | None:
        """
        title: >-
          Consume semantic module identity or an explicitly resolved namespace
          type.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Value | None
        """
        info = semantic_info(node)
        module = info.resolved_module
        if module is not None:
            return self.namespace_value_for_type(
                astx.NamespaceType(
                    module.module_key,
                    namespace_kind=astx.NamespaceKind.MODULE,
                    display_name=module.display_name,
                )
            )
        type_ = info.resolved_type
        if isinstance(type_, astx.NamespaceType):
            return self.namespace_value_for_type(type_)
        return None

    def symbol_address(self, node: astx.Identifier) -> ir.Value:
        """
        title: Obtain validated storage by resolved symbol identity.
        parameters:
          node:
            type: astx.Identifier
        returns:
          type: ir.Value
        """
        symbol = require_semantic_metadata(
            semantic_info(node).resolved_symbol,
            node=node,
            metadata="resolved_symbol",
            context="lvalue address",
        )
        address = self.storage(symbol.symbol_id)
        if address is None:
            raise_lowering_internal_error(
                f"missing storage for resolved symbol '{symbol.symbol_id}'",
                node=node,
            )
        return address

    def resolved_class_receiver_field_address(
        self,
        *,
        receiver: astx.AST,
        member_name: str,
        layout: SemanticClassLayout,
        field: SemanticClassLayoutField,
    ) -> ir.Value:
        """
        title: Address a resolved field through the concrete class descriptor.
        parameters:
          receiver:
            type: astx.AST
          member_name:
            type: str
          layout:
            type: SemanticClassLayout
          field:
            type: SemanticClassLayoutField
        returns:
          type: ir.Value
        """
        base_value = self.evaluate(receiver)
        self.require_class(receiver, base_value)
        self.pin_class(receiver, base_value)
        descriptor_field = next(
            (
                header
                for header in layout.header_fields
                if header.kind is ClassHeaderFieldKind.TYPE_DESCRIPTOR
            ),
            None,
        )
        if descriptor_field is None:
            raise_lowering_internal_error(
                "class layout has no type descriptor field", node=receiver
            )
        integer = ir.IntType(32)
        descriptor_slot = self.builder().gep(
            base_value,
            [
                ir.Constant(integer, 0),
                ir.Constant(integer, descriptor_field.storage_index),
            ],
            inbounds=True,
        )
        pointer = ir.IntType(8).as_pointer()
        function_type = ir.FunctionType(pointer, [pointer, integer])
        descriptor = self.builder().bitcast(
            self.builder().load(descriptor_slot),
            function_type.as_pointer(),
        )
        address = self.builder().call(
            descriptor,
            [
                self.raw_class(base_value),
                ir.Constant(integer, field.access_index),
            ],
            name=f"{member_name}_raw_addr",
        )
        self.require_class(receiver, address)
        llvm_type = require_semantic_metadata(
            self.types.llvm_type(field.member.type_),
            node=receiver,
            metadata="field LLVM type",
            context="class field address",
        )
        return self.builder().bitcast(
            address, llvm_type.as_pointer(), name=f"{member_name}_addr"
        )

    def field_address(self, node: astx.FieldAccess) -> ir.Value:
        """
        title: Emit an address using the resolved class or struct field plan.
        parameters:
          node:
            type: astx.FieldAccess
        returns:
          type: ir.Value
        """
        info = semantic_info(node)
        class_field = info.resolved_class_field_access
        if class_field is not None:
            layout = require_semantic_metadata(
                class_field.class_.layout,
                node=node,
                metadata="layout",
                context="class field address",
            )
            return self.resolved_class_receiver_field_address(
                receiver=node.value,
                member_name=class_field.member.name,
                layout=layout,
                field=class_field.field,
            )
        struct_field = require_semantic_metadata(
            info.resolved_field_access,
            node=node,
            metadata="resolved_field_access",
            context="struct field address",
        )
        if isinstance(node.value, astx.Identifier):
            base_ptr = self.symbol_address(node.value)
        elif isinstance(node.value, astx.FieldAccess):
            base_ptr = self.field_address(node.value)
        else:
            base_value = self.evaluate(node.value)
            llvm_type = require_semantic_metadata(
                self.types.llvm_type(resolved_type(node.value)),
                node=node.value,
                metadata="struct LLVM type",
                context="struct field address",
            )
            base_ptr = self.alloca(f"fieldtmp_{id(node.value)}", llvm_type)
            self.builder().store(base_value, base_ptr)
        indices = [
            ir.Constant(ir.IntType(32), 0),
            ir.Constant(ir.IntType(32), struct_field.field.index),
        ]
        if isinstance(node.value, astx.FieldAccess):
            llvm_type = require_semantic_metadata(
                self.types.llvm_type(resolved_type(node.value)),
                node=node.value,
                metadata="struct LLVM type",
                context="nested struct field address",
            )
            pointer = llvm_type.as_pointer()
            if base_ptr.type != pointer:
                base_ptr = self.builder().bitcast(
                    base_ptr,
                    pointer,
                    name=f"{struct_field.field.name}_baseptr",
                )
        return self.builder().gep(
            base_ptr,
            indices,
            inbounds=True,
            name=f"{struct_field.field.name}_addr",
        )

    def base_class_field_address(self, node: astx.BaseFieldAccess) -> ir.Value:
        """
        title: >-
          Address an explicit base field without reconstructing inheritance.
        parameters:
          node:
            type: astx.BaseFieldAccess
        returns:
          type: ir.Value
        """
        field = require_semantic_metadata(
            semantic_info(node).resolved_base_class_field_access,
            node=node,
            metadata="resolved_base_class_field_access",
            context="base field address",
        )
        layout = require_semantic_metadata(
            field.receiver_class.layout,
            node=node,
            metadata="layout",
            context="base field address",
        )
        return self.resolved_class_receiver_field_address(
            receiver=node.receiver,
            member_name=field.member.name,
            layout=layout,
            field=field.field,
        )

    def static_class_field_address(
        self, node: astx.StaticFieldAccess
    ) -> ir.Value:
        """
        title: Find static storage only through its resolved emitted identity.
        parameters:
          node:
            type: astx.StaticFieldAccess
        returns:
          type: ir.Value
        """
        field = require_semantic_metadata(
            semantic_info(node).resolved_static_class_field_access,
            node=node,
            metadata="resolved_static_class_field_access",
            context="static field address",
        )
        global_name = field.storage.global_name
        value = self.module.globals.get(global_name)
        if value is None:
            raise_lowering_internal_error(
                f"missing static class field global '{global_name}'", node=node
            )
        return value

    def lvalue_address(self, node: astx.AST) -> ir.Value:
        """
        title: Address the lvalue form already validated by semantic analysis.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Value
        """
        if isinstance(node, astx.Identifier):
            return self.symbol_address(node)
        if isinstance(node, astx.FieldAccess):
            return self.field_address(node)
        if isinstance(node, astx.BaseFieldAccess):
            return self.base_class_field_address(node)
        if isinstance(node, astx.StaticFieldAccess):
            return self.static_class_field_address(node)
        raise_lowering_internal_error(
            "invalid resolved mutable target", node=node
        )
