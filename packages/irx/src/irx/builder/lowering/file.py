"""
title: Lower semantically resolved single-owner file operations.
"""

from typing import Any, cast

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
from irx.builder.lowering.control_flow import ControlFlowVisitorMixin
from irx.builder.protocols import VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.file import FILE_ERROR_CAPACITY
from irx.builder.state import CleanupAction
from irx.typecheck import typechecked


@private
@typechecked
class FileVisitorMixin(VisitorMixinBase):
    """
    title: Focused file lowering using native status and ownership contracts.
    """

    def file_error_buffer(self) -> ir.Value:
        """
        title: Allocate caller-owned native error storage.
        returns:
          type: ir.Value
        """
        storage = self.create_entry_block_alloca(
            "file_error",
            ir.ArrayType(self._llvm.INT8_TYPE, FILE_ERROR_CAPACITY),
        )
        zero = ir.Constant(self._llvm.INT32_TYPE, 0)
        return self._llvm.ir_builder.gep(storage, [zero, zero], inbounds=True)

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
        function = self._llvm.ir_builder.function
        fail = function.append_basic_block("native.fail")
        success = function.append_basic_block("native.ok")
        ok = self._llvm.ir_builder.icmp_signed(
            "==",
            status,
            ir.Constant(self._llvm.INT32_TYPE, 0),
        )
        self._llvm.ir_builder.cbranch(ok, success, fail)
        self._llvm.ir_builder.position_at_end(fail)
        pending = cast(Any, self).exception_call(
            "pending", [cast(Any, self).context_value()]
        )
        existing = function.append_basic_block("native.pending")
        materialize = function.append_basic_block("native.error")
        self._llvm.ir_builder.cbranch(
            self._llvm.ir_builder.icmp_signed(
                "!=", pending, ir.Constant(ir.IntType(32), 0)
            ),
            existing,
            materialize,
        )
        self._llvm.ir_builder.position_at_end(existing)
        cast(Any, self).emit_exception_transfer(node)
        self._llvm.ir_builder.position_at_end(materialize)
        if code == "ARX-RUNTIME-FILE-001":
            os_error = function.append_basic_block("native.oserror")
            value_error = function.append_basic_block("native.valueerror")
            self._llvm.ir_builder.cbranch(
                self._llvm.ir_builder.icmp_signed(
                    ">=", status, ir.Constant(ir.IntType(32), 65536)
                ),
                os_error,
                value_error,
            )
            self._llvm.ir_builder.position_at_end(os_error)
            cast(Any, self).raise_runtime_exception(
                node, "OSError", error, code=code
            )
            self._llvm.ir_builder.position_at_end(value_error)
            overflow = function.append_basic_block("native.overflow")
            other = function.append_basic_block("native.filevalue")
            self._llvm.ir_builder.cbranch(
                self._llvm.ir_builder.icmp_signed(
                    "==", status, ir.Constant(ir.IntType(32), 5)
                ),
                overflow,
                other,
            )
            self._llvm.ir_builder.position_at_end(overflow)
            cast(Any, self).raise_runtime_exception(
                node, "OverflowError", error, code=code
            )
            self._llvm.ir_builder.position_at_end(other)
            allocation = self._llvm.ir_builder.icmp_signed(
                "==", status, ir.Constant(ir.IntType(32), 4)
            )
            cast(Any, self).fatal_status(
                node,
                self._llvm.ir_builder.neg(
                    self._llvm.ir_builder.zext(allocation, ir.IntType(32))
                ),
            )
        cast(Any, self).raise_runtime_exception(
            node,
            "ValueError" if "FILE" in code else "RuntimeError",
            error,
            code=code,
        )
        self._llvm.ir_builder.position_at_end(success)

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
        release = self.require_runtime_symbol("file", "irx_file_release")

        def cleanup() -> None:
            """
            title: Release the captured owned handle, checking close failure.
            """
            status = self._llvm.ir_builder.call(release, [handle, error])
            self.file_check(node, status, error)

        self.cleanup_stack.append(
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
            self.visit_child(expression)
            values.append(
                require_lowered_value(
                    safe_pop(self.result_stack),
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
        self.result_stack.append(handle)

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
            else cast(
                ControlFlowVisitorMixin, self
            )._constant_c_string_pointer("r", name_hint="file_default_mode")
        )
        output = self.create_entry_block_alloca(
            "file_result", self._llvm.OPAQUE_POINTER_TYPE
        )
        error = self.file_error_buffer()
        function = self.require_runtime_symbol("file", "irx_file_open")
        status = self._llvm.ir_builder.call(
            function, [values[resolution.path_index], mode, output, error]
        )
        self.file_check(
            node, status, error, cleanup_temporaries=cleanup_temporaries
        )
        return self._llvm.ir_builder.load(output, name="file_handle")

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
        self.visit_child(node.receiver)
        handle = require_lowered_value(
            safe_pop(self.result_stack),
            node=node.receiver,
            context="file receiver",
        )
        if operation.receiver_field is not None:
            from irx.builder.lowering.classes import (  # noqa: PLC0415
                ClassVisitorMixin,
            )

            classes = cast(ClassVisitorMixin, self)
            classes.class_pin(node.receiver, handle)
            classes.class_operation(node, "require", handle)
            address = self._llvm.ir_builder.gep(
                handle,
                [
                    ir.Constant(self._llvm.INT32_TYPE, 0),
                    ir.Constant(
                        self._llvm.INT32_TYPE,
                        operation.receiver_field.storage_index,
                    ),
                ],
            )
            handle = self._llvm.ir_builder.load(address)
        arguments = [handle]
        if operation.receiver_field is not None:
            from irx.builder.lowering.functions import (  # noqa: PLC0415
                FunctionVisitorMixin,
            )

            resolution = require_semantic_metadata(
                semantic.resolved_call,
                node=node,
                metadata="resolved_call",
                context="public File method",
            )
            arguments.extend(
                cast(FunctionVisitorMixin, self).lower_bound_call_arguments(
                    resolution
                )
            )
        else:
            for expression in node.args:
                self.visit_child(expression)
                arguments.append(
                    require_lowered_value(
                        safe_pop(self.result_stack),
                        node=expression,
                        context="file argument",
                    )
                )
        output: ir.Value | None = None
        if operation.name in {"read", "write"}:
            output_type = (
                self._llvm.INT8_TYPE.as_pointer()
                if operation.name == "read"
                else self._llvm.INT64_TYPE
            )
            output = self.create_entry_block_alloca("file_output", output_type)
            arguments.append(output)
        error = self.file_error_buffer()
        arguments.append(error)
        function = self.require_runtime_symbol(
            "file", f"irx_file_{operation.name}"
        )
        status = self._llvm.ir_builder.call(function, arguments)
        self.file_check(node, status, error)
        if output is not None:
            result = self._llvm.ir_builder.load(output, name="file_value")
            if operation.name == "read":
                self._register_owned_string_temporary(node, result)
            self.result_stack.append(result)
