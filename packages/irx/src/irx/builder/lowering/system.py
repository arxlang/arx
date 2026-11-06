# mypy: disable-error-code=no-redef

"""
title: System/runtime lowering implementations for llvmliteir.
"""

from typing import cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.arrow_conversion import (
    ARROW_CONVERSION,
    ArrowConversion,
    ArrowTableCast,
)
from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import (
    display_type_name,
    is_boolean_type,
    is_numeric_type,
    is_unsigned_type,
)
from irx.builder.diagnostics import (
    raise_lowering_error,
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import SystemServices
from irx.builder.runtime import safe_pop
from irx.builder.services.representations import (
    resolved_type as resolved_ast_type,
)
from irx.builder.types import is_int_type
from irx.diagnostics import DiagnosticCodes
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class SystemLowering:
    """
    title: Lower system operations to LLVM.
    attributes:
      services:
        type: SystemServices
    """

    services: SystemServices

    def __init__(self, services: SystemServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: SystemServices
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
            f"no system handler for {type(node).__name__}", node=node
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
                "llvm.system.Cast",
                "irx.system",
                "lowering",
                astx.Cast,
                self.visit,
                source="irx.builder.lowering.system.SystemLowering.visit",
            ),
            contribute_node(
                "llvm.system.IsInstanceExpr",
                "irx.system",
                "lowering",
                astx.IsInstanceExpr,
                self.visit,
                source="irx.builder.lowering.system.SystemLowering.visit",
            ),
            contribute_node(
                "llvm.system.PrintExpr",
                "irx.system",
                "lowering",
                astx.PrintExpr,
                self.visit,
                source="irx.builder.lowering.system.SystemLowering.visit",
            ),
            contribute_node(
                "llvm.system.TypeOfExpr",
                "irx.system",
                "lowering",
                astx.TypeOfExpr,
                self.visit,
                source="irx.builder.lowering.system.SystemLowering.visit",
            ),
        )

    @dispatch
    def visit(self, node: astx.Cast) -> None:
        """
        title: Visit Cast nodes.
        parameters:
          node:
            type: astx.Cast
        """
        if isinstance(node.target_type, astx.NullableType) and isinstance(
            node.value, astx.LiteralNone
        ):
            storage = require_semantic_metadata(
                self.services.types.llvm_type(node.target_type),
                node=node,
                metadata="nullable type",
                context="null construction",
            )
            self.services.function_state.result_stack.append(
                ir.Constant(storage, None)
            )
            return
        self.services.visit_child(node.value)
        value = safe_pop(self.services.function_state.result_stack)
        if value is None:
            raise_lowering_internal_error("Invalid value in Cast", node=node)

        semantic = require_semantic_metadata(
            getattr(node, "semantic", None),
            node=node,
            metadata="semantic",
            context="cast",
        )
        plan = semantic.extras.get(ARROW_CONVERSION)
        if isinstance(plan, ArrowTableCast):
            self.lower_table_cast(node, value, plan)
            return
        if isinstance(plan, ArrowConversion):
            self.lower_arrow_cast(node, value, plan)
            return
        source_type = resolved_ast_type(node.value)
        target_type = node.target_type
        if (
            isinstance(source_type, astx.ClassType)
            and isinstance(target_type, astx.DataFrameType)
        ) or (
            isinstance(source_type, astx.DataFrameType)
            and isinstance(target_type, (astx.ClassType, astx.DataFrameType))
        ):
            raise_lowering_internal_error(
                "Arrow cast is missing its conversion plan", node=node
            )

        target_llvm_type = self.services.types.llvm_type(target_type)
        if target_llvm_type in (
            self.services.llvm.ASCII_STRING_TYPE,
            self.services.llvm.UTF8_STRING_TYPE,
        ):
            if (
                isinstance(value.type, ir.PointerType)
                and value.type.pointee == self.services.llvm.INT8_TYPE
            ):
                self.services.function_state.result_stack.append(value)
                return
            if is_int_type(value.type):
                arg, fmt_str = self.services.strings.integer_format(
                    value,
                    unsigned=is_unsigned_type(source_type)
                    or is_boolean_type(source_type),
                )
                fmt_gv = self.services.strings.format_global(fmt_str)
                ptr = self.services.strings.format_heap(node, fmt_gv, [arg])
                self.services.cleanup.register_owned_string_temporary(
                    node, ptr
                )
                self.services.function_state.result_stack.append(ptr)
                return

            if isinstance(
                value.type, (ir.FloatType, ir.DoubleType, ir.HalfType)
            ):
                if isinstance(value.type, (ir.FloatType, ir.HalfType)):
                    value_prom = self.services.llvm.ir_builder.fpext(
                        value, self.services.llvm.DOUBLE_TYPE, "to_double"
                    )
                else:
                    value_prom = value
                fmt_gv = self.services.strings.format_global("%.6f")
                ptr = self.services.strings.format_heap(
                    node, fmt_gv, [value_prom]
                )
                self.services.cleanup.register_owned_string_temporary(
                    node, ptr
                )
                self.services.function_state.result_stack.append(ptr)
                return
            raise_lowering_error(
                f"Unsupported cast from {value.type} to {target_llvm_type}",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )
        if semantic.numeric_conversion is not None:
            result = self.services.numeric.lower_numeric_cast(
                node, value, semantic.numeric_conversion, semantic.numeric_mode
            )
            self.services.function_state.result_stack.append(result)
            return
        scalar_source = (
            source_type.value_type
            if isinstance(source_type, astx.NullableType)
            else source_type
        )
        scalar_target = (
            target_type.value_type
            if isinstance(target_type, astx.NullableType)
            else target_type
        )
        if is_numeric_type(scalar_source) and is_numeric_type(scalar_target):
            raise_lowering_internal_error(
                "numeric cast is missing its conversion plan", node=node
            )
        result = self.services.numeric.cast_scalar(
            value,
            source_type=source_type,
            target_type=target_type,
        )
        self.services.function_state.result_stack.append(result)

    @dispatch
    def visit(self, node: astx.IsInstanceExpr) -> None:
        """
        title: Visit IsInstanceExpr nodes.
        parameters:
          node:
            type: astx.IsInstanceExpr
        """
        self.services.visit_child(node.value)
        _ = safe_pop(self.services.function_state.result_stack)
        static_result = cast(bool, getattr(node, "static_result", False))
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.BOOLEAN_TYPE, int(static_result))
        )

    @dispatch
    def visit(self, node: astx.PrintExpr) -> None:
        """
        title: Visit PrintExpr nodes.
        parameters:
          node:
            type: astx.PrintExpr
        """
        self.services.visit_child(node.message)
        message_value = safe_pop(self.services.function_state.result_stack)
        if message_value is None:
            raise_lowering_internal_error(
                "Invalid message in PrintExpr", node=node
            )

        message_source_type = resolved_ast_type(node.message)
        message_type = message_value.type
        ptr: ir.Value
        release_formatted_pointer = False
        if (
            isinstance(message_type, ir.PointerType)
            and message_type.pointee == self.services.llvm.INT8_TYPE
        ):
            ptr = message_value
        elif is_int_type(message_type):
            int_arg, int_fmt = self.services.strings.integer_format(
                message_value,
                unsigned=is_unsigned_type(message_source_type)
                or is_boolean_type(message_source_type),
            )
            int_fmt_gv = self.services.strings.format_global(int_fmt)
            ptr = self.services.strings.format_heap(
                node, int_fmt_gv, [int_arg]
            )
            release_formatted_pointer = True
        elif isinstance(
            message_type, (ir.HalfType, ir.FloatType, ir.DoubleType)
        ):
            if isinstance(message_type, (ir.HalfType, ir.FloatType)):
                float_arg = self.services.llvm.ir_builder.fpext(
                    message_value,
                    self.services.llvm.DOUBLE_TYPE,
                    "print_to_double",
                )
            else:
                float_arg = message_value
            float_fmt_gv = self.services.strings.format_global("%.6f")
            ptr = self.services.strings.format_heap(
                node, float_fmt_gv, [float_arg]
            )
            release_formatted_pointer = True
        else:
            raise_lowering_error(
                f"Unsupported message type in PrintExpr: {message_type}",
                code=DiagnosticCodes.LOWERING_TYPE_MISMATCH,
                node=node,
            )

        puts_fn = self.services.require_runtime_symbol("libc", "puts")
        self.services.llvm.ir_builder.call(puts_fn, [ptr])
        if release_formatted_pointer:
            free_fn = self.services.require_runtime_symbol("libc", "free")
            self.services.llvm.ir_builder.call(free_fn, [ptr])
        self.services.function_state.result_stack.append(
            ir.Constant(self.services.llvm.INT32_TYPE, 0)
        )

    @dispatch
    def visit(self, node: astx.TypeOfExpr) -> None:
        """
        title: Visit TypeOfExpr nodes.
        parameters:
          node:
            type: astx.TypeOfExpr
        """
        self.services.visit_child(node.value)
        _ = safe_pop(self.services.function_state.result_stack)
        type_name = display_type_name(resolved_ast_type(node.value))
        pointer = self.services.strings.constant(
            type_name,
            name_hint="type_name",
        )
        self.services.function_state.result_stack.append(pointer)

    def lower_table_cast(
        self, node: astx.Cast, value: ir.Value, plan: ArrowTableCast
    ) -> None:
        """
        title: Check every table chunk while preserving independent ownership.
        parameters:
          node:
            type: astx.Cast
          value:
            type: ir.Value
          plan:
            type: ArrowTableCast
        """
        builder = self.services.llvm.ir_builder
        if plan.schema_ipc is None:
            self.services.class_operation(node.value, "retain", value)
            result = value
        else:
            data = plan.schema_ipc
            payload = ir.Constant(
                ir.ArrayType(ir.IntType(8), len(data)), bytearray(data)
            )
            global_value = ir.GlobalVariable(
                self.services.llvm.module,
                payload.type,
                self.services.llvm.module.get_unique_name("table_cast_schema"),
            )
            global_value.linkage = "internal"
            global_value.global_constant = True
            global_value.initializer = payload
            zero = ir.Constant(ir.IntType(32), 0)
            pointer = builder.gep(global_value, [zero, zero], inbounds=True)
            create = self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_schema_ipc"
            )
            schema = self.services.checked_native_call(
                node, create, [pointer, ir.Constant(ir.IntType(64), len(data))]
            )
            cleanup = self.services.track_native_handle(
                node, "record_batch", "irx_rb_api_schema_destroy", schema
            )
            convert = self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_table_cast"
            )
            result = self.services.checked_native_call(
                node, convert, [value, schema]
            )
            self.services.arrow_temporary(node, result)
            self.services.release_native_handle(cleanup)
        if plan.schema_ipc is None:
            self.services.arrow_temporary(node, result)
        self.services.function_state.result_stack.append(result)

    def lower_arrow_cast(
        self, node: astx.Cast, value: ir.Value, plan: ArrowConversion
    ) -> None:
        """
        title: >-
          Lower a resolved RecordBatch conversion through checked runtime APIs.
        parameters:
          node:
            type: astx.Cast
          value:
            type: ir.Value
          plan:
            type: ArrowConversion
        """
        builder = self.services.llvm.ir_builder
        zero = ir.Constant(ir.IntType(32), 0)
        index = ir.Constant(ir.IntType(32), plan.handle_index)
        if plan.to_dataframe:
            self.services.class_operation(node.value, "require", value)
            box = builder.load(builder.gep(value, [zero, index]))
            if plan.columns is None:
                convert = self.services.require_runtime_symbol(
                    "record_batch", "irx_rb_api_batch_to_dynamic_table"
                )
                table = self.services.checked_native_call(node, convert, [box])
                self.services.arrow_temporary(node, table)
                self.services.function_state.result_stack.append(table)
                return
            if plan.schema_ipc is not None:
                payload = ir.Constant(
                    ir.ArrayType(ir.IntType(8), len(plan.schema_ipc)),
                    bytearray(plan.schema_ipc),
                )
                global_value = ir.GlobalVariable(
                    self.services.llvm.module,
                    payload.type,
                    self.services.llvm.module.get_unique_name(
                        "dataframe_schema_ipc"
                    ),
                )
                global_value.linkage = "internal"
                global_value.global_constant = True
                global_value.initializer = payload
                pointer = builder.gep(
                    global_value, [zero, zero], inbounds=True
                )
                create = self.services.require_runtime_symbol(
                    "record_batch", "irx_rb_api_schema_ipc"
                )
                schema = self.services.checked_native_call(
                    node,
                    create,
                    [
                        pointer,
                        ir.Constant(ir.IntType(64), len(plan.schema_ipc)),
                    ],
                )
                cleanup = self.services.track_native_handle(
                    node, "record_batch", "irx_rb_api_schema_destroy", schema
                )
            else:
                create = self.services.require_runtime_symbol(
                    "record_batch", "irx_rb_api_schema_new"
                )
                schema = self.services.checked_native_call(node, create, [])
                cleanup = self.services.track_native_handle(
                    node, "record_batch", "irx_rb_api_schema_destroy", schema
                )
                add = self.services.require_runtime_symbol(
                    "record_batch", "irx_rb_api_schema_add"
                )
                for name, type_id, nullable in plan.columns:
                    pointer = self.services.strings.constant(
                        name, name_hint="dataframe_field"
                    )
                    self.services.checked_native_call(
                        node,
                        add,
                        [
                            schema,
                            pointer,
                            ir.Constant(ir.IntType(32), type_id),
                            ir.Constant(ir.IntType(32), int(nullable)),
                        ],
                    )
            convert = self.services.require_runtime_symbol(
                "record_batch", "irx_rb_api_batch_to_table"
            )
            table = self.services.checked_native_call(
                node, convert, [box, schema]
            )
            self.services.arrow_temporary(node, table)
            self.services.release_native_handle(cleanup)
            self.services.function_state.result_stack.append(table)
            return
        resolution = require_semantic_metadata(
            cast(
                SemanticInfo, getattr(node, "semantic", None)
            ).resolved_class_construction,
            node=node,
            metadata="resolved_class_construction",
            context="Arrow cast",
        )
        self.services.lower_class_construct(node, resolution)
        instance = self.services.function_state.result_stack[-1]
        box = builder.load(builder.gep(instance, [zero, index]))
        convert = self.services.require_runtime_symbol(
            "record_batch",
            "irx_rb_api_table_to_dynamic_batch"
            if plan.columns is None
            else "irx_rb_api_table_to_batch",
        )
        self.services.checked_native_call(node, convert, [value, box])
