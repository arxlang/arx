# mypy: disable-error-code=no-redef

"""
title: Array lowering implementation for llvmliteir.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private

from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.lowering.contracts import ArrayServices
from irx.builder.runtime import safe_pop
from irx.builder.types import is_int_type
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ArrayLowering:
    """
    title: Array lowering implementation.
    attributes:
      services:
        type: ArrayServices
    """

    services: ArrayServices

    def __init__(self, services: ArrayServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: ArrayServices
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
            f"no array handler for {type(node).__name__}", node=node
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
                "llvm.array.ArrayInt32ArrayLength",
                "irx.array",
                "lowering",
                astx.ArrayInt32ArrayLength,
                self.visit,
                source="irx.builder.lowering.array.ArrayLowering.visit",
            ),
        )

    @dispatch
    def visit(self, node: astx.ArrayInt32ArrayLength) -> None:
        """
        title: Visit ArrayInt32ArrayLength nodes.
        parameters:
          node:
            type: astx.ArrayInt32ArrayLength
        """
        builder_new = self.services.require_runtime_symbol(
            "array", "irx_arrow_array_builder_int32_new"
        )
        append_int32 = self.services.require_runtime_symbol(
            "array", "irx_arrow_array_builder_append_int32"
        )
        finish_builder = self.services.require_runtime_symbol(
            "array", "irx_arrow_array_builder_finish"
        )
        array_length = self.services.require_runtime_symbol(
            "array", "irx_arrow_array_length"
        )
        release_array = self.services.require_runtime_symbol(
            "array", "irx_arrow_array_release"
        )

        builder_slot = self.services.llvm.ir_builder.alloca(
            self.services.llvm.ARRAY_BUILDER_HANDLE_TYPE,
            name="array_builder_slot",
        )
        self.services.llvm.ir_builder.call(builder_new, [builder_slot])
        builder_handle = self.services.llvm.ir_builder.load(
            builder_slot, "array_builder"
        )

        for item in node.values:
            self.services.visit_child(item)
            value = safe_pop(self.services.function_state.result_stack)
            if value is None:
                raise_lowering_internal_error(
                    "Array helper expected an integer value", node=node
                )
            if not is_int_type(value.type):
                raise_lowering_internal_error(
                    "Array helper supports only integer expressions", node=node
                )

            if value.type.width < self.services.llvm.INT32_TYPE.width:
                value = self.services.llvm.ir_builder.sext(
                    value, self.services.llvm.INT32_TYPE, "array_i32_promote"
                )
            elif value.type.width > self.services.llvm.INT32_TYPE.width:
                value = self.services.llvm.ir_builder.trunc(
                    value, self.services.llvm.INT32_TYPE, "array_i32_trunc"
                )

            self.services.llvm.ir_builder.call(
                append_int32, [builder_handle, value]
            )

        array_slot = self.services.llvm.ir_builder.alloca(
            self.services.llvm.ARRAY_HANDLE_TYPE,
            name="array_slot",
        )
        self.services.llvm.ir_builder.call(
            finish_builder, [builder_handle, array_slot]
        )
        array_handle = self.services.llvm.ir_builder.load(
            array_slot, "array_handle"
        )
        length_i64 = self.services.llvm.ir_builder.call(
            array_length, [array_handle], "array_length"
        )
        self.services.llvm.ir_builder.call(release_array, [array_handle])

        length_i32 = self.services.llvm.ir_builder.trunc(
            length_i64, self.services.llvm.INT32_TYPE, "array_length_i32"
        )
        self.services.function_state.result_stack.append(length_i32)
