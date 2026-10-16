"""
title: Lower semantically resolved single-owner file operations.
"""

from typing import cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import OwnershipTransferKind, SemanticInfo
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
        if self.emitting_failure_cleanup:
            return
        function = self._llvm.ir_builder.function
        fail = function.append_basic_block("file.fail")
        success = function.append_basic_block("file.ok")
        ok = self._llvm.ir_builder.icmp_signed(
            "==",
            status,
            ir.Constant(self._llvm.INT32_TYPE, 0),
        )
        self._llvm.ir_builder.cbranch(ok, success, fail)
        self._llvm.ir_builder.position_at_end(fail)
        if cleanup_temporaries:
            # Do not replace the original failure with a cleanup error.
            self.emitting_failure_cleanup = True
            try:
                for cleanup in reversed(self.cleanup_stack):
                    if cleanup.owner_symbol_id is None:
                        cleanup.emitter()
            finally:
                self.emitting_failure_cleanup = False
        for instance in reversed(self.class_construction_stack):
            rollback_error = self.file_error_buffer()
            release = self.require_runtime_symbol("class", "irx_class_release")
            pointer = instance
            if pointer.type != self._llvm.INT8_TYPE.as_pointer():
                pointer = self._llvm.ir_builder.bitcast(
                    pointer, self._llvm.INT8_TYPE.as_pointer()
                )
            self._llvm.ir_builder.call(release, [pointer, rollback_error])
        failure = self.require_runtime_symbol("errors", "__arx_runtime_fail")
        self._llvm.ir_builder.call(
            failure,
            [
                cast(ControlFlowVisitorMixin, self)._constant_c_string_pointer(
                    code, name_hint="file_code"
                ),
                cast(ControlFlowVisitorMixin, self)._constant_c_string_pointer(
                    cast(ControlFlowVisitorMixin, self)._assert_source_name(
                        node
                    ),
                    name_hint="file_source",
                ),
                ir.Constant(self._llvm.INT32_TYPE, node.loc.line),
                ir.Constant(self._llvm.INT32_TYPE, node.loc.col),
                error,
            ],
        )
        self._llvm.ir_builder.unreachable()
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
        self.file_check(node, status, error)
        handle = self._llvm.ir_builder.load(output, name="file_handle")
        ownership = require_semantic_metadata(
            resource_ownership(node),
            node=node,
            metadata="resource_ownership",
            context="file open",
        )
        if ownership.transfer_kind is not OwnershipTransferKind.MOVE:
            self.file_cleanup(node, handle, None)
        self.result_stack.append(handle)

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
        arguments = [handle]
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
