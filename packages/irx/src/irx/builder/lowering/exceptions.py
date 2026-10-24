# mypy: disable-error-code=no-redef
"""
title: Explicit status propagation and lexical exception exit regions.
"""

from typing import Any, cast

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import (
    ClassHeaderFieldKind,
    ExceptionCauseMode,
    FunctionSignature,
    ResolvedExceptionType,
    SemanticInfo,
)
from irx.builder.core import VisitorCore
from irx.builder.diagnostics import (
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.protocols import DispatchRegistrar, VisitorMixinBase
from irx.builder.runtime import safe_pop
from irx.builder.runtime.record_batch_api import is_checked_native_facade
from irx.builder.state import (
    CleanupAction,
    CleanupKind,
    ExceptionTarget,
    LoopTargets,
    PendingReturn,
)
from irx.typecheck import typechecked


@private
@typechecked
class ExceptionVisitorMixin(VisitorMixinBase):
    """
    title: Lower resolved exceptions without foreign stack unwinding.
    """

    def exception_call(self, operation: str, args: list[ir.Value]) -> ir.Value:
        """
        title: Call one registered opaque exception-runtime operation.
        parameters:
          operation:
            type: str
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        function = self.require_runtime_symbol(
            "exceptions", "irx_exception_" + operation
        )
        return self._llvm.ir_builder.call(function, args)

    def context_value(self) -> ir.Value:
        """
        title: Require the execution context of a generated frame.
        returns:
          type: ir.Value
        """
        assert self.exception_context is not None
        return self.exception_context

    def exception_string(self, value: str) -> ir.Value:
        """
        title: Materialize an immutable native diagnostic string.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        return cast(Any, self)._constant_c_string_pointer(
            value, name_hint="exception.text"
        )

    def exception_location(self, node: astx.AST) -> list[ir.Value]:
        """
        title: Preserve the source location supplied by semantic analysis.
        parameters:
          node:
            type: astx.AST
        returns:
          type: list[ir.Value]
        """
        return [
            self.exception_string(cast(Any, self)._assert_source_name(node)),
            ir.Constant(ir.IntType(32), node.loc.line),
            ir.Constant(ir.IntType(32), node.loc.col),
        ]

    def emit_resolved_call(
        self,
        node: astx.AST,
        callee: ir.Value,
        signature: FunctionSignature,
        args: list[ir.Value],
    ) -> ir.Value | None:
        """
        title: Read an ABI result slot only on the successful status edge.
        parameters:
          node:
            type: astx.AST
          callee:
            type: ir.Value
          signature:
            type: FunctionSignature
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value | None
        """
        if not signature.exception_abi:
            if any(
                is_checked_native_facade(
                    signature.symbol_name,
                    name,
                    self.runtime_features.feature(name).metadata.get(
                        "checked_facade_abi"
                    ),
                )
                for name in signature.required_runtime_features
            ):
                value = cast(Any, self).checked_native_call(node, callee, args)
                return (
                    None
                    if isinstance(signature.return_type, astx.NoneType)
                    else value
                )
            value = self._llvm.ir_builder.call(callee, args)
            return None if isinstance(value.type, ir.VoidType) else value
        result_type = self._llvm_type_for_ast_type(signature.return_type)
        assert result_type is not None
        output = None
        operands = [self.context_value(), *args]
        if not isinstance(result_type, ir.VoidType):
            output = self.create_entry_block_alloca("call.result", result_type)
            operands.append(output)
        status = self._llvm.ir_builder.call(callee, operands, "call.status")
        self.propagate_status(node, status)
        return None if output is None else self._llvm.ir_builder.load(output)

    def propagate_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: Route failed generated calls through the active lexical exits.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
        """
        function = self._llvm.ir_builder.function
        success = function.append_basic_block("call.success")
        failure = function.append_basic_block("call.failure")
        self._llvm.ir_builder.cbranch(
            self._llvm.ir_builder.icmp_signed(
                "==", status, ir.Constant(status.type, 0)
            ),
            success,
            failure,
        )
        self._llvm.ir_builder.position_at_end(failure)
        self.exception_call(
            "trace", [self.context_value(), *self.exception_location(node)]
        )
        self.emit_exception_transfer(node)
        self._llvm.ir_builder.position_at_end(success)

    def abandon_pending_returns(
        self,
        completions: tuple[PendingReturn, ...] | None = None,
        *,
        preserved_depth: int | None = None,
    ) -> None:
        """
        title: Release only suspended return results replaced by this transfer.
        parameters:
          completions:
            type: tuple[PendingReturn, Ellipsis] | None
          preserved_depth:
            type: int | None
        """
        saved = self.pending_returns
        selected = tuple(saved) if completions is None else completions
        self.pending_returns = [
            item
            for item in saved
            if not any(item is chosen for chosen in selected)
        ]
        try:
            for completion in reversed(selected):
                if (
                    preserved_depth is not None
                    and completion.restore_depth is not None
                    and preserved_depth > completion.restore_depth
                ):
                    continue
                for release in reversed(completion.actions):
                    release()
        finally:
            self.pending_returns = saved

    def abandon_loop_returns(self, target: LoopTargets) -> None:
        """
        title: A loop transfer replaces only returns outside its local loops.
        parameters:
          target:
            type: LoopTargets
        """
        self.abandon_pending_returns(
            tuple(
                completion
                for completion in self.pending_returns
                if any(target is loop for loop in completion.loops)
            ),
            preserved_depth=target.cleanup_depth,
        )

    def propagate_pending_exception(self) -> None:
        """
        title: Stop ordinary cleanup at the nearest still-active handler.
        """
        pending = self.exception_call("pending", [self.context_value()])
        with self._llvm.ir_builder.if_then(
            self._llvm.ir_builder.icmp_signed(
                "!=", pending, ir.Constant(ir.IntType(32), 0)
            )
        ):
            self.emit_exception_transfer(None)

    def emit_exception_transfer(self, node: astx.AST | None) -> None:
        """
        title: Unwind lexical cleanup regions without crossing native frames.
        parameters:
          node:
            type: astx.AST | None
        """
        target = next(
            (
                item
                for item in reversed(self.exception_targets)
                if item.cleanup_depth <= len(self.cleanup_stack)
            ),
            None,
        )
        # A locally handled failure cancels only the innermost candidate,
        # not older completions suspended outside that handler.
        self.abandon_pending_returns(
            tuple(
                completion
                for completion in self.pending_returns
                if target is None
                or any(target is item for item in completion.exception_targets)
            ),
            preserved_depth=None if target is None else target.cleanup_depth,
        )
        previous = self.emitting_failure_cleanup
        self.emitting_failure_cleanup = True
        try:
            self._emit_active_cleanups(
                0 if target is None else target.cleanup_depth
            )
        finally:
            self.emitting_failure_cleanup = previous
        if self._llvm.ir_builder.block.is_terminated:
            return
        if target is not None:
            self._llvm.ir_builder.branch(target.block)
        else:
            self._llvm.ir_builder.ret(ir.Constant(ir.IntType(32), 1))

    def emit_success_return(self, value: ir.Value | None) -> None:
        """
        title: Publish a return value only after every exit region succeeded.
        parameters:
          value:
            type: ir.Value | None
        """
        if self.exception_context is None:
            if value is None:
                self._llvm.ir_builder.ret_void()
            else:
                self._llvm.ir_builder.ret(value)
            return
        if value is not None:
            assert self.exception_result_slot is not None
            self._llvm.ir_builder.store(value, self.exception_result_slot)
        self._llvm.ir_builder.ret(ir.Constant(ir.IntType(32), 0))

    def emit_entry_wrapper(self) -> None:
        """
        title: Keep the platform main ABI outside the generated status ABI.
        """
        if self.entry_function_symbol_id is None:
            return
        entry = self.llvm_functions_by_symbol_id.get(
            self.entry_function_symbol_id
        )
        if entry is None:
            return
        integer = ir.IntType(32)
        pointer = ir.IntType(8).as_pointer()
        wrapper = ir.Function(
            self._llvm.module, ir.FunctionType(integer, []), "main"
        )
        previous = self._llvm.ir_builder
        self._llvm.ir_builder = ir.IRBuilder(
            wrapper.append_basic_block("entry")
        )
        context_out = self._llvm.ir_builder.alloca(pointer)
        created = self.exception_call("context_create", [context_out])
        ready = wrapper.append_basic_block("ready")
        failed = wrapper.append_basic_block("context.failed")
        self._llvm.ir_builder.cbranch(
            self._llvm.ir_builder.icmp_signed(
                "==", created, ir.Constant(integer, 0)
            ),
            ready,
            failed,
        )
        self._llvm.ir_builder.position_at_end(failed)
        fatal = self.require_runtime_symbol("errors", "__arx_runtime_fail")
        self._llvm.ir_builder.call(
            fatal,
            [
                self.exception_string("ARX-RUNTIME-EXCEPTION-001"),
                self.exception_string(""),
                ir.Constant(integer, -1),
                ir.Constant(integer, -1),
                self.exception_string("execution context allocation failed"),
            ],
        )
        self._llvm.ir_builder.unreachable()
        self._llvm.ir_builder.position_at_end(ready)
        context = self._llvm.ir_builder.load(context_out)
        args = [context]
        result = None
        if len(entry.args) > 1:
            result = self._llvm.ir_builder.alloca(entry.args[-1].type.pointee)
            args.append(result)
        status = self._llvm.ir_builder.call(entry, args)
        success = wrapper.append_basic_block("success")
        failure = wrapper.append_basic_block("failure")
        self._llvm.ir_builder.cbranch(
            self._llvm.ir_builder.icmp_signed(
                "==", status, ir.Constant(integer, 0)
            ),
            success,
            failure,
        )
        self._llvm.ir_builder.position_at_end(failure)
        self.exception_call("report", [context])
        self.exception_call("context_destroy", [context])
        self._llvm.ir_builder.ret(ir.Constant(integer, 1))
        self._llvm.ir_builder.position_at_end(success)
        code = (
            ir.Constant(integer, 0)
            if result is None
            else self._llvm.ir_builder.load(result)
        )
        if code.type != integer:
            code = (
                self._llvm.ir_builder.trunc(code, integer)
                if code.type.width > integer.width
                else self._llvm.ir_builder.zext(code, integer)
            )
        self.exception_call("context_destroy", [context])
        self._llvm.ir_builder.ret(code)
        self._llvm.ir_builder = previous

    def exception_field_address(
        self,
        payload: ir.Value,
        exception: ResolvedExceptionType,
        *,
        diagnostic: bool = True,
    ) -> ir.Value:
        """
        title: Address an inherited exception field through its descriptor.
        parameters:
          payload:
            type: ir.Value
          exception:
            type: ResolvedExceptionType
          diagnostic:
            type: bool
        returns:
          type: ir.Value
        """
        field = (
            exception.diagnostic_field
            if diagnostic
            else exception.message_field
        )
        descriptor = cast(Any, self).class_field_function(exception.class_)
        raw = self._llvm.ir_builder.call(
            descriptor,
            [
                cast(Any, self).class_raw(payload),
                ir.Constant(ir.IntType(32), field.access_index),
            ],
        )
        return self._llvm.ir_builder.bitcast(
            raw, ir.IntType(8).as_pointer().as_pointer()
        )

    def initialize_exception_record(
        self,
        node: astx.AST,
        payload: ir.Value,
        exception: ResolvedExceptionType,
        *,
        location: list[ir.Value] | None = None,
    ) -> None:
        """
        title: Snapshot nominal ancestry and message into an opaque record.
        parameters:
          node:
            type: astx.AST
          payload:
            type: ir.Value
          exception:
            type: ResolvedExceptionType
          location:
            type: list[ir.Value] | None
        """
        pointer = ir.IntType(8).as_pointer()
        identifiers = [
            self.exception_string(item) for item in exception.ancestry
        ]
        array = self._llvm.ir_builder.alloca(
            ir.ArrayType(pointer, len(identifiers))
        )
        zero = ir.Constant(ir.IntType(32), 0)
        for index, value in enumerate(identifiers):
            self._llvm.ir_builder.store(
                value,
                self._llvm.ir_builder.gep(
                    array, [zero, ir.Constant(ir.IntType(32), index)]
                ),
            )
        slot = self.exception_field_address(payload, exception)
        message = self._llvm.ir_builder.load(
            self.exception_field_address(payload, exception, diagnostic=False)
        )
        status = self.exception_call(
            "info_create",
            [
                self.exception_string(exception.class_.qualified_name),
                message,
                self._llvm.ir_builder.gep(array, [zero, zero]),
                ir.Constant(ir.IntType(32), len(identifiers)),
                slot,
            ],
        )
        self.fatal_status(node, status, location=location)

    def fatal_status(
        self,
        node: astx.AST,
        status: ir.Value,
        *,
        location: list[ir.Value] | None = None,
    ) -> None:
        """
        title: Fail non-recursively when exception bookkeeping cannot allocate.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
          location:
            type: list[ir.Value] | None
        """
        with self._llvm.ir_builder.if_then(
            self._llvm.ir_builder.icmp_signed(
                "<", status, ir.Constant(status.type, 0)
            )
        ):
            failure = self.require_runtime_symbol(
                "errors", "__arx_runtime_fail"
            )
            self._llvm.ir_builder.call(
                failure,
                [
                    self.exception_string("ARX-RUNTIME-EXCEPTION-001"),
                    *(
                        self.exception_location(node)
                        if location is None
                        else location
                    ),
                    self.exception_string(
                        "exception runtime allocation failed"
                    ),
                ],
            )
            self._llvm.ir_builder.unreachable()

    def raise_runtime_exception(
        self,
        node: astx.AST,
        role: str,
        message: ir.Value,
        *,
        code: str,
    ) -> None:
        """
        title: Materialize a trusted builtin exception for a native failure.
        parameters:
          node:
            type: astx.AST
          role:
            type: str
          message:
            type: ir.Value
          code:
            type: str
        """
        exception = require_semantic_metadata(
            self.runtime_exception_types.get(role),
            node=node,
            metadata="runtime_exception_types",
            context=role,
        )
        helper = self.builtin_exception_helper(node, exception)
        self._llvm.ir_builder.call(
            helper,
            [
                self.context_value(),
                message,
                *self.exception_location(node),
                self.exception_string(code),
            ],
        )
        self.emit_exception_transfer(node)

    def builtin_exception_helper(
        self, node: astx.AST, exception: ResolvedExceptionType
    ) -> ir.Function:
        """
        title: Share cold builtin materialization between failure guards.
        parameters:
          node:
            type: astx.AST
          exception:
            type: ResolvedExceptionType
        returns:
          type: ir.Function
        """
        name = "irx.raise." + exception.class_.qualified_name
        existing = self._llvm.module.globals.get(name)
        if isinstance(existing, ir.Function):
            return existing
        pointer = ir.IntType(8).as_pointer()
        integer = ir.IntType(32)
        helper = ir.Function(
            self._llvm.module,
            ir.FunctionType(
                integer, [pointer, pointer, pointer, integer, integer, pointer]
            ),
            name,
        )
        helper.linkage = "internal"
        helper.attributes.add("noinline")
        helper.attributes.add("cold")
        for argument, label in zip(
            helper.args,
            ("context", "message", "source", "line", "column", "code"),
        ):
            argument.name = label
        saved = (
            self._llvm.ir_builder,
            self.exception_context,
            self.exception_result_slot,
            self.exception_targets,
            self.cleanup_stack,
            self.pending_returns,
        )
        self._llvm.ir_builder = ir.IRBuilder(
            helper.append_basic_block("entry")
        )
        self.exception_context = helper.args[0]
        self.exception_result_slot = None
        self.exception_targets = []
        self.cleanup_stack = []
        self.pending_returns = []
        try:
            status = self.materialize_runtime_exception(
                node,
                exception,
                helper.args[1],
                list(helper.args[2:5]),
                helper.args[5],
            )
            self._llvm.ir_builder.ret(status)
        finally:
            (
                self._llvm.ir_builder,
                self.exception_context,
                self.exception_result_slot,
                self.exception_targets,
                self.cleanup_stack,
                self.pending_returns,
            ) = saved
        return helper

    def materialize_runtime_exception(
        self,
        node: astx.AST,
        exception: ResolvedExceptionType,
        message: ir.Value,
        location: list[ir.Value],
        code: ir.Value,
    ) -> ir.Value:
        """
        title: Create a builtin payload and pending status in a cold helper.
        parameters:
          node:
            type: astx.AST
          exception:
            type: ResolvedExceptionType
          message:
            type: ir.Value
          location:
            type: list[ir.Value]
          code:
            type: ir.Value
        returns:
          type: ir.Value
        """
        class_ = cast(
            SemanticInfo, getattr(exception.class_.declaration, "semantic")
        ).resolved_class
        assert class_ is not None
        layout = class_.layout
        assert layout is not None
        type_ = self._llvm_type_for_ast_type(
            astx.ClassType(
                class_.name,
                module_key=class_.module_key,
                qualified_name=class_.qualified_name,
            )
        )
        assert type_ is not None
        pointer = ir.IntType(8).as_pointer()
        integer = ir.IntType(32)
        zero = ir.Constant(integer, 0)
        size = self._llvm.ir_builder.ptrtoint(
            self._llvm.ir_builder.gep(
                ir.Constant(type_, None), [ir.Constant(integer, 1)]
            ),
            self._llvm.SIZE_T_TYPE,
        )
        output = self.create_entry_block_alloca("exception.object", pointer)
        details = cast(Any, self).file_error_buffer()
        create = self.require_runtime_symbol("class", "irx_class_create")
        status = self._llvm.ir_builder.call(
            create,
            [
                size,
                cast(Any, self).class_drop_function(class_),
                output,
                details,
            ],
        )
        self.fatal_status(
            node, self._llvm.ir_builder.neg(status), location=location
        )
        raw = self._llvm.ir_builder.load(output)
        value = self._llvm.ir_builder.bitcast(raw, type_)

        for header in layout.header_fields:
            if header.kind is ClassHeaderFieldKind.LIFETIME:
                continue
            initial = ir.Constant(pointer, None)
            if header.kind is ClassHeaderFieldKind.TYPE_DESCRIPTOR:
                initial = self._llvm.ir_builder.bitcast(
                    cast(Any, self).class_field_function(class_), pointer
                )
            if (
                header.kind is ClassHeaderFieldKind.DISPATCH_TABLE
                and layout.dispatch_table_size
            ):
                initial = self._llvm.ir_builder.bitcast(
                    self._llvm.module.globals[layout.dispatch_global_name],
                    pointer,
                )
            self._llvm.ir_builder.store(
                initial,
                self._llvm.ir_builder.gep(
                    value, [zero, ir.Constant(integer, header.storage_index)]
                ),
            )
        message = self._llvm.ir_builder.select(
            self._llvm.ir_builder.icmp_unsigned(
                "==", message, ir.Constant(pointer, None)
            ),
            self.exception_string(""),
            message,
        )
        copy = self._llvm.ir_builder.call(
            cast(Any, self)._create_strcat_inline(),
            [message, self.exception_string("")],
        )
        invalid = self._llvm.ir_builder.icmp_unsigned(
            "==", copy, ir.Constant(pointer, None)
        )
        self.fatal_status(
            node,
            self._llvm.ir_builder.neg(
                self._llvm.ir_builder.zext(invalid, integer)
            ),
            location=location,
        )
        self._llvm.ir_builder.store(
            copy,
            self.exception_field_address(value, exception, diagnostic=False),
        )
        self.initialize_exception_record(
            node, value, exception, location=location
        )
        status = self.exception_call(
            "raise",
            [
                self.context_value(),
                raw,
                self.exception_field_address(value, exception),
                ir.Constant(pointer, None),
                zero,
                *location,
                code,
            ],
        )
        self.fatal_status(node, status, location=location)
        release = self.require_runtime_symbol("class", "irx_class_release")
        self._llvm.ir_builder.call(
            release, [self.context_value(), raw, details]
        )
        return status

    @cast(DispatchRegistrar, VisitorCore.visit).dispatch
    def visit(self, node: astx.ThrowStmt) -> None:
        """
        title: Raise one evaluated nominal exception or dynamically re-raise.
        parameters:
          node:
            type: astx.ThrowStmt
        """
        semantic = cast(SemanticInfo | None, getattr(node, "semantic", None))
        resolution = require_semantic_metadata(
            None if semantic is None else semantic.resolved_raise,
            node=node,
            metadata="resolved_raise",
            context="raise",
        )
        if node.exception is None:
            status = self.exception_call("reraise", [self.context_value()])
            with self._llvm.ir_builder.if_then(
                self._llvm.ir_builder.icmp_signed(
                    "<", status, ir.Constant(ir.IntType(32), 0)
                )
            ):
                self.raise_runtime_exception(
                    node,
                    "RuntimeError",
                    self.exception_string("no active exception to re-raise"),
                    code="ARX-RUNTIME-EXCEPTION-002",
                )
        else:
            self.visit_child(node.exception)
            value = require_lowered_value(
                safe_pop(self.result_stack), node=node, context="raise operand"
            )
            assert resolution.exception_type is not None
            cast(Any, self).class_operation(node.exception, "require", value)
            # Cause evaluation may mutate the field/binding that provided the
            # operand. Keep that evaluated object alive until raise retains it.
            cast(Any, self).class_pin(node.exception, value)
            slot = self.exception_field_address(
                value, resolution.exception_type
            )
            cause = ir.Constant(ir.IntType(8).as_pointer(), None)
            mode = {
                ExceptionCauseMode.IMPLICIT: 0,
                ExceptionCauseMode.EXPLICIT: 1,
                ExceptionCauseMode.SUPPRESS: 2,
            }[resolution.cause_mode]
            if mode == 1:
                assert (
                    node.cause is not None
                    and resolution.cause_type is not None
                )
                self.visit_child(node.cause)
                cause_value = require_lowered_value(
                    safe_pop(self.result_stack),
                    node=node.cause,
                    context="raise cause",
                )
                cast(Any, self).class_operation(
                    node.cause, "require", cause_value
                )
                cause = self._llvm.ir_builder.load(
                    self.exception_field_address(
                        cause_value, resolution.cause_type
                    )
                )
            status = self.exception_call(
                "raise",
                [
                    self.context_value(),
                    cast(Any, self).class_raw(value),
                    slot,
                    cause,
                    ir.Constant(ir.IntType(32), mode),
                    *self.exception_location(node),
                    self.exception_string(""),
                ],
            )
            self.fatal_status(node, status)
        self.emit_exception_transfer(node)

    def lower_exception_suite(
        self, block: astx.Block, *, preserve_scope: bool = False
    ) -> None:
        """
        title: Lower a statement-only exception suite without leaking values.
        parameters:
          block:
            type: astx.Block
          preserve_scope:
            type: bool
        """
        depth = len(self.result_stack)
        try:
            cast(Any, self).lower_statement_block(
                block, preserve_scope=preserve_scope
            )
        finally:
            del self.result_stack[depth:]

    @cast(DispatchRegistrar, VisitorCore.visit).dispatch
    def visit(self, node: astx.ExceptionHandlerStmt) -> None:
        """
        title: Lower handlers and finalization as shared lexical exit regions.
        parameters:
          node:
            type: astx.ExceptionHandlerStmt
        """
        semantic = cast(SemanticInfo | None, getattr(node, "semantic", None))
        require_semantic_metadata(
            None if semantic is None else semantic.resolved_try,
            node=node,
            metadata="resolved_try",
            context="try",
        )
        function = self._llvm.ir_builder.function
        dispatch = function.append_basic_block("except.dispatch")
        merge = function.append_basic_block("try.end")
        initial = self.cleanup_stack
        depth = len(initial)
        self.cleanup_stack = list(initial)
        if node.finally_handler is not None:
            finalizer = node.finally_handler.body
            outer_targets = list(self.exception_targets)

            def finalize() -> None:
                """
                title: Execute finalization with the suspended error active.
                """
                token = self.exception_call(
                    "finally_enter", [self.context_value()]
                )
                saved = self.cleanup_stack
                saved_targets = self.exception_targets
                self.exception_targets = list(outer_targets)

                def discard() -> None:
                    """
                    title: Discard a completion replaced by an explicit exit.
                    """
                    self.exception_call(
                        "finally_leave",
                        [
                            self.context_value(),
                            token,
                            ir.Constant(ir.IntType(32), 0),
                        ],
                    )

                self.cleanup_stack = [
                    *saved,
                    CleanupAction(discard, kind=CleanupKind.HANDLER),
                ]
                self.lower_exception_suite(finalizer)
                self.cleanup_stack = saved
                self.exception_targets = saved_targets
                if not self._llvm.ir_builder.block.is_terminated:
                    self.exception_call(
                        "finally_leave",
                        [
                            self.context_value(),
                            token,
                            ir.Constant(ir.IntType(32), 1),
                        ],
                    )

            self.cleanup_stack.append(
                CleanupAction(finalize, kind=CleanupKind.FINALLY)
            )
        # This boundary marks when an exiting return has completed the try.
        # Destruction beyond it must not reenter this region's handlers.
        self.cleanup_stack.append(
            CleanupAction(
                lambda: None, kind=CleanupKind.HANDLER, fallible=False
            )
        )
        protected = list(self.cleanup_stack)
        self.exception_targets.append(
            ExceptionTarget(dispatch, len(protected))
        )
        self.lower_exception_suite(node.body, preserve_scope=True)
        self.exception_targets.pop()
        if not self._llvm.ir_builder.block.is_terminated:
            if node.else_body is not None:
                self.lower_exception_suite(node.else_body)
            if not self._llvm.ir_builder.block.is_terminated:
                self._emit_active_cleanups(depth)
            if not self._llvm.ir_builder.block.is_terminated:
                self._llvm.ir_builder.branch(merge)
        self.cleanup_stack = list(protected)
        self._llvm.ir_builder.position_at_end(dispatch)
        for handler in node.handlers.nodes:
            handler_info = cast(
                SemanticInfo | None, getattr(handler, "semantic", None)
            )
            resolved = require_semantic_metadata(
                None
                if handler_info is None
                else handler_info.resolved_exception_handler,
                node=handler,
                metadata="resolved_exception_handler",
                context="except",
            )
            body = function.append_basic_block("except.body")
            following = function.append_basic_block("except.next")
            match = ir.Constant(ir.IntType(1), not bool(resolved.types))
            for matched_type in resolved.types:
                matches = self.exception_call(
                    "matches",
                    [
                        self.context_value(),
                        self.exception_string(
                            matched_type.class_.qualified_name
                        ),
                    ],
                )
                match = self._llvm.ir_builder.or_(
                    match,
                    self._llvm.ir_builder.icmp_signed(
                        "!=", matches, ir.Constant(ir.IntType(32), 0)
                    ),
                )
            self._llvm.ir_builder.cbranch(match, body, following)
            self._llvm.ir_builder.position_at_end(body)
            token = self.exception_call(
                "handler_enter", [self.context_value()]
            )

            def leave(token: ir.Value = token) -> None:
                """
                title: Restore the dynamically enclosing handler state.
                parameters:
                  token:
                    type: ir.Value
                """
                self.exception_call(
                    "handler_leave", [self.context_value(), token]
                )

            self.cleanup_stack = [
                *protected,
                CleanupAction(leave, kind=CleanupKind.HANDLER),
            ]
            if resolved.symbol is not None:
                type_ = self._llvm_type_for_ast_type(resolved.binding_type)
                assert type_ is not None
                value = self._llvm.ir_builder.bitcast(
                    self.exception_call(
                        "handled_payload", [self.context_value()]
                    ),
                    type_,
                )
                slot = self.create_entry_block_alloca(
                    resolved.symbol.name, type_
                )
                self._llvm.ir_builder.store(value, slot)
                self.named_values[resolved.symbol.symbol_id] = slot
                cast(Any, self).class_operation(handler, "retain", value)
                cast(Any, self).class_cleanup(
                    handler, slot, resolved.symbol.symbol_id, storage=True
                )
            self.lower_exception_suite(handler.body)
            if not self._llvm.ir_builder.block.is_terminated:
                self._emit_active_cleanups(depth)
            if not self._llvm.ir_builder.block.is_terminated:
                self._llvm.ir_builder.branch(merge)
            self.cleanup_stack = list(protected)
            self._llvm.ir_builder.position_at_end(following)
        self.emit_exception_transfer(node)
        self.cleanup_stack = initial
        self._llvm.ir_builder.position_at_end(merge)
        if not any(
            merge in block.terminator.operands
            for block in function.blocks
            if block.terminator is not None
        ):
            self._llvm.ir_builder.unreachable()
