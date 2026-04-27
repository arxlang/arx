# mypy: disable-error-code=no-redef

"""
title: DataFrame visitor mixin for llvmliteir.
"""

from __future__ import annotations

from typing import Any, cast

import astx

from llvmlite import ir

from irx.analysis.types import is_float_type, is_unsigned_type
from irx.builder.core import VisitorCore
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
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
            self._llvm.ir_builder.call(append, [builder_handle, value])
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
        self._llvm.ir_builder.call(append, [builder_handle, value])

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
        self._llvm.ir_builder.call(
            builder_new,
            [
                ir.Constant(self._llvm.INT32_TYPE, type_id),
                builder_slot,
            ],
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
        self._llvm.ir_builder.call(
            finish_builder,
            [builder_handle, array_slot],
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
        index = self._column_index(node)
        if index is not None:
            column_by_index = self.require_runtime_symbol(
                "dataframe",
                "irx_arrow_table_column_by_index",
            )
            self._llvm.ir_builder.call(
                column_by_index,
                [
                    table_handle,
                    ir.Constant(self._llvm.INT32_TYPE, index),
                    column_slot,
                ],
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
            self._llvm.ir_builder.call(
                column_by_name,
                [table_handle, name_pointer, column_slot],
            )

        column_handle = self._llvm.ir_builder.load(
            column_slot,
            "dataframe_column",
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
        if node.type_.columns is None:
            raise Exception("dataframe literal lowering requires a schema")

        literal_by_name = {column.name: column for column in node.columns}
        release_array = self.require_runtime_symbol(
            "array",
            "irx_arrow_array_release",
        )
        table_new = self.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_new_from_arrays",
        )

        array_handles: list[ir.Value] = []
        name_pointers: list[ir.Value] = []
        for schema_column in node.type_.columns:
            literal_column = literal_by_name.get(schema_column.name)
            if literal_column is None:
                raise Exception("dataframe literal is missing a column")
            array_handles.append(
                self._build_arrow_array_from_column(
                    schema_column.name,
                    schema_column.type_,
                    literal_column.values,
                )
            )
            name_pointers.append(
                cast(Any, self)._constant_c_string_pointer(
                    schema_column.name,
                    name_hint=f"dataframe_column_{schema_column.name}",
                )
            )

        column_count = len(array_handles)
        names_array_type = ir.ArrayType(
            self._llvm.ASCII_STRING_TYPE,
            column_count,
        )
        arrays_array_type = ir.ArrayType(
            self._llvm.ARRAY_HANDLE_TYPE,
            column_count,
        )
        names_array = self._llvm.ir_builder.alloca(
            names_array_type,
            name="dataframe_names",
        )
        arrays_array = self._llvm.ir_builder.alloca(
            arrays_array_type,
            name="dataframe_arrays",
        )

        for index, (name_pointer, array_handle) in enumerate(
            zip(name_pointers, array_handles, strict=True)
        ):
            indices = [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(self._llvm.INT32_TYPE, index),
            ]
            name_slot = self._llvm.ir_builder.gep(names_array, indices)
            array_slot = self._llvm.ir_builder.gep(arrays_array, indices)
            self._llvm.ir_builder.store(name_pointer, name_slot)
            self._llvm.ir_builder.store(array_handle, array_slot)

        names_ptr = self._llvm.ir_builder.gep(
            names_array,
            [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(self._llvm.INT32_TYPE, 0),
            ],
        )
        arrays_ptr = self._llvm.ir_builder.gep(
            arrays_array,
            [
                ir.Constant(self._llvm.INT32_TYPE, 0),
                ir.Constant(self._llvm.INT32_TYPE, 0),
            ],
        )
        table_slot = self._llvm.ir_builder.alloca(
            self._llvm.TABLE_HANDLE_TYPE,
            name="dataframe_table_slot",
        )
        self._llvm.ir_builder.call(
            table_new,
            [
                ir.Constant(self._llvm.INT64_TYPE, column_count),
                names_ptr,
                arrays_ptr,
                table_slot,
            ],
        )
        table_handle = self._llvm.ir_builder.load(
            table_slot,
            "dataframe_table",
        )

        for array_handle in array_handles:
            self._llvm.ir_builder.call(release_array, [array_handle])

        self.result_stack.append(table_handle)

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
        self.result_stack.append(
            self._llvm.ir_builder.call(nrows, [table_handle], "nrows")
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
        self.result_stack.append(
            self._llvm.ir_builder.call(ncols, [table_handle], "ncols")
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
        self.result_stack.append(
            self._llvm.ir_builder.call(retain, [table_handle])
        )

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
        self._llvm.ir_builder.call(release, [table_handle])
        self.result_stack.append(ir.Constant(self._llvm.INT32_TYPE, 0))

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
        self.result_stack.append(
            self._llvm.ir_builder.call(retain, [column_handle])
        )

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
        self._llvm.ir_builder.call(release, [column_handle])
        self.result_stack.append(ir.Constant(self._llvm.INT32_TYPE, 0))


__all__ = ["DataFrameVisitorMixin"]
