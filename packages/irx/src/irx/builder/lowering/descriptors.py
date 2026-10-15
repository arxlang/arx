# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: Lower resolved descriptor literals and queries through the opaque C ABI.
"""

from __future__ import annotations

import struct

from typing import cast

import astx

from llvmlite import ir

from irx.analysis.ownership import arrow_resource_ownership
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    ResourceKind,
    SemanticInfo,
)
from irx.analysis.schema_descriptors import DescriptorOutput, ResolvedCSchema
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.arrow.abi_generated import RUNTIME_FEATURE_IDS
from irx.builder.runtime.arrow.lowering import (
    call_arrow_runtime,
    require_arrow_runtime_success,
)
from irx.typecheck import typechecked

NATIVE_INDEX_BITS = 64


@typechecked
class DescriptorLoweringMixin(VisitorMixinBase):
    """
    title: Emit only pre-resolved C Data facts, never Arrow C++ layouts.
    """

    def descriptor_bytes(self, data: bytes) -> ir.Constant:
        """
        title: Materialize immutable bytes with module-local lifetime.
        parameters:
          data:
            type: bytes
        returns:
          type: ir.Constant
        """
        type_ = ir.ArrayType(ir.IntType(8), len(data))
        module = self._llvm.module
        value = ir.GlobalVariable(
            module, type_, module.get_unique_name("descriptor.bytes")
        )
        value.linkage = "internal"
        value.global_constant = True
        value.initializer = ir.Constant(type_, bytearray(data))
        return value.bitcast(self._llvm.OPAQUE_POINTER_TYPE)

    def descriptor_release_callback(self) -> ir.Constant:
        """
        title: >-
          Supply a valid release marker for synchronously copied static
          schemas.
        returns:
          type: ir.Constant
        """
        module = self._llvm.module
        name = "irx.descriptor.static.release"
        existing = module.globals.get(name)
        if isinstance(existing, ir.Function):
            return existing.bitcast(self._llvm.OPAQUE_POINTER_TYPE)
        function = ir.Function(
            module,
            ir.FunctionType(ir.VoidType(), [self._llvm.OPAQUE_POINTER_TYPE]),
            name,
        )
        function.linkage = "internal"
        ir.IRBuilder(function.append_basic_block("entry")).ret_void()
        return function.bitcast(self._llvm.OPAQUE_POINTER_TYPE)

    def descriptor_c_schema(self, tree: ResolvedCSchema) -> ir.Constant:
        """
        title: >-
          Lower a resolved standard C Data schema tree into immutable globals.
        parameters:
          tree:
            type: ResolvedCSchema
        returns:
          type: ir.Constant
        """
        ptr = self._llvm.OPAQUE_POINTER_TYPE
        null = ir.Constant(ptr, None)
        i64 = ir.IntType(64)
        # This is ArrowSchema's published C layout, not an Arrow C++ object.
        schema_type = ir.LiteralStructType(
            [ptr, ptr, ptr, i64, i64, ptr, ptr, ptr, ptr]
        )
        children = null
        if tree.children:
            values = [
                self.descriptor_c_schema(child) for child in tree.children
            ]
            array_type = ir.ArrayType(ptr, len(values))
            array = ir.GlobalVariable(
                self._llvm.module,
                array_type,
                self._llvm.module.get_unique_name("descriptor.children"),
            )
            array.linkage = "internal"
            array.global_constant = True
            array.initializer = ir.Constant(array_type, values)
            children = array.bitcast(ptr)
        # The existing LLVM backend targets the host ABI. C Data metadata uses
        # native-endian int32 lengths, and binary values are never NUL-scanned.
        metadata = bytearray(struct.pack("=i", len(tree.metadata)))
        for key, value in tree.metadata:
            for item in (key, value):
                metadata.extend(struct.pack("=i", len(item)))
                metadata.extend(item)
        values = [
            self.descriptor_bytes(
                tree.physical.c_format.encode("utf8") + b"\0"
            ),
            self.descriptor_bytes(tree.name.encode("utf8") + b"\0"),
            self.descriptor_bytes(bytes(metadata)),
            ir.Constant(i64, tree.flags),
            ir.Constant(i64, len(tree.children)),
            children,
            self.descriptor_c_schema(tree.dictionary)
            if tree.dictionary
            else null,
            self.descriptor_release_callback(),
            null,
        ]
        schema = ir.GlobalVariable(
            self._llvm.module,
            schema_type,
            self._llvm.module.get_unique_name("descriptor.schema"),
        )
        schema.linkage = "internal"
        schema.global_constant = True
        schema.initializer = ir.Constant(schema_type, values)
        return schema.bitcast(ptr)

    def guard_descriptor_contract(
        self, node: astx.AST, version: int, feature: str = "array"
    ) -> None:
        """
        title: >-
          Check the resolved minimum runtime contract before descriptor calls.
        parameters:
          node:
            type: astx.AST
          version:
            type: int
          feature:
            type: str
        """
        i32 = ir.IntType(32)
        available = self._llvm.ir_builder.alloca(i32)
        supported = self._llvm.ir_builder.alloca(i32)
        function = self.require_runtime_symbol(
            "core", "irx_arrow_runtime_has_feature"
        )
        status, error = call_arrow_runtime(
            self,
            function,
            [
                ir.Constant(i32, RUNTIME_FEATURE_IDS[feature]),
                ir.Constant(i32, version),
                available,
                supported,
            ],
            "descriptor_contract",
        )
        core = cast(VisitorCore, self)
        core._register_resource_slot_cleanup(
            arrow_resource_ownership(ResourceKind.ERROR, OwnershipKind.OWNED),
            error,
        )
        require_arrow_runtime_success(
            self, node, status, "descriptor_contract"
        )
        self.cleanup_stack.pop()
        compatible = self._llvm.ir_builder.icmp_signed(
            "!=",
            self._llvm.ir_builder.load(available),
            ir.Constant(i32, 0),
        )
        core._guard_runtime_condition(
            node,
            compatible,
            code="ARX-RUNTIME-ARROW-ABI-001",
            message="native descriptor feature contract is unavailable",
            block_name="descriptor.contract",
        )

    def emit_descriptor(
        self, node: astx.DataType, arguments: tuple[astx.Expr, ...] = ()
    ) -> None:
        """
        title: >-
          Call the resolved native operation, checking status before outputs.
        parameters:
          node:
            type: astx.DataType
          arguments:
            type: tuple[astx.Expr, Ellipsis]
        """
        semantic = getattr(node, "semantic", None)
        if (
            not isinstance(semantic, SemanticInfo)
            or semantic.resolved_descriptor is None
        ):
            raise_lowering_internal_error(
                "missing resolved descriptor operation", node=node
            )
        resolved = semantic.resolved_descriptor
        core = cast(VisitorCore, self)
        for feature in resolved.required_features:
            core.activate_runtime_feature(feature)
        self.guard_descriptor_contract(node, resolved.required_feature_version)
        function = self.require_runtime_symbol("array", resolved.symbol)
        lowered: list[ir.Value] = []
        for index, argument in enumerate(arguments):
            self.visit_child(argument)
            value = safe_pop(self.result_stack)
            if value is None:
                raise_lowering_internal_error(
                    "descriptor operand produced no value", node=argument
                )
            # Native descriptor indices are signed i64; analysis accepts only
            # signed integers. Never narrow or reinterpret unsigned values.
            if (
                index == 1
                and resolved.index_bit_width is not None
                and resolved.index_bit_width < NATIVE_INDEX_BITS
            ):
                value = self._llvm.ir_builder.sext(value, ir.IntType(64))
            lowered.append(value)
        if resolved.literal is not None:
            lowered.append(self.descriptor_c_schema(resolved.literal))
        output_type: ir.Type = self._llvm.OPAQUE_POINTER_TYPE
        if resolved.output is DescriptorOutput.BOOLEAN:
            output_type = ir.IntType(32)
        elif resolved.output is DescriptorOutput.INT64:
            output_type = ir.IntType(64)
        slot = self._llvm.ir_builder.alloca(
            output_type, name="descriptor.output"
        )
        self._llvm.ir_builder.store(ir.Constant(output_type, None), slot)
        status, error_slot = call_arrow_runtime(
            self, function, [*lowered, slot], resolved.symbol
        )
        core._register_resource_slot_cleanup(
            arrow_resource_ownership(ResourceKind.ERROR, OwnershipKind.OWNED),
            error_slot,
        )
        require_arrow_runtime_success(self, node, status, resolved.symbol)
        self.cleanup_stack.pop()
        result = self._llvm.ir_builder.load(slot)
        if resolved.output is DescriptorOutput.BOOLEAN:
            result = self._llvm.ir_builder.icmp_signed(
                "!=", result, ir.Constant(ir.IntType(32), 0)
            )
        if resolved.output in {
            DescriptorOutput.HANDLE,
            DescriptorOutput.STRING,
        }:
            core._register_owned_resource_temporary(node, result)
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.TypeDescriptorLiteral) -> None:
        """
        title: Lower a type descriptor literal.
        parameters:
          node:
            type: astx.TypeDescriptorLiteral
        """
        self.emit_descriptor(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.FieldLiteral) -> None:
        """
        title: Lower an immutable field literal.
        parameters:
          node:
            type: astx.FieldLiteral
        """
        self.emit_descriptor(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.SchemaLiteral) -> None:
        """
        title: Lower an immutable schema literal.
        parameters:
          node:
            type: astx.SchemaLiteral
        """
        self.emit_descriptor(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DescriptorQuery) -> None:
        """
        title: Lower a semantically resolved descriptor query.
        parameters:
          node:
            type: astx.DescriptorQuery
        """
        self.emit_descriptor(node, node.arguments)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DescriptorCompatibility) -> None:
        """
        title: >-
          Emit an analyzed compatibility constant without runtime allocation.
        parameters:
          node:
            type: astx.DescriptorCompatibility
        """
        semantic = getattr(node, "semantic", None)
        if (
            not isinstance(semantic, SemanticInfo)
            or semantic.resolved_descriptor_conversion is None
        ):
            raise_lowering_internal_error(
                "missing descriptor conversion resolution", node=node
            )
        self.result_stack.append(
            ir.Constant(
                ir.IntType(32), int(semantic.resolved_descriptor_conversion)
            )
        )
