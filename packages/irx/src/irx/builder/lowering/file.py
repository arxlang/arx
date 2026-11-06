"""
title: Lower semantically resolved single-owner file operations.
"""

import astx

from llvmlite import ir
from public import private

from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    OwnershipTransferKind,
    ResolvedFileOpen,
    SemanticInfo,
)
from irx.builder.diagnostics import (
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import FileServices
from irx.builder.runtime import safe_pop
from irx.builder.runtime.file import FILE_ERROR_CAPACITY
from irx.builder.state import CleanupAction
from irx.typecheck import typechecked


@private
@typechecked
class FileLowering:
    """
    title: Focused file lowering using native status and ownership contracts.
    attributes:
      services:
        type: FileServices
    """

    services: FileServices

    def __init__(self, services: FileServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: FileServices
        """
        self.services = services

    def file_error_buffer(self) -> ir.Value:
        """
        title: Allocate caller-owned native error storage.
        returns:
          type: ir.Value
        """
        storage = self.services.create_entry_block_alloca(
            "file_error",
            ir.ArrayType(self.services.llvm.INT8_TYPE, FILE_ERROR_CAPACITY),
        )
        zero = ir.Constant(self.services.llvm.INT32_TYPE, 0)
        return self.services.llvm.ir_builder.gep(
            storage, [zero, zero], inbounds=True
        )

    def file_check(
        self,
        node: astx.AST,
        status: ir.Value,
        error: ir.Value,
        *,
        code: str = "ARX-RUNTIME-FILE-001",
        cleanup_temporaries: bool = False,
    ) -> None:
        """
        title: Guard file outputs before use, reporting caller-owned errors.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          error:
            type: ir.Value
          code:
            type: str
          cleanup_temporaries:
            type: bool
        """
        function = self.services.llvm.ir_builder.function
        fail = function.append_basic_block("native.fail")
        success = function.append_basic_block("native.ok")
        ok = self.services.llvm.ir_builder.icmp_signed(
            "==",
            status,
            ir.Constant(self.services.llvm.INT32_TYPE, 0),
        )
        self.services.llvm.ir_builder.cbranch(ok, success, fail)
        self.services.llvm.ir_builder.position_at_end(fail)
        pending = self.services.exceptions.exception_call(
            "pending", [self.services.exceptions.context_value()]
        )
        existing = function.append_basic_block("native.pending")
        materialize = function.append_basic_block("native.error")
        self.services.llvm.ir_builder.cbranch(
            self.services.llvm.ir_builder.icmp_signed(
                "!=", pending, ir.Constant(ir.IntType(32), 0)
            ),
            existing,
            materialize,
        )
        self.services.llvm.ir_builder.position_at_end(existing)
        self.services.exceptions.emit_exception_transfer(node)
        self.services.llvm.ir_builder.position_at_end(materialize)
        if code == "ARX-RUNTIME-FILE-001":
            os_error = function.append_basic_block("native.oserror")
            value_error = function.append_basic_block("native.valueerror")
            self.services.llvm.ir_builder.cbranch(
                self.services.llvm.ir_builder.icmp_signed(
                    ">=", status, ir.Constant(ir.IntType(32), 65536)
                ),
                os_error,
                value_error,
            )
            self.services.llvm.ir_builder.position_at_end(os_error)
            self.services.raise_runtime_exception(
                node, "OSError", error, code=code
            )
            self.services.llvm.ir_builder.position_at_end(value_error)
            overflow = function.append_basic_block("native.overflow")
            other = function.append_basic_block("native.filevalue")
            self.services.llvm.ir_builder.cbranch(
                self.services.llvm.ir_builder.icmp_signed(
                    "==", status, ir.Constant(ir.IntType(32), 5)
                ),
                overflow,
                other,
            )
            self.services.llvm.ir_builder.position_at_end(overflow)
            self.services.raise_runtime_exception(
                node, "OverflowError", error, code=code
            )
            self.services.llvm.ir_builder.position_at_end(other)
            allocation = self.services.llvm.ir_builder.icmp_signed(
                "==", status, ir.Constant(ir.IntType(32), 4)
            )
            self.services.fatal_status(
                node,
                self.services.llvm.ir_builder.neg(
                    self.services.llvm.ir_builder.zext(
                        allocation, ir.IntType(32)
                    )
                ),
            )
        self.services.raise_runtime_exception(
            node,
            "ValueError" if "FILE" in code else "RuntimeError",
            error,
            code=code,
        )
        self.services.llvm.ir_builder.position_at_end(success)

    def file_cleanup(
        self,
        node: astx.AST,
        handle: ir.Value,
        owner_id: str | None,
    ) -> None:
        """
        title: Register exactly-once wrapper release on ordinary scope exits.
        parameters:
          node:
            type: astx.AST
          handle:
            type: ir.Value
          owner_id:
            type: str | None
        """
        error = self.file_error_buffer()
        release = self.services.require_runtime_symbol(
            "file", "irx_file_release"
        )

        def cleanup() -> None:
            """
            title: Release the captured owned handle, checking close failure.
            """
            status = self.services.llvm.ir_builder.call(
                release, [handle, error]
            )
            self.file_check(node, status, error)

        self.services.exit_state.cleanup_stack.append(
            CleanupAction(cleanup, owner_symbol_id=owner_id)
        )

    def lower_file_open(self, node: astx.FunctionCall) -> None:
        """
        title: Evaluate the resolved file operands and produce an owned handle.
        parameters:
          node:
            type: astx.FunctionCall
        """
        attached = getattr(node, "semantic", None)
        semantic = require_semantic_metadata(
            attached if isinstance(attached, SemanticInfo) else None,
            node=node,
            metadata="semantic",
            context="file open",
        )
        resolution = require_semantic_metadata(
            semantic.resolved_file_open,
            node=node,
            metadata="resolved_file_open",
            context="file open",
        )
        values: list[ir.Value] = []
        for expression in resolution.evaluations:
            self.services.visit_child(expression)
            values.append(
                require_lowered_value(
                    safe_pop(self.services.function_state.result_stack),
                    node=expression,
                    context="open argument",
                )
            )
        handle = self.create_native_file(node, resolution, values)
        ownership = require_semantic_metadata(
            resource_ownership(node),
            node=node,
            metadata="resource_ownership",
            context="file open",
        )
        if ownership.transfer_kind is not OwnershipTransferKind.MOVE:
            self.file_cleanup(node, handle, None)
        self.services.function_state.result_stack.append(handle)

    def create_native_file(
        self,
        node: astx.AST,
        resolution: ResolvedFileOpen,
        values: list[ir.Value],
        *,
        cleanup_temporaries: bool = False,
    ) -> ir.Value:
        """
        title: Publish a native handle only after caller-side status checking.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedFileOpen
          values:
            type: list[ir.Value]
          cleanup_temporaries:
            type: bool
        returns:
          type: ir.Value
        """
        mode = (
            values[resolution.mode_index]
            if resolution.mode_index is not None
            else self.services.strings.constant(
                "r", name_hint="file_default_mode"
            )
        )
        output = self.services.create_entry_block_alloca(
            "file_result", self.services.llvm.OPAQUE_POINTER_TYPE
        )
        error = self.file_error_buffer()
        function = self.services.require_runtime_symbol(
            "file", "irx_file_open"
        )
        status = self.services.llvm.ir_builder.call(
            function,
            [
                values[resolution.path_index],
                mode,
                ir.Constant(
                    self.services.llvm.INT32_TYPE, int(resolution.text_options)
                ),
                output,
                error,
            ],
        )
        self.file_check(
            node, status, error, cleanup_temporaries=cleanup_temporaries
        )
        return self.services.llvm.ir_builder.load(output, name="file_handle")

    def lower_file_method(self, node: astx.MethodCall) -> None:
        """
        title: Lower one validated file operation and its status-gated output.
        parameters:
          node:
            type: astx.MethodCall
        """
        attached = getattr(node, "semantic", None)
        semantic = require_semantic_metadata(
            attached if isinstance(attached, SemanticInfo) else None,
            node=node,
            metadata="semantic",
            context="file method",
        )
        operation = require_semantic_metadata(
            semantic.resolved_file_operation,
            node=node,
            metadata="resolved_file_operation",
            context="file method",
        )
        self.services.visit_child(node.receiver)
        handle = require_lowered_value(
            safe_pop(self.services.function_state.result_stack),
            node=node.receiver,
            context="file receiver",
        )
        if operation.receiver_field is not None:
            self.services.class_pin(node.receiver, handle)
            self.services.class_operation(node, "require", handle)
            address = self.services.llvm.ir_builder.gep(
                handle,
                [
                    ir.Constant(self.services.llvm.INT32_TYPE, 0),
                    ir.Constant(
                        self.services.llvm.INT32_TYPE,
                        operation.receiver_field.storage_index,
                    ),
                ],
            )
            handle = self.services.llvm.ir_builder.load(address)
        arguments = [handle]
        if operation.receiver_field is not None:
            resolution = require_semantic_metadata(
                semantic.resolved_call,
                node=node,
                metadata="resolved_call",
                context="public File method",
            )
            arguments.extend(
                self.services.lower_bound_call_arguments(resolution)
            )
        else:
            for expression in node.args:
                self.services.visit_child(expression)
                arguments.append(
                    require_lowered_value(
                        safe_pop(self.services.function_state.result_stack),
                        node=expression,
                        context="file argument",
                    )
                )
        builder = self.services.llvm.ir_builder
        if operation.name == "write_bytes":
            data = arguments.pop()
            arguments.extend(
                [
                    builder.extract_value(data, 0),
                    builder.extract_value(data, 1),
                ]
            )
        byte_count: ir.Value | None = None
        output: ir.Value | None = None
        if operation.name in {"read", "write", "read_bytes", "write_bytes"}:
            output_type = (
                self.services.llvm.INT8_TYPE.as_pointer()
                if operation.name in {"read", "read_bytes"}
                else self.services.llvm.INT64_TYPE
            )
            output = self.services.create_entry_block_alloca(
                "file_output", output_type
            )
            arguments.append(output)
            if operation.name == "read_bytes":
                byte_count = self.services.create_entry_block_alloca(
                    "file_byte_count", self.services.llvm.INT64_TYPE
                )
                arguments.append(byte_count)
        error = self.file_error_buffer()
        arguments.append(error)
        function = self.services.require_runtime_symbol(
            "file", f"irx_file_{operation.name}"
        )
        status = self.services.llvm.ir_builder.call(function, arguments)
        self.file_check(node, status, error)
        if output is not None:
            result = self.services.llvm.ir_builder.load(
                output, name="file_value"
            )
            if operation.name == "read":
                self.services.cleanup.register_owned_string_temporary(
                    node, result
                )
            if operation.name == "read_bytes":
                assert byte_count is not None
                count = builder.load(byte_count)
                descriptor = builder.insert_value(
                    self.services.empty_list_value(node), result, 0
                )
                descriptor = builder.insert_value(descriptor, count, 1)
                descriptor = builder.insert_value(descriptor, count, 2)
                storage = self.services.create_entry_block_alloca(
                    "file_bytes", self.services.llvm_list_type()
                )
                builder.store(descriptor, storage)
                self.services.cleanup.register_owned_list_temporary(
                    node, storage
                )
                result = descriptor
            self.services.function_state.result_stack.append(result)
