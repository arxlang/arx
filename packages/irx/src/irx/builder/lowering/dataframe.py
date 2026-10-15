# mypy: disable-error-code=no-redef

"""
title: DataFrame visitor mixin for llvmliteir.
"""

from __future__ import annotations

from typing import Any, cast

import astx

from llvmlite import ir

from irx.analysis.ownership import arrow_resource_ownership
from irx.analysis.resolved_nodes import OwnershipKind, ResourceKind
from irx.analysis.types import is_float_type, is_unsigned_type
from irx.builder.core import VisitorCore, semantic_symbol_key
from irx.builder.lowering.tabular import TabularLoweringMixin
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.arrow.lowering import call_arrow_runtime
from irx.builder.runtime.assertions.feature import (
    ASSERT_FAILURE_SYMBOL_NAME,
    ASSERT_RUNTIME_FEATURE_NAME,
)
from irx.builder.types import is_int_type
from irx.builtins.collections.dataframe import (
    DATAFRAME_COLUMN_INDEX_EXTRA,
    dataframe_type_id,
)
from irx.typecheck import typechecked


@typechecked
class DataFrameVisitorMixin(VisitorMixinBase):
    """
    title: DataFrame visitor mixin.
    """

    def _check_arrow_status(
        self,
        status: ir.Value,
        error_slot: ir.Value,
        operation: str,
    ) -> None:
        """
        title: Branch to the assertion runtime when an Arrow call fails.
        parameters:
          status:
            type: ir.Value
          error_slot:
            type: ir.Value
          operation:
            type: str
        """
        is_ok = self._llvm.ir_builder.icmp_signed(
            "==",
            status,
            ir.Constant(self._llvm.INT32_TYPE, 0),
            f"{operation}_ok",
        )
        counter = getattr(self, "_dataframe_runtime_check_counter", 0)
        setattr(self, "_dataframe_runtime_check_counter", counter + 1)
        function = self._llvm.ir_builder.function
        pass_block = function.append_basic_block(
            f"dataframe_runtime_ok_{counter}"
        )
        fail_block = function.append_basic_block(
            f"dataframe_runtime_fail_{counter}"
        )
        self._llvm.ir_builder.cbranch(is_ok, pass_block, fail_block)

        self._llvm.ir_builder.position_at_start(fail_block)
        self._emit_active_cleanups()
        error_message = self.require_runtime_symbol(
            "core",
            "irx_arrow_error_message",
        )
        error_handle = self._llvm.ir_builder.load(
            error_slot,
            f"{operation}_error",
        )
        message_slot = self._llvm.ir_builder.alloca(
            self._llvm.ASCII_STRING_TYPE,
            name=f"{operation}_message_slot",
        )
        fallback_message = cast(Any, self)._constant_c_string_pointer(
            "Arrow runtime operation failed",
            name_hint="arrow_runtime_fallback_message",
        )
        self._llvm.ir_builder.store(fallback_message, message_slot)
        accessor_error_slot = self._llvm.ir_builder.alloca(
            self._llvm.OPAQUE_POINTER_TYPE,
            name=f"{operation}_accessor_error_slot",
        )
        self._llvm.ir_builder.store(
            ir.Constant(self._llvm.OPAQUE_POINTER_TYPE, None),
            accessor_error_slot,
        )
        self._llvm.ir_builder.call(
            error_message,
            [error_handle, message_slot, accessor_error_slot],
        )
        message_ptr = self._llvm.ir_builder.load(
            message_slot,
            name=f"{operation}_message",
        )
        source_ptr = cast(Any, self)._constant_c_string_pointer(
            "irx-arrow-dataframe",
            name_hint="dataframe_runtime_source",
        )
        fail_function = self.require_runtime_symbol(
            ASSERT_RUNTIME_FEATURE_NAME,
            ASSERT_FAILURE_SYMBOL_NAME,
        )
        self._llvm.ir_builder.call(
            fail_function,
            [
                source_ptr,
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(self._llvm.INT32_TYPE, 0),
                message_ptr,
            ],
        )
        self._llvm.ir_builder.unreachable()

        self._llvm.ir_builder.position_at_start(pass_block)

    def _resource_release_slot(
        self,
        base: astx.AST,
        value: ir.Value,
        *,
        name: str,
    ) -> ir.Value:
        """
        title: Return mutable storage for an explicit resource release.
        summary: >-
          Reuse named local storage so the automatic lexical cleanup observes
          the null token written by the release ABI.
        parameters:
          base:
            type: astx.AST
          value:
            type: ir.Value
          name:
            type: str
        returns:
          type: ir.Value
        """
        if isinstance(base, astx.Identifier):
            symbol_key = semantic_symbol_key(base, base.name)
            storage = self.named_values.get(symbol_key)
            if isinstance(storage, ir.Value):
                return storage
        slot = self._llvm.ir_builder.alloca(value.type, name=name)
        self._llvm.ir_builder.store(value, slot)
        return slot

    def _append_dataframe_value(
        self,
        builder_handle: ir.Value,
        value_node: astx.AST,
        target_type: astx.DataType,
    ) -> None:
        """
        title: Append one lowered scalar value to an Arrow array builder.
        parameters:
          builder_handle:
            type: ir.Value
          value_node:
            type: astx.AST
          target_type:
            type: astx.DataType
        """
        self.visit_child(value_node)
        value = safe_pop(self.result_stack)
        if value is None:
            raise Exception("dataframe column value lowering failed")
        value = self._cast_ast_value(
            value,
            source_type=self._resolved_ast_type(value_node),
            target_type=target_type,
        )

        if is_float_type(target_type):
            append = self.require_runtime_symbol(
                "array",
                "irx_arrow_array_builder_append_double",
            )
            if value.type != self._llvm.DOUBLE_TYPE:
                value = self._llvm.ir_builder.fpext(
                    value,
                    self._llvm.DOUBLE_TYPE,
                    "dataframe_fpext",
                )
            status, error_slot = call_arrow_runtime(
                self,
                append,
                [builder_handle, value],
                "dataframe_append_double",
            )
            self._check_arrow_status(
                status,
                error_slot,
                "dataframe_append_double",
            )
            return

        append = self.require_runtime_symbol(
            "array",
            "irx_arrow_array_builder_append_int",
        )
        if not is_int_type(value.type):
            raise Exception("dataframe column value must lower to a scalar")
        if value.type.width < self._llvm.INT64_TYPE.width:
            if is_unsigned_type(target_type) or isinstance(
                target_type,
                astx.Boolean,
            ):
                value = self._llvm.ir_builder.zext(
                    value,
                    self._llvm.INT64_TYPE,
                    "dataframe_zext",
                )
            else:
                value = self._llvm.ir_builder.sext(
                    value,
                    self._llvm.INT64_TYPE,
                    "dataframe_sext",
                )
        elif value.type.width > self._llvm.INT64_TYPE.width:
            value = self._llvm.ir_builder.trunc(
                value,
                self._llvm.INT64_TYPE,
                "dataframe_trunc",
            )
        status, error_slot = call_arrow_runtime(
            self,
            append,
            [builder_handle, value],
            "dataframe_append_int",
        )
        self._check_arrow_status(
            status,
            error_slot,
            "dataframe_append_int",
        )

    def _build_arrow_array_from_column(
        self,
        column_name: str,
        column_type: astx.DataType,
        values: tuple[astx.AST, ...],
    ) -> ir.Value:
        """
        title: Build one Arrow array handle from column values.
        parameters:
          column_name:
            type: str
          column_type:
            type: astx.DataType
          values:
            type: tuple[astx.AST, Ellipsis]
        returns:
          type: ir.Value
        """
        type_id = dataframe_type_id(column_type)
        if type_id is None:
            raise Exception("unsupported dataframe column type")

        builder_new = self.require_runtime_symbol(
            "array",
            "irx_arrow_array_builder_new",
        )
        finish_builder = self.require_runtime_symbol(
            "array",
            "irx_arrow_array_builder_finish",
        )

        builder_slot = self._llvm.ir_builder.alloca(
            self._llvm.ARRAY_BUILDER_HANDLE_TYPE,
            name=f"{column_name}_array_builder_slot",
        )
        self._llvm.ir_builder.store(
            ir.Constant(self._llvm.ARRAY_BUILDER_HANDLE_TYPE, None),
            builder_slot,
        )
        status, error_slot = call_arrow_runtime(
            self,
            builder_new,
            [
                ir.Constant(self._llvm.INT32_TYPE, type_id),
                builder_slot,
            ],
            "dataframe_array_builder_new",
        )
        self._check_arrow_status(
            status,
            error_slot,
            "dataframe_array_builder_new",
        )
        cast(Any, self)._register_resource_slot_cleanup(
            arrow_resource_ownership(
                ResourceKind.ARRAY_BUILDER,
                OwnershipKind.OWNED,
            ),
            builder_slot,
        )
        builder_handle = self._llvm.ir_builder.load(
            builder_slot,
            f"{column_name}_array_builder",
        )

        for value in values:
            self._append_dataframe_value(builder_handle, value, column_type)

        array_slot = self._llvm.ir_builder.alloca(
            self._llvm.ARRAY_HANDLE_TYPE,
            name=f"{column_name}_array_slot",
        )
        self._llvm.ir_builder.store(
            ir.Constant(self._llvm.ARRAY_HANDLE_TYPE, None),
            array_slot,
        )
        status, error_slot = call_arrow_runtime(
            self,
            finish_builder,
            [builder_slot, array_slot],
            "dataframe_array_builder_finish",
        )
        self._check_arrow_status(
            status,
            error_slot,
            "dataframe_array_builder_finish",
        )
        cast(Any, self)._register_resource_slot_cleanup(
            arrow_resource_ownership(
                ResourceKind.ARRAY,
                OwnershipKind.OWNED,
            ),
            array_slot,
        )
        return self._llvm.ir_builder.load(
            array_slot,
            f"{column_name}_array",
        )

    def _column_index(self, node: astx.DataFrameColumnAccess) -> int | None:
        """
        title: Return the statically resolved column index when available.
        parameters:
          node:
            type: astx.DataFrameColumnAccess
        returns:
          type: int | None
        """
        semantic = getattr(node, "semantic", None)
        extras = getattr(semantic, "extras", {})
        index = extras.get(DATAFRAME_COLUMN_INDEX_EXTRA)
        return index if isinstance(index, int) else None

    def _lower_dataframe_column_access(
        self,
        node: astx.DataFrameColumnAccess,
    ) -> None:
        """
        title: Lower one DataFrame column access node.
        parameters:
          node:
            type: astx.DataFrameColumnAccess
        """
        self.visit_child(node.base)
        table_handle = safe_pop(self.result_stack)
        if table_handle is None:
            raise Exception("dataframe column access requires a table")

        column_slot = self._llvm.ir_builder.alloca(
            self._llvm.CHUNKED_ARRAY_HANDLE_TYPE,
            name="dataframe_column_slot",
        )
        self._llvm.ir_builder.store(
            ir.Constant(self._llvm.CHUNKED_ARRAY_HANDLE_TYPE, None),
            column_slot,
        )
        index = self._column_index(node)
        if index is not None:
            column_by_index = self.require_runtime_symbol(
                "dataframe",
                "irx_arrow_table_column_by_index",
            )
            status, error_slot = call_arrow_runtime(
                self,
                column_by_index,
                [
                    table_handle,
                    ir.Constant(self._llvm.INT32_TYPE, index),
                    column_slot,
                ],
                "dataframe_column_by_index",
            )
            self._check_arrow_status(
                status,
                error_slot,
                "dataframe_column_by_index",
            )
        else:
            column_by_name = self.require_runtime_symbol(
                "dataframe",
                "irx_arrow_table_column_by_name",
            )
            name_pointer = cast(Any, self)._constant_c_string_pointer(
                node.column_name,
                name_hint=f"dataframe_column_{node.column_name}",
            )
            status, error_slot = call_arrow_runtime(
                self,
                column_by_name,
                [table_handle, name_pointer, column_slot],
                "dataframe_column_by_name",
            )
            self._check_arrow_status(
                status,
                error_slot,
                "dataframe_column_by_name",
            )

        column_handle = self._llvm.ir_builder.load(
            column_slot,
            "dataframe_column",
        )
        cast(Any, self)._register_owned_resource_temporary(
            node,
            column_handle,
        )
        self.result_stack.append(column_handle)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DataFrameLiteral) -> None:
        """
        title: Visit DataFrameLiteral nodes.
        parameters:
          node:
            type: astx.DataFrameLiteral
        """
        cast(TabularLoweringMixin, self).lower_tabular_literal(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DataFrameColumnAccess) -> None:
        """
        title: Visit DataFrameColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameColumnAccess
        """
        self._lower_dataframe_column_access(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DataFrameStringColumnAccess) -> None:
        """
        title: Visit DataFrameStringColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameStringColumnAccess
        """
        self._lower_dataframe_column_access(node)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DataFrameRowCount) -> None:
        """
        title: Visit DataFrameRowCount nodes.
        parameters:
          node:
            type: astx.DataFrameRowCount
        """
        self.visit_child(node.base)
        table_handle = safe_pop(self.result_stack)
        if table_handle is None:
            raise Exception("dataframe nrows requires a table")
        nrows = self.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_num_rows",
        )
        result_slot = self._llvm.ir_builder.alloca(
            self._llvm.INT64_TYPE,
            name="dataframe_nrows_slot",
        )
        status, error_slot = call_arrow_runtime(
            self,
            nrows,
            [table_handle, result_slot],
            "dataframe_nrows",
        )
        self._check_arrow_status(status, error_slot, "dataframe_nrows")
        self.result_stack.append(
            self._llvm.ir_builder.load(result_slot, "nrows")
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DataFrameColumnCount) -> None:
        """
        title: Visit DataFrameColumnCount nodes.
        parameters:
          node:
            type: astx.DataFrameColumnCount
        """
        self.visit_child(node.base)
        table_handle = safe_pop(self.result_stack)
        if table_handle is None:
            raise Exception("dataframe ncols requires a table")
        ncols = self.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_num_columns",
        )
        result_slot = self._llvm.ir_builder.alloca(
            self._llvm.INT64_TYPE,
            name="dataframe_ncols_slot",
        )
        status, error_slot = call_arrow_runtime(
            self,
            ncols,
            [table_handle, result_slot],
            "dataframe_ncols",
        )
        self._check_arrow_status(status, error_slot, "dataframe_ncols")
        self.result_stack.append(
            self._llvm.ir_builder.load(result_slot, "ncols")
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DataFrameRetain) -> None:
        """
        title: Visit DataFrameRetain nodes.
        parameters:
          node:
            type: astx.DataFrameRetain
        """
        self.visit_child(node.base)
        table_handle = safe_pop(self.result_stack)
        retain = self.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_retain",
        )
        retained_slot = self._llvm.ir_builder.alloca(
            self._llvm.TABLE_HANDLE_TYPE,
            name="retained_dataframe_slot",
        )
        status, error_slot = call_arrow_runtime(
            self,
            retain,
            [table_handle, retained_slot],
            "dataframe_table_retain",
        )
        self._check_arrow_status(
            status,
            error_slot,
            "dataframe_table_retain",
        )
        self.result_stack.append(status)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.DataFrameRelease) -> None:
        """
        title: Visit DataFrameRelease nodes.
        parameters:
          node:
            type: astx.DataFrameRelease
        """
        self.visit_child(node.base)
        table_handle = safe_pop(self.result_stack)
        release = self.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_release",
        )
        table_slot = self._resource_release_slot(
            node.base,
            table_handle,
            name="released_dataframe_slot",
        )
        status, error_slot = call_arrow_runtime(
            self,
            release,
            [table_slot],
            "dataframe_table_release",
        )
        self._check_arrow_status(
            status,
            error_slot,
            "dataframe_table_release",
        )
        self.result_stack.append(status)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.SeriesRetain) -> None:
        """
        title: Visit SeriesRetain nodes.
        parameters:
          node:
            type: astx.SeriesRetain
        """
        self.visit_child(node.base)
        column_handle = safe_pop(self.result_stack)
        retain = self.require_runtime_symbol(
            "dataframe",
            "irx_arrow_chunked_array_retain",
        )
        retained_slot = self._llvm.ir_builder.alloca(
            self._llvm.CHUNKED_ARRAY_HANDLE_TYPE,
            name="retained_series_slot",
        )
        status, error_slot = call_arrow_runtime(
            self,
            retain,
            [column_handle, retained_slot],
            "dataframe_series_retain",
        )
        self._check_arrow_status(
            status,
            error_slot,
            "dataframe_series_retain",
        )
        self.result_stack.append(status)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.SeriesRelease) -> None:
        """
        title: Visit SeriesRelease nodes.
        parameters:
          node:
            type: astx.SeriesRelease
        """
        self.visit_child(node.base)
        column_handle = safe_pop(self.result_stack)
        release = self.require_runtime_symbol(
            "dataframe",
            "irx_arrow_chunked_array_release",
        )
        column_slot = self._resource_release_slot(
            node.base,
            column_handle,
            name="released_series_slot",
        )
        status, error_slot = call_arrow_runtime(
            self,
            release,
            [column_slot],
            "dataframe_series_release",
        )
        self._check_arrow_status(
            status,
            error_slot,
            "dataframe_series_release",
        )
        self.result_stack.append(status)


__all__ = ["DataFrameVisitorMixin"]
