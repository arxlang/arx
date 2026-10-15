# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
"""
title: First-class primitive arrays through the registered opaque Arrow ABI.
"""

from __future__ import annotations

from typing import cast

import astx

from llvmlite import ir

from irx.analysis.array_values import ResolvedArray
from irx.analysis.ownership import arrow_resource_ownership
from irx.analysis.resolved_nodes import (
    OwnershipKind,
    ResourceKind,
    SemanticInfo,
)
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.lowering.descriptors import DescriptorLoweringMixin
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.arrow.lowering import (
    call_arrow_runtime,
    require_arrow_runtime_success,
)
from irx.typecheck import typechecked


@typechecked
class ArrayValueLoweringMixin(VisitorMixinBase):
    """
    title: Lower resolved array contracts with explicit status and ownership.
    """

    def array_resolution(self, node: astx.DataType) -> ResolvedArray:
        """
        title: Require semantic metadata and the additive array ABI contract.
        parameters:
          node:
            type: astx.DataType
        returns:
          type: ResolvedArray
        """
        info = getattr(node, "semantic", None)
        if not isinstance(info, SemanticInfo) or info.resolved_array is None:
            raise_lowering_internal_error(
                "missing resolved array operation", node=node
            )
        for feature in info.resolved_array.required_features:
            cast(VisitorCore, self).activate_runtime_feature(feature)
        cast(DescriptorLoweringMixin, self).guard_descriptor_contract(
            node, info.resolved_array.required_feature_version
        )
        return info.resolved_array

    def array_call(
        self, node: astx.AST, symbol: str, arguments: list[ir.Value]
    ) -> None:
        """
        title: Check native status before any operation output is inspected.
        parameters:
          node:
            type: astx.AST
          symbol:
            type: str
          arguments:
            type: list[ir.Value]
        """
        function = self.require_runtime_symbol("array", symbol)
        status, error = call_arrow_runtime(self, function, arguments, symbol)
        cast(VisitorCore, self)._register_resource_slot_cleanup(
            arrow_resource_ownership(ResourceKind.ERROR, OwnershipKind.OWNED),
            error,
        )
        require_arrow_runtime_success(self, node, status, symbol)
        # A successful ABI call leaves no error owner. Keep its failure-only
        # cleanup out of sibling branches whose output slot does not dominate.
        self.cleanup_stack.pop()

    def array_slot(self, type_: ir.Type, name: str) -> ir.Value:
        """
        title: Allocate initialized status output or owner storage.
        parameters:
          type_:
            type: ir.Type
          name:
            type: str
        returns:
          type: ir.Value
        """
        builder = self._llvm.ir_builder
        slot = builder.alloca(type_, name=name)
        builder.store(ir.Constant(type_, None), slot)
        return slot

    def append_array_element(
        self,
        value: astx.Expr,
        actual: astx.DataType,
        resolved: ResolvedArray,
        owner: ir.Value,
    ) -> None:
        """
        title: Append validity separately and never extract a null payload.
        parameters:
          value:
            type: astx.Expr
          actual:
            type: astx.DataType
          resolved:
            type: ResolvedArray
          owner:
            type: ir.Value
        """
        core, builder = cast(VisitorCore, self), self._llvm.ir_builder
        self.visit_child(value)
        aggregate = core._cast_ast_value(
            safe_pop(self.result_stack),
            source_type=actual,
            target_type=astx.NullableType(resolved.element_type),
        )
        managed = isinstance(resolved.element_type, astx.ScalarType)
        valid = (
            builder.icmp_unsigned(
                "!=", aggregate, ir.Constant(aggregate.type, None)
            )
            if managed
            else builder.extract_value(aggregate, 0)
        )
        present = builder.function.append_basic_block("array.append.value")
        absent = builder.function.append_basic_block("array.append.null")
        end = builder.function.append_basic_block("array.append.end")
        builder.cbranch(valid, present, absent)
        builder.position_at_end(present)
        payload = core._cast_ast_value(
            aggregate if managed else builder.extract_value(aggregate, 1),
            source_type=resolved.element_type,
            target_type=resolved.scalar_abi_type,
        )
        self.array_call(value, resolved.symbol, [owner, payload])
        builder.branch(end)
        builder.position_at_end(absent)
        self.array_call(
            value,
            "irx_arrow_array_builder_append_null",
            [
                owner,
                ir.Constant(ir.IntType(64), 1),
            ],
        )
        builder.branch(end)
        builder.position_at_end(end)

    @VisitorCore.visit.dispatch  # type: ignore[attr-defined]
    def visit(self, node: astx.ArrayLiteral) -> None:
        """
        title: Construct an array, reusable builder or chunk sequence.
        parameters:
          node:
            type: astx.ArrayLiteral
        """
        resolved = self.array_resolution(node)
        if isinstance(node.type_, astx.ChunkedArrayType):
            self.chunked_literal(node, resolved)
            return
        if isinstance(node.type_, astx.ArrayBuilderType):
            output = self.array_slot(
                self._llvm.OPAQUE_POINTER_TYPE, "array.builder.output"
            )
            self.new_array_builder(node, resolved, output)
            result = self._llvm.ir_builder.load(output)
            cast(VisitorCore, self)._register_owned_resource_temporary(
                node, result
            )
            self.result_stack.append(result)
            return
        core, builder = cast(VisitorCore, self), self._llvm.ir_builder
        current = builder.block
        owner = core.create_entry_block_alloca(
            "array.builder", self._llvm.OPAQUE_POINTER_TYPE
        )
        initializer = ir.IRBuilder(builder.function.entry_basic_block)
        initializer.position_after(owner)
        initializer.store(
            ir.Constant(self._llvm.OPAQUE_POINTER_TYPE, None), owner
        )
        builder.position_at_end(current)
        core._register_resource_slot_cleanup(
            arrow_resource_ownership(
                ResourceKind.ARRAY_BUILDER, OwnershipKind.OWNED
            ),
            owner,
        )
        self.new_array_builder(node, resolved, owner)
        pointer = builder.load(owner)
        for value, actual in zip(
            resolved.arguments or node.values,
            resolved.argument_types,
            strict=True,
        ):
            self.append_array_element(value, actual, resolved, pointer)
        output = self.array_slot(
            self._llvm.OPAQUE_POINTER_TYPE, "array.result"
        )
        assert isinstance(resolved.result_type, astx.ArrayType)
        self.array_call(
            node,
            "irx_arrow_array_builder_build"
            if resolved.descriptor
            else "irx_arrow_array_builder_finish_typed",
            [
                pointer if resolved.descriptor else owner,
                ir.Constant(
                    ir.IntType(32), int(resolved.result_type.nullable)
                ),
                output,
            ],
        )
        result = builder.load(output)
        core._register_owned_resource_temporary(node, result)
        self.result_stack.append(result)

    def array_type_operand(self, resolved: ResolvedArray) -> ir.Value:
        """
        title: Lower an analyzed descriptor or the stable primitive storage id.
        parameters:
          resolved:
            type: ResolvedArray
        returns:
          type: ir.Value
        """
        if resolved.descriptor is None:
            return ir.Constant(ir.IntType(32), resolved.type_id)
        self.visit_child(resolved.descriptor)
        value = safe_pop(self.result_stack)
        if value is None:
            raise_lowering_internal_error("missing logical array descriptor")
        return value

    def new_array_builder(
        self,
        node: astx.ArrayLiteral,
        resolved: ResolvedArray,
        output: ir.Value,
    ) -> None:
        """
        title: Select the resolved primitive or descriptor-driven builder ABI.
        parameters:
          node:
            type: astx.ArrayLiteral
          resolved:
            type: ResolvedArray
          output:
            type: ir.Value
        """
        self.array_call(
            node,
            "irx_arrow_array_builder_new_logical"
            if resolved.descriptor
            else "irx_arrow_array_builder_new",
            [self.array_type_operand(resolved), output],
        )

    def chunked_literal(
        self, node: astx.ArrayLiteral, resolved: ResolvedArray
    ) -> None:
        """
        title: Borrow constructor chunks and publish an independent owner.
        parameters:
          node:
            type: astx.ArrayLiteral
          resolved:
            type: ResolvedArray
        """
        core, builder = cast(VisitorCore, self), self._llvm.ir_builder
        pointer = self._llvm.OPAQUE_POINTER_TYPE
        count = len(node.values)
        slots = builder.alloca(ir.ArrayType(pointer, max(count, 1)))
        zero = ir.Constant(ir.IntType(32), 0)
        for index, value in enumerate(node.values):
            self.visit_child(value)
            chunk = safe_pop(self.result_stack)
            if chunk is None:
                raise_lowering_internal_error(
                    "missing chunk value", node=value
                )
            slot = builder.gep(
                slots, [zero, ir.Constant(ir.IntType(32), index)]
            )
            builder.store(chunk, slot)
        output = self.array_slot(pointer, "chunked.output")
        self.array_call(
            node,
            "irx_arrow_chunked_new_logical"
            if resolved.descriptor
            else "irx_arrow_chunked_new",
            [
                self.array_type_operand(resolved),
                ir.Constant(ir.IntType(32), int(node.type_.nullable)),
                builder.gep(slots, [zero, zero]),
                ir.Constant(ir.IntType(64), count),
                output,
            ],
        )
        result = builder.load(output)
        core._register_owned_resource_temporary(node, result)
        self.result_stack.append(result)

    def array_scalar_result(
        self,
        node: astx.ArrayQuery,
        resolved: ResolvedArray,
        arguments: list[ir.Value],
    ) -> ir.Value:
        """
        title: Read payload output only after successful status and validity.
        parameters:
          node:
            type: astx.ArrayQuery
          resolved:
            type: ResolvedArray
          arguments:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        core, builder = cast(VisitorCore, self), self._llvm.ir_builder
        valid = self.array_slot(ir.IntType(32), "array.scalar.valid")
        payload_type = core._llvm_type_for_ast_type(resolved.scalar_abi_type)
        result_type = core._llvm_type_for_ast_type(resolved.result_type)
        assert payload_type is not None and result_type is not None
        payload = self.array_slot(payload_type, "array.scalar.payload")
        self.array_call(node, resolved.symbol, [*arguments, valid, payload])
        is_valid = builder.icmp_signed(
            "!=", builder.load(valid), ir.Constant(ir.IntType(32), 0)
        )
        origin = builder.block
        success = builder.function.append_basic_block("array.scalar.present")
        end = builder.function.append_basic_block("array.scalar.end")
        builder.cbranch(is_valid, success, end)
        builder.position_at_end(success)
        value = core._cast_ast_value(
            builder.load(payload),
            source_type=resolved.scalar_abi_type,
            target_type=resolved.element_type,
        )
        result = core._cast_ast_value(
            value,
            source_type=resolved.element_type,
            target_type=resolved.result_type,
        )
        builder.branch(end)
        builder.position_at_end(end)
        phi = builder.phi(result_type, "array.scalar.result")
        phi.add_incoming(ir.Constant(result_type, None), origin)
        phi.add_incoming(result, success)
        return phi

    @VisitorCore.visit.dispatch  # type: ignore[attr-defined]
    def visit(self, node: astx.ArrayQuery) -> None:
        """
        title: Lower array inspection or immutable transformations by sidecar.
        parameters:
          node:
            type: astx.ArrayQuery
        """
        resolved = self.array_resolution(node)
        core, builder = cast(VisitorCore, self), self._llvm.ir_builder
        operands = (
            resolved.arguments
            if resolved.arguments is not None
            else node.arguments
        )
        if resolved.operation is astx.ArrayOperation.APPEND:
            self.visit_child(operands[0])
            owner = safe_pop(self.result_stack)
            if owner is None:
                raise_lowering_internal_error("missing builder", node=node)
            self.append_array_element(
                operands[1], resolved.argument_types[1], resolved, owner
            )
            return
        arguments: list[ir.Value] = []
        for index, (argument, actual) in enumerate(
            zip(operands, resolved.argument_types, strict=True)
        ):
            self.visit_child(argument)
            value = safe_pop(self.result_stack)
            if value is None:
                raise_lowering_internal_error(
                    "array argument has no value", node=argument
                )
            if index and resolved.operation in {
                astx.ArrayOperation.AT,
                astx.ArrayOperation.SLICE,
                astx.ArrayOperation.CHUNK_AT,
                astx.ArrayOperation.RESERVE,
            }:
                value = core._cast_ast_value(
                    value, source_type=actual, target_type=astx.Int64()
                )
            arguments.append(value)
        if resolved.operation is astx.ArrayOperation.FROM_BUFFER:
            view = builder.alloca(arguments[0].type, name="array.buffer.input")
            builder.store(arguments[0], view)
            arguments = [ir.Constant(ir.IntType(32), resolved.type_id), view]
        if resolved.operation is astx.ArrayOperation.AT and isinstance(
            resolved.element_type, astx.ScalarType
        ):
            output = self.array_slot(
                self._llvm.OPAQUE_POINTER_TYPE, "array.scalar.owner"
            )
            self.array_call(node, resolved.symbol, [*arguments, output])
            result = builder.load(output)
            core._register_owned_resource_temporary(node, result)
            self.result_stack.append(result)
            return
        if resolved.operation is astx.ArrayOperation.AT:
            self.result_stack.append(
                self.array_scalar_result(node, resolved, arguments)
            )
            return
        if resolved.operation is astx.ArrayOperation.RESERVE:
            self.array_call(node, resolved.symbol, arguments)
            return
        if resolved.operation is astx.ArrayOperation.FINISH:
            assert isinstance(resolved.result_type, astx.ArrayType)
            arguments.append(
                ir.Constant(ir.IntType(32), int(resolved.result_type.nullable))
            )
        output_type = core._llvm_type_for_ast_type(resolved.result_type)
        if resolved.operation is astx.ArrayOperation.EQUAL:
            output_type = ir.IntType(32)
        assert output_type is not None
        output = self.array_slot(output_type, "array.output")
        self.array_call(node, resolved.symbol, [*arguments, output])
        result = builder.load(output)
        if resolved.operation is astx.ArrayOperation.EQUAL:
            result = builder.icmp_signed(
                "!=", result, ir.Constant(ir.IntType(32), 0)
            )
        if isinstance(
            resolved.result_type, (astx.ArrayType, astx.ChunkedArrayType)
        ):
            core._register_owned_resource_temporary(node, result)
        self.result_stack.append(result)
