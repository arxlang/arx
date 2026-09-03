# mypy: disable-error-code=no-redef
# mypy: disable-error-code=untyped-decorator
# mypy: disable-error-code=attr-defined

"""
title: Array visitor mixin for llvmliteir.
"""

from __future__ import annotations

import astx

from irx.builder.core import VisitorCore
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.arrow.lowering import call_arrow_runtime
from irx.builder.types import is_int_type
from irx.typecheck import typechecked


@typechecked
class ArrayVisitorMixin(VisitorMixinBase):
    """
    title: Array visitor mixin.
    """

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.ArrayInt32ArrayLength) -> None:
        """
        title: Visit ArrayInt32ArrayLength nodes.
        parameters:
          node:
            type: astx.ArrayInt32ArrayLength
        """
        builder_new = self.require_runtime_symbol(
            "array", "irx_arrow_array_builder_int32_new"
        )
        append_int32 = self.require_runtime_symbol(
            "array", "irx_arrow_array_builder_append_int32"
        )
        finish_builder = self.require_runtime_symbol(
            "array", "irx_arrow_array_builder_finish"
        )
        array_length = self.require_runtime_symbol(
            "array", "irx_arrow_array_length"
        )
        release_array = self.require_runtime_symbol(
            "array", "irx_arrow_array_release"
        )

        builder_slot = self._llvm.ir_builder.alloca(
            self._llvm.ARRAY_BUILDER_HANDLE_TYPE,
            name="array_builder_slot",
        )
        call_arrow_runtime(
            self,
            builder_new,
            [builder_slot],
            "array_builder_new",
        )
        builder_handle = self._llvm.ir_builder.load(
            builder_slot, "array_builder"
        )

        for item in node.values:
            self.visit_child(item)
            value = safe_pop(self.result_stack)
            if value is None:
                raise Exception("Array helper expected an integer value")
            if not is_int_type(value.type):
                raise Exception(
                    "Array helper supports only integer expressions"
                )

            if value.type.width < self._llvm.INT32_TYPE.width:
                value = self._llvm.ir_builder.sext(
                    value, self._llvm.INT32_TYPE, "array_i32_promote"
                )
            elif value.type.width > self._llvm.INT32_TYPE.width:
                value = self._llvm.ir_builder.trunc(
                    value, self._llvm.INT32_TYPE, "array_i32_trunc"
                )

            call_arrow_runtime(
                self,
                append_int32,
                [builder_handle, value],
                "array_builder_append",
            )

        array_slot = self._llvm.ir_builder.alloca(
            self._llvm.ARRAY_HANDLE_TYPE,
            name="array_slot",
        )
        call_arrow_runtime(
            self,
            finish_builder,
            [builder_slot, array_slot],
            "array_builder_finish",
        )
        array_handle = self._llvm.ir_builder.load(array_slot, "array_handle")
        length_slot = self._llvm.ir_builder.alloca(
            self._llvm.INT64_TYPE,
            name="array_length_slot",
        )
        call_arrow_runtime(
            self,
            array_length,
            [array_handle, length_slot],
            "array_length",
        )
        length_i64 = self._llvm.ir_builder.load(
            length_slot,
            "array_length",
        )
        call_arrow_runtime(
            self,
            release_array,
            [array_slot],
            "array_release",
        )

        length_i32 = self._llvm.ir_builder.trunc(
            length_i64, self._llvm.INT32_TYPE, "array_length_i32"
        )
        self.result_stack.append(length_i32)


__all__ = ["ArrayVisitorMixin"]
