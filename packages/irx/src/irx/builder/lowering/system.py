# mypy: disable-error-code=no-redef

"""
title: System/runtime visitor mixins for llvmliteir.
"""

from typing import Any, cast

import astx

from llvmlite import ir

from irx.analysis.arrow_conversion import (
    ARROW_CONVERSION,
    ArrowConversion,
    ArrowTableCast,
)
from irx.analysis.resolved_nodes import SemanticInfo
from irx.analysis.types import (
    display_type_name,
    is_boolean_type,
    is_unsigned_type,
)
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_semantic_metadata,
)
from irx.builder.lowering.classes import ClassVisitorMixin
from irx.builder.lowering.control_flow import ControlFlowVisitorMixin
from irx.builder.runtime import safe_pop
from irx.builder.types import is_int_type
from irx.typecheck import typechecked


@typechecked
class SystemVisitorMixin(ClassVisitorMixin):
    @VisitorCore.visit.dispatch
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
                self._llvm_type_for_ast_type(node.target_type),
                node=node,
                metadata="nullable type",
                context="null construction",
            )
            self.result_stack.append(ir.Constant(storage, None))
            return
        self.visit_child(node.value)
        value = safe_pop(self.result_stack)
        if value is None:
            raise Exception("Invalid value in Cast")

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
        source_type = self._resolved_ast_type(node.value)
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

        target_llvm_type = self._llvm_type_for_ast_type(target_type)
        if target_llvm_type in (
            self._llvm.ASCII_STRING_TYPE,
            self._llvm.UTF8_STRING_TYPE,
        ):
            if (
                isinstance(value.type, ir.PointerType)
                and value.type.pointee == self._llvm.INT8_TYPE
            ):
                self.result_stack.append(value)
                return
            if is_int_type(value.type):
                arg, fmt_str = self._normalize_int_for_printf(
                    value,
                    unsigned=is_unsigned_type(source_type)
                    or is_boolean_type(source_type),
                )
                fmt_gv = self._get_or_create_format_global(fmt_str)
                ptr = self._snprintf_heap(node, fmt_gv, [arg])
                self._register_owned_string_temporary(node, ptr)
                self.result_stack.append(ptr)
                return

            if isinstance(
                value.type, (ir.FloatType, ir.DoubleType, ir.HalfType)
            ):
                if isinstance(value.type, (ir.FloatType, ir.HalfType)):
                    value_prom = self._llvm.ir_builder.fpext(
                        value, self._llvm.DOUBLE_TYPE, "to_double"
                    )
                else:
                    value_prom = value
                fmt_gv = self._get_or_create_format_global("%.6f")
                ptr = self._snprintf_heap(node, fmt_gv, [value_prom])
                self._register_owned_string_temporary(node, ptr)
                self.result_stack.append(ptr)
                return
            raise Exception(
                f"Unsupported cast from {value.type} to {target_llvm_type}"
            )
        result = self._cast_ast_value(
            value,
            source_type=source_type,
            target_type=target_type,
        )
        self.result_stack.append(result)

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.IsInstanceExpr) -> None:
        """
        title: Visit IsInstanceExpr nodes.
        parameters:
          node:
            type: astx.IsInstanceExpr
        """
        self.visit_child(node.value)
        _ = safe_pop(self.result_stack)
        static_result = cast(bool, getattr(node, "static_result", False))
        self.result_stack.append(
            ir.Constant(self._llvm.BOOLEAN_TYPE, int(static_result))
        )

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.PrintExpr) -> None:
        """
        title: Visit PrintExpr nodes.
        parameters:
          node:
            type: astx.PrintExpr
        """
        self.visit_child(node.message)
        message_value = safe_pop(self.result_stack)
        if message_value is None:
            raise Exception("Invalid message in PrintExpr")

        message_source_type = self._resolved_ast_type(node.message)
        message_type = message_value.type
        ptr: ir.Value
        release_formatted_pointer = False
        if (
            isinstance(message_type, ir.PointerType)
            and message_type.pointee == self._llvm.INT8_TYPE
        ):
            ptr = message_value
        elif is_int_type(message_type):
            int_arg, int_fmt = self._normalize_int_for_printf(
                message_value,
                unsigned=is_unsigned_type(message_source_type)
                or is_boolean_type(message_source_type),
            )
            int_fmt_gv = self._get_or_create_format_global(int_fmt)
            ptr = self._snprintf_heap(node, int_fmt_gv, [int_arg])
            release_formatted_pointer = True
        elif isinstance(
            message_type, (ir.HalfType, ir.FloatType, ir.DoubleType)
        ):
            if isinstance(message_type, (ir.HalfType, ir.FloatType)):
                float_arg = self._llvm.ir_builder.fpext(
                    message_value, self._llvm.DOUBLE_TYPE, "print_to_double"
                )
            else:
                float_arg = message_value
            float_fmt_gv = self._get_or_create_format_global("%.6f")
            ptr = self._snprintf_heap(node, float_fmt_gv, [float_arg])
            release_formatted_pointer = True
        else:
            raise Exception(
                f"Unsupported message type in PrintExpr: {message_type}"
            )

        puts_fn = self.require_runtime_symbol("libc", "puts")
        self._llvm.ir_builder.call(puts_fn, [ptr])
        if release_formatted_pointer:
            free_fn = self.require_runtime_symbol("libc", "free")
            self._llvm.ir_builder.call(free_fn, [ptr])
        self.result_stack.append(ir.Constant(self._llvm.INT32_TYPE, 0))

    @VisitorCore.visit.dispatch
    def visit(self, node: astx.TypeOfExpr) -> None:
        """
        title: Visit TypeOfExpr nodes.
        parameters:
          node:
            type: astx.TypeOfExpr
        """
        self.visit_child(node.value)
        _ = safe_pop(self.result_stack)
        type_name = display_type_name(self._resolved_ast_type(node.value))
        pointer = cast(Any, self)._constant_c_string_pointer(
            type_name,
            name_hint="type_name",
        )
        self.result_stack.append(pointer)

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
        builder = self._llvm.ir_builder
        if plan.schema_ipc is None:
            self.class_operation(node.value, "retain", value)
            result = value
        else:
            data = plan.schema_ipc
            payload = ir.Constant(
                ir.ArrayType(ir.IntType(8), len(data)), bytearray(data)
            )
            global_value = ir.GlobalVariable(
                self._llvm.module,
                payload.type,
                self._llvm.module.get_unique_name("table_cast_schema"),
            )
            global_value.linkage = "internal"
            global_value.global_constant = True
            global_value.initializer = payload
            zero = ir.Constant(ir.IntType(32), 0)
            pointer = builder.gep(global_value, [zero, zero], inbounds=True)
            create = self.require_runtime_symbol(
                "record_batch", "irx_rb_api_schema_ipc"
            )
            schema = builder.call(
                create, [pointer, ir.Constant(ir.IntType(64), len(data))]
            )
            convert = self.require_runtime_symbol(
                "record_batch", "irx_rb_api_table_cast"
            )
            result = builder.call(convert, [value, schema])
            destroy = self.require_runtime_symbol(
                "record_batch", "irx_rb_api_schema_destroy"
            )
            builder.call(destroy, [schema])
        self.arrow_temporary(node, result)
        self.result_stack.append(result)

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
        builder = self._llvm.ir_builder
        zero = ir.Constant(ir.IntType(32), 0)
        index = ir.Constant(ir.IntType(32), plan.handle_index)
        if plan.to_dataframe:
            self.class_operation(node.value, "require", value)
            box = builder.load(builder.gep(value, [zero, index]))
            if plan.columns is None:
                convert = self.require_runtime_symbol(
                    "record_batch", "irx_rb_api_batch_to_dynamic_table"
                )
                table = builder.call(convert, [box])
                self.arrow_temporary(node, table)
                self.result_stack.append(table)
                return
            if plan.schema_ipc is not None:
                payload = ir.Constant(
                    ir.ArrayType(ir.IntType(8), len(plan.schema_ipc)),
                    bytearray(plan.schema_ipc),
                )
                global_value = ir.GlobalVariable(
                    self._llvm.module,
                    payload.type,
                    self._llvm.module.get_unique_name("dataframe_schema_ipc"),
                )
                global_value.linkage = "internal"
                global_value.global_constant = True
                global_value.initializer = payload
                pointer = builder.gep(
                    global_value, [zero, zero], inbounds=True
                )
                create = self.require_runtime_symbol(
                    "record_batch", "irx_rb_api_schema_ipc"
                )
                schema = builder.call(
                    create,
                    [
                        pointer,
                        ir.Constant(ir.IntType(64), len(plan.schema_ipc)),
                    ],
                )
            else:
                create = self.require_runtime_symbol(
                    "record_batch", "irx_rb_api_schema_new"
                )
                schema = builder.call(create, [])
                add = self.require_runtime_symbol(
                    "record_batch", "irx_rb_api_schema_add"
                )
                for name, type_id, nullable in plan.columns:
                    pointer = cast(
                        ControlFlowVisitorMixin, self
                    )._constant_c_string_pointer(
                        name, name_hint="dataframe_field"
                    )
                    builder.call(
                        add,
                        [
                            schema,
                            pointer,
                            ir.Constant(ir.IntType(32), type_id),
                            ir.Constant(ir.IntType(32), int(nullable)),
                        ],
                    )
            convert = self.require_runtime_symbol(
                "record_batch", "irx_rb_api_batch_to_table"
            )
            table = builder.call(convert, [box, schema])
            destroy = self.require_runtime_symbol(
                "record_batch", "irx_rb_api_schema_destroy"
            )
            builder.call(destroy, [schema])
            self.arrow_temporary(node, table)
            self.result_stack.append(table)
            return
        resolution = require_semantic_metadata(
            cast(
                SemanticInfo, getattr(node, "semantic", None)
            ).resolved_class_construction,
            node=node,
            metadata="resolved_class_construction",
            context="Arrow cast",
        )
        self.lower_class_construct(node, resolution)
        instance = self.result_stack[-1]
        box = builder.load(builder.gep(instance, [zero, index]))
        convert = self.require_runtime_symbol(
            "record_batch",
            "irx_rb_api_table_to_dynamic_batch"
            if plan.columns is None
            else "irx_rb_api_table_to_batch",
        )
        builder.call(convert, [value, box])
