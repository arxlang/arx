# mypy: disable-error-code=no-redef

"""
title: DataFrame lowering implementation for llvmliteir.
"""

from __future__ import annotations

from typing import cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import is_float_type, is_unsigned_type
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import DataFrameServices
from irx.builder.runtime import safe_pop
from irx.builder.runtime.record_batch_api import ARROW_API_SIGNATURES
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builder.state import CleanupAction
from irx.builder.types import is_int_type
from irx.builtins.collections.dataframe import (
    DATAFRAME_COLUMN_INDEX_EXTRA,
    dataframe_type_id,
)
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class DataFrameLowering:
    """
    title: DataFrame lowering implementation.
    attributes:
      services:
        type: DataFrameServices
    """

    services: DataFrameServices

    def __init__(self, services: DataFrameServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: DataFrameServices
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
            f"no dataframe handler for {type(node).__name__}", node=node
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
                "llvm.dataframe.DataFrameLiteral",
                "irx.dataframe",
                "lowering",
                astx.DataFrameLiteral,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.DataFrameColumnAccess",
                "irx.dataframe",
                "lowering",
                astx.DataFrameColumnAccess,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.DataFrameStringColumnAccess",
                "irx.dataframe",
                "lowering",
                astx.DataFrameStringColumnAccess,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.DataFrameRowCount",
                "irx.dataframe",
                "lowering",
                astx.DataFrameRowCount,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.DataFrameColumnCount",
                "irx.dataframe",
                "lowering",
                astx.DataFrameColumnCount,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.DataFrameRetain",
                "irx.dataframe",
                "lowering",
                astx.DataFrameRetain,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.DataFrameRelease",
                "irx.dataframe",
                "lowering",
                astx.DataFrameRelease,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.SeriesRetain",
                "irx.dataframe",
                "lowering",
                astx.SeriesRetain,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
            contribute_node(
                "llvm.dataframe.SeriesRelease",
                "irx.dataframe",
                "lowering",
                astx.SeriesRelease,
                self.visit,
                source="irx.builder.lowering.dataframe.DataFrameLowering.visit",
            ),
        )

    @private
    def checked_native_call(
        self, node: astx.AST, function: ir.Function, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: Call a checked facade and load its result only after success.
        parameters:
          node:
            type: astx.AST
          function:
            type: ir.Function
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
          description: Value result, or the successful status for void APIs.
        """
        contract = ARROW_API_SIGNATURES.get(function.name)
        if contract is None:
            raise_lowering_internal_error(
                "missing checked native signature", node=node
            )
        output = None
        operands = list(args)
        if contract[0] != "v":
            output_type = function.function_type.args[-2].pointee
            output = self.services.create_entry_block_alloca(
                "native.result", output_type
            )
            operands.append(output)
        error = self.services.create_entry_block_alloca(
            "native.error", ir.ArrayType(ir.IntType(8), 1024)
        )
        zero = ir.Constant(ir.IntType(32), 0)
        message = self.services.llvm.ir_builder.gep(error, [zero, zero])
        operands.append(message)
        status = self.services.llvm.ir_builder.call(function, operands)
        self.check_arrow_status(node, status, function.name, message)
        return (
            status
            if output is None
            else self.services.llvm.ir_builder.load(output)
        )

    @private
    def check_arrow_status(
        self,
        node: astx.AST,
        status: ir.Value,
        operation: str,
        message: ir.Value | None = None,
    ) -> None:
        """
        title: Translate typed native failures without parsing diagnostic text.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          operation:
            type: str
          message:
            type: ir.Value | None
        """
        function = self.services.llvm.ir_builder.function
        success = function.append_basic_block(operation + ".success")
        failure = function.append_basic_block(operation + ".failure")
        self.services.llvm.ir_builder.cbranch(
            self.services.llvm.ir_builder.icmp_signed(
                "==", status, ir.Constant(status.type, 0)
            ),
            success,
            failure,
        )
        self.services.llvm.ir_builder.position_at_end(failure)
        if message is None:
            message = self.services.llvm.ir_builder.call(
                self.services.require_runtime_symbol(
                    "dataframe", "irx_arrow_last_error"
                ),
                [],
            )
        fallback = function.append_basic_block("arrow.runtime_error")
        switch = self.services.llvm.ir_builder.switch(status, fallback)
        for code, role in (
            (-2, "ValueError"),
            (-3, "IndexError"),
            (-4, "TypeError"),
            (-5, "OSError"),
            (-6, "ValueError"),
            (-8, "OverflowError"),
        ):
            block = function.append_basic_block("arrow." + role)
            switch.add_case(ir.Constant(status.type, code), block)
            self.services.llvm.ir_builder.position_at_end(block)
            self.services.raise_runtime_exception(
                node, role, message, code="ARX-RUNTIME-ARROW-001"
            )
        allocation = function.append_basic_block("arrow.allocation_failure")
        switch.add_case(ir.Constant(status.type, -7), allocation)
        self.services.llvm.ir_builder.position_at_end(allocation)
        self.services.fatal_status(node, status)
        self.services.llvm.ir_builder.unreachable()
        self.services.llvm.ir_builder.position_at_end(fallback)
        self.services.raise_runtime_exception(
            node, "RuntimeError", message, code="ARX-RUNTIME-ARROW-001"
        )
        self.services.llvm.ir_builder.position_at_end(success)

    @private
    def track_native_handle(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Own a construction handle across later fallible native calls.
        parameters:
          node:
            type: astx.AST
          feature:
            type: str
          destroy:
            type: str
          value:
            type: ir.Value
        returns:
          type: CleanupAction
        """

        def release() -> None:
            """
            title: Destroy the handle through its declared native boundary.
            """
            function = self.services.require_runtime_symbol(feature, destroy)
            if destroy in ARROW_API_SIGNATURES:
                self.checked_native_call(node, function, [value])
            else:
                self.services.llvm.ir_builder.call(function, [value])

        action = CleanupAction(release)
        self.services.exit_state.cleanup_stack.append(action)
        return action

    @private
    def release_native_handle(self, action: CleanupAction) -> None:
        """
        title: Consume one tracked native handle on normal completion.
        parameters:
          action:
            type: CleanupAction
        """
        self.services.exit_state.cleanup_stack.remove(action)
        action.emitter()

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
        self.services.visit_child(value_node)
        value = safe_pop(self.services.function_state.result_stack)
        if value is None:
            raise_lowering_internal_error(
                "dataframe column value lowering failed", node=value_node
            )
        value = self.services.numeric.cast_scalar(
            value,
            source_type=resolved_ast_type(value_node),
            target_type=target_type,
        )

        if is_float_type(target_type):
            append = self.services.require_runtime_symbol(
                "array",
                "irx_arrow_array_builder_append_double",
            )
            if value.type != self.services.llvm.DOUBLE_TYPE:
                value = self.services.llvm.ir_builder.fpext(
                    value,
                    self.services.llvm.DOUBLE_TYPE,
                    "dataframe_fpext",
                )
            status = self.services.llvm.ir_builder.call(
                append,
                [builder_handle, value],
            )
            self.check_arrow_status(
                value_node, status, "dataframe_append_double"
            )
            return

        append = self.services.require_runtime_symbol(
            "array",
            "irx_arrow_array_builder_append_int",
        )
        if not is_int_type(value.type):
            raise_lowering_internal_error(
                "dataframe column value must lower to a scalar",
                node=value_node,
            )
        if value.type.width < self.services.llvm.INT64_TYPE.width:
            if is_unsigned_type(target_type) or isinstance(
                target_type,
                astx.Boolean,
            ):
                value = self.services.llvm.ir_builder.zext(
                    value,
                    self.services.llvm.INT64_TYPE,
                    "dataframe_zext",
                )
            else:
                value = self.services.llvm.ir_builder.sext(
                    value,
                    self.services.llvm.INT64_TYPE,
                    "dataframe_sext",
                )
        elif value.type.width > self.services.llvm.INT64_TYPE.width:
            value = self.services.llvm.ir_builder.trunc(
                value,
                self.services.llvm.INT64_TYPE,
                "dataframe_trunc",
            )
        status = self.services.llvm.ir_builder.call(
            append, [builder_handle, value]
        )
        self.check_arrow_status(value_node, status, "dataframe_append_int")

    def _build_arrow_array_from_column(
        self,
        node: astx.AST,
        column_name: str,
        column_type: astx.DataType,
        values: tuple[astx.AST, ...],
    ) -> ir.Value:
        """
        title: Build one Arrow array handle from column values.
        parameters:
          node:
            type: astx.AST
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
            raise_lowering_error(
                "unsupported dataframe column type",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )

        builder_new = self.services.require_runtime_symbol(
            "array",
            "irx_arrow_array_builder_new",
        )
        finish_builder = self.services.require_runtime_symbol(
            "array",
            "irx_arrow_array_builder_finish",
        )

        builder_slot = self.services.llvm.ir_builder.alloca(
            self.services.llvm.ARRAY_BUILDER_HANDLE_TYPE,
            name=f"{column_name}_array_builder_slot",
        )
        status = self.services.llvm.ir_builder.call(
            builder_new,
            [
                ir.Constant(self.services.llvm.INT32_TYPE, type_id),
                builder_slot,
            ],
        )
        self.check_arrow_status(node, status, "dataframe_array_builder_new")
        builder_handle = self.services.llvm.ir_builder.load(
            builder_slot,
            f"{column_name}_array_builder",
        )

        cleanup = self.track_native_handle(
            node, "array", "irx_arrow_array_builder_release", builder_handle
        )
        for value in values:
            self._append_dataframe_value(builder_handle, value, column_type)

        array_slot = self.services.llvm.ir_builder.alloca(
            self.services.llvm.ARRAY_HANDLE_TYPE,
            name=f"{column_name}_array_slot",
        )
        status = self.services.llvm.ir_builder.call(
            finish_builder,
            [builder_handle, array_slot],
        )
        self.check_arrow_status(node, status, "dataframe_array_builder_finish")
        self.services.exit_state.cleanup_stack.remove(cleanup)
        return self.services.llvm.ir_builder.load(
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
        self.services.visit_child(node.base)
        table_handle = safe_pop(self.services.function_state.result_stack)
        if table_handle is None:
            raise_lowering_internal_error(
                "dataframe column access requires a table", node=node
            )

        column_slot = self.services.llvm.ir_builder.alloca(
            self.services.llvm.CHUNKED_ARRAY_HANDLE_TYPE,
            name="dataframe_column_slot",
        )
        index = self._column_index(node)
        if index is not None:
            column_by_index = self.services.require_runtime_symbol(
                "dataframe",
                "irx_arrow_table_column_by_index",
            )
            status = self.services.llvm.ir_builder.call(
                column_by_index,
                [
                    table_handle,
                    ir.Constant(self.services.llvm.INT32_TYPE, index),
                    column_slot,
                ],
            )
            self.check_arrow_status(node, status, "dataframe_column_by_index")
        else:
            column_by_name = self.services.require_runtime_symbol(
                "dataframe",
                "irx_arrow_table_column_by_name",
            )
            name_pointer = self.services.strings.constant(
                node.column_name,
                name_hint=f"dataframe_column_{node.column_name}",
            )
            status = self.services.llvm.ir_builder.call(
                column_by_name,
                [table_handle, name_pointer, column_slot],
            )
            self.check_arrow_status(node, status, "dataframe_column_by_name")

        column_handle = self.services.llvm.ir_builder.load(
            column_slot,
            "dataframe_column",
        )
        self.services.arrow_temporary(node, column_handle)
        self.services.function_state.result_stack.append(column_handle)

    def lower_extended_dataframe_literal(
        self, node: astx.DataFrameLiteral
    ) -> None:
        """
        title: >-
          Build nullable/string/unsigned literals through the RecordBatch ABI.
        parameters:
          node:
            type: astx.DataFrameLiteral
        """
        info = cast(SemanticInfo | None, getattr(node, "semantic", None))
        ids = cast(
            tuple[int, ...],
            require_semantic_metadata(
                None
                if info is None
                else info.extras.get("dataframe_storage_ids"),
                node=node,
                metadata="dataframe_storage_ids",
                context="DataFrame literal",
            ),
        )
        assert node.type_.columns is not None
        builder = self.services.llvm.ir_builder
        schema = self.checked_native_call(
            node,
            self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_schema_new"
            ),
            [],
        )
        schema_cleanup = self.track_native_handle(
            node, "record_batch", "irx_rb_api_schema_destroy", schema
        )
        add = self.services.require_runtime_symbol(
            "record_batch", "irx_rb_api_schema_add"
        )
        for column, type_id in zip(node.type_.columns, ids):
            name = self.services.strings.constant(
                column.name, name_hint="dataframe_field"
            )
            self.checked_native_call(
                node,
                add,
                [
                    schema,
                    name,
                    ir.Constant(ir.IntType(32), type_id),
                    ir.Constant(ir.IntType(32), int(column.nullable)),
                ],
            )
        owner = self.checked_native_call(
            node,
            self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_builder_new"
            ),
            [schema],
        )
        owner_cleanup = self.track_native_handle(
            node, "record_batch", "irx_rb_api_builder_destroy", owner
        )
        values = {column.name: column.values for column in node.columns}
        append_names = {
            0: "i8",
            1: "i16",
            2: "i32",
            3: "i64",
            4: "u8",
            5: "u16",
            6: "u32",
            7: "u64",
            8: "f32",
            9: "f64",
            10: "bool",
            11: "utf8",
            13: "date",
            17: "timestamp",
            21: "time",
        }
        for index, (column, type_id) in enumerate(
            zip(node.type_.columns, ids)
        ):
            column_index = ir.Constant(ir.IntType(32), index)
            for value_node in values[column.name]:
                if isinstance(value_node, astx.LiteralNone):
                    self.checked_native_call(
                        node,
                        self.services.require_runtime_symbol(
                            "record_batch", "irx_rb_api_append_null"
                        ),
                        [owner, column_index],
                    )
                    continue
                if isinstance(
                    column.type_,
                    (astx.Date, astx.Time, astx.Timestamp, astx.DateTime),
                ):
                    literal_info = cast(
                        SemanticInfo | None,
                        getattr(value_node, "semantic", None),
                    )
                    physical = require_semantic_metadata(
                        None
                        if literal_info is None
                        else literal_info.extras.get(
                            "dataframe_temporal_value"
                        ),
                        node=value_node,
                        metadata="dataframe_temporal_value",
                        context="temporal DataFrame literal",
                    )
                    value = ir.Constant(ir.IntType(64), physical)
                else:
                    self.services.visit_child(value_node)
                    value = safe_pop(self.services.function_state.result_stack)
                    if value is None:
                        raise_lowering_internal_error(
                            "DataFrame literal value did not lower",
                            node=value_node,
                        )
                    value = self.services.numeric.cast_scalar(
                        value,
                        source_type=resolved_ast_type(value_node),
                        target_type=column.type_,
                    )
                if isinstance(column.type_, astx.Boolean):
                    value = builder.zext(value, ir.IntType(32))
                append = self.services.require_runtime_symbol(
                    "record_batch",
                    "irx_rb_api_append_" + append_names[type_id],
                )
                self.checked_native_call(
                    node, append, [owner, column_index, value]
                )
        batch = self.checked_native_call(
            node,
            self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_batch_new"
            ),
            [],
        )
        batch_cleanup = self.track_native_handle(
            node, "record_batch", "irx_rb_api_batch_destroy", batch
        )
        self.checked_native_call(
            node,
            self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_builder_finish"
            ),
            [owner, batch],
        )
        table = self.checked_native_call(
            node,
            self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_batch_to_table"
            ),
            [batch, schema],
        )
        self.services.arrow_temporary(node, table)
        for cleanup in (batch_cleanup, owner_cleanup, schema_cleanup):
            self.release_native_handle(cleanup)
        self.services.function_state.result_stack.append(table)

    @dispatch
    def visit(self, node: astx.DataFrameLiteral) -> None:
        """
        title: Visit DataFrameLiteral nodes.
        parameters:
          node:
            type: astx.DataFrameLiteral
        """
        info = getattr(node, "semantic", None)
        payload = (
            None if info is None else info.extras.get("dataframe_literal_ipc")
        )
        if isinstance(payload, bytes):
            data = ir.Constant(
                ir.ArrayType(ir.IntType(8), len(payload)), bytearray(payload)
            )
            storage = ir.GlobalVariable(
                self.services.llvm.module,
                data.type,
                self.services.llvm.module.get_unique_name("dataframe_literal"),
            )
            storage.linkage = "internal"
            storage.global_constant = True
            storage.initializer = data
            zero = ir.Constant(ir.IntType(32), 0)
            pointer = self.services.llvm.ir_builder.gep(
                storage, [zero, zero], inbounds=True
            )
            output = self.services.create_entry_block_alloca(
                "literal_table", self.services.llvm.TABLE_HANDLE_TYPE
            )
            status = self.services.llvm.ir_builder.call(
                self.services.require_runtime_symbol(
                    "dataframe", "irx_arrow_table_from_ipc"
                ),
                [pointer, ir.Constant(ir.IntType(64), len(payload)), output],
            )
            self.check_arrow_status(node, status, "dataframe_literal")
            table = self.services.llvm.ir_builder.load(output)
            self.services.arrow_temporary(node, table)
            self.services.function_state.result_stack.append(table)
            return
        if node.type_.columns is None:
            raise_lowering_internal_error(
                "dataframe literal lowering requires a schema", node=node
            )

        if any(
            c.nullable
            or isinstance(
                c.type_,
                (
                    astx.String,
                    astx.Date,
                    astx.Time,
                    astx.Timestamp,
                    astx.DateTime,
                ),
            )
            or is_unsigned_type(c.type_)
            for c in node.type_.columns
        ):
            self.lower_extended_dataframe_literal(node)
            return

        literal_by_name = {column.name: column for column in node.columns}
        table_new = self.services.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_new_from_arrays",
        )

        array_handles: list[ir.Value] = []
        array_cleanups: list[CleanupAction] = []
        name_pointers: list[ir.Value] = []
        for schema_column in node.type_.columns:
            literal_column = literal_by_name.get(schema_column.name)
            if literal_column is None:
                raise_lowering_internal_error(
                    "dataframe literal is missing a column", node=node
                )
            array_handles.append(
                self._build_arrow_array_from_column(
                    node,
                    schema_column.name,
                    schema_column.type_,
                    literal_column.values,
                )
            )
            array_cleanups.append(
                self.track_native_handle(
                    node, "array", "irx_arrow_array_release", array_handles[-1]
                )
            )
            name_pointers.append(
                self.services.strings.constant(
                    schema_column.name,
                    name_hint=f"dataframe_column_{schema_column.name}",
                )
            )

        column_count = len(array_handles)
        names_array_type = ir.ArrayType(
            self.services.llvm.ASCII_STRING_TYPE,
            column_count,
        )
        arrays_array_type = ir.ArrayType(
            self.services.llvm.ARRAY_HANDLE_TYPE,
            column_count,
        )
        names_array = self.services.llvm.ir_builder.alloca(
            names_array_type,
            name="dataframe_names",
        )
        arrays_array = self.services.llvm.ir_builder.alloca(
            arrays_array_type,
            name="dataframe_arrays",
        )

        for index, (name_pointer, array_handle) in enumerate(
            zip(name_pointers, array_handles, strict=True)
        ):
            indices = [
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
                ir.Constant(self.services.llvm.INT32_TYPE, index),
            ]
            name_slot = self.services.llvm.ir_builder.gep(names_array, indices)
            array_slot = self.services.llvm.ir_builder.gep(
                arrays_array, indices
            )
            self.services.llvm.ir_builder.store(name_pointer, name_slot)
            self.services.llvm.ir_builder.store(array_handle, array_slot)

        names_ptr = self.services.llvm.ir_builder.gep(
            names_array,
            [
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
            ],
        )
        arrays_ptr = self.services.llvm.ir_builder.gep(
            arrays_array,
            [
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
                ir.Constant(self.services.llvm.INT32_TYPE, 0),
            ],
        )
        table_slot = self.services.llvm.ir_builder.alloca(
            self.services.llvm.TABLE_HANDLE_TYPE,
            name="dataframe_table_slot",
        )
        status = self.services.llvm.ir_builder.call(
            table_new,
            [
                ir.Constant(self.services.llvm.INT64_TYPE, column_count),
                names_ptr,
                arrays_ptr,
                table_slot,
            ],
        )
        self.check_arrow_status(node, status, "dataframe_table_new")
        table_handle = self.services.llvm.ir_builder.load(
            table_slot,
            "dataframe_table",
        )

        self.services.arrow_temporary(node, table_handle)
        for cleanup in reversed(array_cleanups):
            self.release_native_handle(cleanup)
        self.services.function_state.result_stack.append(table_handle)

    @dispatch
    def visit(self, node: astx.DataFrameColumnAccess) -> None:
        """
        title: Visit DataFrameColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameColumnAccess
        """
        self._lower_dataframe_column_access(node)

    @dispatch
    def visit(self, node: astx.DataFrameStringColumnAccess) -> None:
        """
        title: Visit DataFrameStringColumnAccess nodes.
        parameters:
          node:
            type: astx.DataFrameStringColumnAccess
        """
        self._lower_dataframe_column_access(node)

    @dispatch
    def visit(self, node: astx.DataFrameRowCount) -> None:
        """
        title: Visit DataFrameRowCount nodes.
        parameters:
          node:
            type: astx.DataFrameRowCount
        """
        self.services.visit_child(node.base)
        table_handle = safe_pop(self.services.function_state.result_stack)
        if table_handle is None:
            raise_lowering_internal_error(
                "dataframe nrows requires a table", node=node
            )
        nrows = self.services.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_num_rows",
        )
        self.services.function_state.result_stack.append(
            self.services.llvm.ir_builder.call(nrows, [table_handle], "nrows")
        )

    @dispatch
    def visit(self, node: astx.DataFrameColumnCount) -> None:
        """
        title: Visit DataFrameColumnCount nodes.
        parameters:
          node:
            type: astx.DataFrameColumnCount
        """
        self.services.visit_child(node.base)
        table_handle = safe_pop(self.services.function_state.result_stack)
        if table_handle is None:
            raise_lowering_internal_error(
                "dataframe ncols requires a table", node=node
            )
        ncols = self.services.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_num_columns",
        )
        self.services.function_state.result_stack.append(
            self.services.llvm.ir_builder.call(ncols, [table_handle], "ncols")
        )

    @dispatch
    def visit(self, node: astx.DataFrameRetain) -> None:
        """
        title: Visit DataFrameRetain nodes.
        parameters:
          node:
            type: astx.DataFrameRetain
        """
        self.services.visit_child(node.base)
        table_handle = safe_pop(self.services.function_state.result_stack)
        retain = self.services.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_retain",
        )
        status = self.services.llvm.ir_builder.call(retain, [table_handle])
        self.check_arrow_status(node, status, "dataframe_table_retain")
        self.services.arrow_explicit_lifetime(
            node.base, table_handle, retain=True
        )
        self.services.function_state.result_stack.append(status)

    @dispatch
    def visit(self, node: astx.DataFrameRelease) -> None:
        """
        title: Visit DataFrameRelease nodes.
        parameters:
          node:
            type: astx.DataFrameRelease
        """
        self.services.visit_child(node.base)
        table_handle = safe_pop(self.services.function_state.result_stack)
        release = self.services.require_runtime_symbol(
            "dataframe",
            "irx_arrow_table_release",
        )
        self.services.llvm.ir_builder.call(release, [table_handle])
        self.services.arrow_explicit_lifetime(
            node.base, table_handle, retain=False
        )
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT32_TYPE, 0)
        )

    @dispatch
    def visit(self, node: astx.SeriesRetain) -> None:
        """
        title: Visit SeriesRetain nodes.
        parameters:
          node:
            type: astx.SeriesRetain
        """
        self.services.visit_child(node.base)
        column_handle = safe_pop(self.services.function_state.result_stack)
        retain = self.services.require_runtime_symbol(
            "dataframe",
            "irx_arrow_chunked_array_retain",
        )
        status = self.services.llvm.ir_builder.call(retain, [column_handle])
        self.check_arrow_status(node, status, "dataframe_series_retain")
        self.services.arrow_explicit_lifetime(
            node.base, column_handle, retain=True
        )
        self.services.function_state.result_stack.append(status)

    @dispatch
    def visit(self, node: astx.SeriesRelease) -> None:
        """
        title: Visit SeriesRelease nodes.
        parameters:
          node:
            type: astx.SeriesRelease
        """
        self.services.visit_child(node.base)
        column_handle = safe_pop(self.services.function_state.result_stack)
        release = self.services.require_runtime_symbol(
            "dataframe",
            "irx_arrow_chunked_array_release",
        )
        self.services.llvm.ir_builder.call(release, [column_handle])
        self.services.arrow_explicit_lifetime(
            node.base, column_handle, retain=False
        )
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT32_TYPE, 0)
        )
