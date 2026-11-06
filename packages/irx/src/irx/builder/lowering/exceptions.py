# mypy: disable-error-code=no-redef
"""
title: Explicit status propagation and lexical exception exit regions.
"""

from typing import cast

import astx

from llvmlite import ir
from plum import dispatch
from public import private

from irx.analysis.resolved_nodes import (
    ClassHeaderFieldKind,
    ExceptionCauseMode,
    ResolvedExceptionType,
    SemanticInfo,
)
from irx.builder.diagnostics import (
    raise_lowering_internal_error,
    require_lowered_value,
    require_semantic_metadata,
)
from irx.builder.lowering.contracts import ExceptionServices
from irx.builder.runtime import safe_pop
from irx.builder.state import (
    CleanupAction,
    CleanupKind,
    ExceptionTarget,
)
from irx.extensions.nodes import NodeHandler, contribute_node
from irx.typecheck import typechecked


@private
@typechecked
class ExceptionLowering:
    """
    title: Lower resolved exceptions without foreign stack unwinding.
    attributes:
      services:
        type: ExceptionServices
    """

    services: ExceptionServices

    def __init__(self, services: ExceptionServices) -> None:
        """
        title: Bind explicit family-owned emission dependencies.
        parameters:
          services:
            type: ExceptionServices
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
            f"no exceptions handler for {type(node).__name__}", node=node
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
                "llvm.exceptions.ThrowStmt",
                "irx.exceptions",
                "lowering",
                astx.ThrowStmt,
                self.visit,
                source="irx.builder.lowering.exceptions.ExceptionLowering.visit",
            ),
            contribute_node(
                "llvm.exceptions.ExceptionHandlerStmt",
                "irx.exceptions",
                "lowering",
                astx.ExceptionHandlerStmt,
                self.visit,
                source="irx.builder.lowering.exceptions.ExceptionLowering.visit",
            ),
        )

    def exception_string(self, value: str) -> ir.Value:
        """
        title: Materialize an immutable native diagnostic string.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        return self.services.strings.constant(
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
            self.exception_string(self.services.assert_source_name(node)),
            ir.Constant(ir.IntType(32), node.loc.line),
            ir.Constant(ir.IntType(32), node.loc.col),
        ]

    def emit_entry_wrapper(self) -> None:
        """
        title: Keep the platform main ABI outside the generated status ABI.
        """
        if self.services.module_state.entry_function_symbol_id is None:
            return
        entry = self.services.module_state.llvm_functions_by_symbol_id.get(
            self.services.module_state.entry_function_symbol_id
        )
        if entry is None:
            return
        integer = ir.IntType(32)
        pointer = ir.IntType(8).as_pointer()
        wrapper = ir.Function(
            self.services.llvm.module, ir.FunctionType(integer, []), "main"
        )
        previous = self.services.llvm.ir_builder
        self.services.llvm.ir_builder = ir.IRBuilder(
            wrapper.append_basic_block("entry")
        )
        context_out = self.services.llvm.ir_builder.alloca(pointer)
        created = self.services.exceptions.exception_call(
            "context_create", [context_out]
        )
        ready = wrapper.append_basic_block("ready")
        failed = wrapper.append_basic_block("context.failed")
        self.services.llvm.ir_builder.cbranch(
            self.services.llvm.ir_builder.icmp_signed(
                "==", created, ir.Constant(integer, 0)
            ),
            ready,
            failed,
        )
        self.services.llvm.ir_builder.position_at_end(failed)
        fatal = self.services.require_runtime_symbol(
            "errors", "__arx_runtime_fail"
        )
        self.services.llvm.ir_builder.call(
            fatal,
            [
                self.exception_string("ARX-RUNTIME-EXCEPTION-001"),
                self.exception_string(""),
                ir.Constant(integer, -1),
                ir.Constant(integer, -1),
                self.exception_string("execution context allocation failed"),
            ],
        )
        self.services.llvm.ir_builder.unreachable()
        self.services.llvm.ir_builder.position_at_end(ready)
        context = self.services.llvm.ir_builder.load(context_out)
        args = [context]
        result = None
        if len(entry.args) > 1:
            result = self.services.llvm.ir_builder.alloca(
                entry.args[-1].type.pointee
            )
            args.append(result)
        status = self.services.llvm.ir_builder.call(entry, args)
        success = wrapper.append_basic_block("success")
        failure = wrapper.append_basic_block("failure")
        self.services.llvm.ir_builder.cbranch(
            self.services.llvm.ir_builder.icmp_signed(
                "==", status, ir.Constant(integer, 0)
            ),
            success,
            failure,
        )
        self.services.llvm.ir_builder.position_at_end(failure)
        self.services.exceptions.exception_call("report", [context])
        self.services.exceptions.exception_call("context_destroy", [context])
        self.services.llvm.ir_builder.ret(ir.Constant(integer, 1))
        self.services.llvm.ir_builder.position_at_end(success)
        code = (
            ir.Constant(integer, 0)
            if result is None
            else self.services.llvm.ir_builder.load(result)
        )
        if code.type != integer:
            code = (
                self.services.llvm.ir_builder.trunc(code, integer)
                if code.type.width > integer.width
                else self.services.llvm.ir_builder.zext(code, integer)
            )
        self.services.exceptions.exception_call("context_destroy", [context])
        self.services.llvm.ir_builder.ret(code)
        self.services.llvm.ir_builder = previous

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
        descriptor = self.services.class_field_function(exception.class_)
        raw = self.services.llvm.ir_builder.call(
            descriptor,
            [
                self.services.class_raw(payload),
                ir.Constant(ir.IntType(32), field.access_index),
            ],
        )
        return self.services.llvm.ir_builder.bitcast(
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
        array = self.services.llvm.ir_builder.alloca(
            ir.ArrayType(pointer, len(identifiers))
        )
        zero = ir.Constant(ir.IntType(32), 0)
        for index, value in enumerate(identifiers):
            self.services.llvm.ir_builder.store(
                value,
                self.services.llvm.ir_builder.gep(
                    array, [zero, ir.Constant(ir.IntType(32), index)]
                ),
            )
        slot = self.exception_field_address(payload, exception)
        message = self.services.llvm.ir_builder.load(
            self.exception_field_address(payload, exception, diagnostic=False)
        )
        status = self.services.exceptions.exception_call(
            "info_create",
            [
                self.exception_string(exception.class_.qualified_name),
                message,
                self.services.llvm.ir_builder.gep(array, [zero, zero]),
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
        with self.services.llvm.ir_builder.if_then(
            self.services.llvm.ir_builder.icmp_signed(
                "<", status, ir.Constant(status.type, 0)
            )
        ):
            failure = self.services.require_runtime_symbol(
                "errors", "__arx_runtime_fail"
            )
            self.services.llvm.ir_builder.call(
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
            self.services.llvm.ir_builder.unreachable()

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
            self.services.exception_module_state.runtime_exception_types.get(
                role
            ),
            node=node,
            metadata="runtime_exception_types",
            context=role,
        )
        helper = self.builtin_exception_helper(node, exception)
        self.services.llvm.ir_builder.call(
            helper,
            [
                self.services.exceptions.context_value(),
                message,
                *self.exception_location(node),
                self.exception_string(code),
            ],
        )
        self.services.exceptions.emit_exception_transfer(node)

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
        existing = self.services.llvm.module.globals.get(name)
        if isinstance(existing, ir.Function):
            return existing
        pointer = ir.IntType(8).as_pointer()
        integer = ir.IntType(32)
        helper = ir.Function(
            self.services.llvm.module,
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
        saved_builder = self.services.llvm.ir_builder
        self.services.llvm.ir_builder = ir.IRBuilder(
            helper.append_basic_block("entry")
        )
        try:
            with self.services.exit_state.function_scope(helper.args[0]):
                status = self.materialize_runtime_exception(
                    node,
                    exception,
                    helper.args[1],
                    list(helper.args[2:5]),
                    helper.args[5],
                )
                self.services.llvm.ir_builder.ret(status)
        finally:
            self.services.llvm.ir_builder = saved_builder
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
        type_ = self.services.types.llvm_type(
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
        size = self.services.llvm.ir_builder.ptrtoint(
            self.services.llvm.ir_builder.gep(
                ir.Constant(type_, None), [ir.Constant(integer, 1)]
            ),
            self.services.llvm.SIZE_T_TYPE,
        )
        output = self.services.create_entry_block_alloca(
            "exception.object", pointer
        )
        details = self.services.file_error_buffer()
        create = self.services.require_runtime_symbol(
            "class", "irx_class_create"
        )
        status = self.services.llvm.ir_builder.call(
            create,
            [
                size,
                self.services.class_drop_function(class_),
                output,
                details,
            ],
        )
        self.fatal_status(
            node, self.services.llvm.ir_builder.neg(status), location=location
        )
        raw = self.services.llvm.ir_builder.load(output)
        value = self.services.llvm.ir_builder.bitcast(raw, type_)

        for header in layout.header_fields:
            if header.kind is ClassHeaderFieldKind.LIFETIME:
                continue
            initial = ir.Constant(pointer, None)
            if header.kind is ClassHeaderFieldKind.TYPE_DESCRIPTOR:
                initial = self.services.llvm.ir_builder.bitcast(
                    self.services.class_field_function(class_), pointer
                )
            if (
                header.kind is ClassHeaderFieldKind.DISPATCH_TABLE
                and layout.dispatch_table_size
            ):
                initial = self.services.llvm.ir_builder.bitcast(
                    self.services.llvm.module.globals[
                        layout.dispatch_global_name
                    ],
                    pointer,
                )
            self.services.llvm.ir_builder.store(
                initial,
                self.services.llvm.ir_builder.gep(
                    value, [zero, ir.Constant(integer, header.storage_index)]
                ),
            )
        message = self.services.llvm.ir_builder.select(
            self.services.llvm.ir_builder.icmp_unsigned(
                "==", message, ir.Constant(pointer, None)
            ),
            self.exception_string(""),
            message,
        )
        copy = self.services.llvm.ir_builder.call(
            self.services.strings.concatenation_function(),
            [message, self.exception_string("")],
        )
        invalid = self.services.llvm.ir_builder.icmp_unsigned(
            "==", copy, ir.Constant(pointer, None)
        )
        self.fatal_status(
            node,
            self.services.llvm.ir_builder.neg(
                self.services.llvm.ir_builder.zext(invalid, integer)
            ),
            location=location,
        )
        self.services.llvm.ir_builder.store(
            copy,
            self.exception_field_address(value, exception, diagnostic=False),
        )
        self.initialize_exception_record(
            node, value, exception, location=location
        )
        status = self.services.exceptions.exception_call(
            "raise",
            [
                self.services.exceptions.context_value(),
                raw,
                self.exception_field_address(value, exception),
                ir.Constant(pointer, None),
                zero,
                *location,
                code,
            ],
        )
        self.fatal_status(node, status, location=location)
        release = self.services.require_runtime_symbol(
            "class", "irx_class_release"
        )
        self.services.llvm.ir_builder.call(
            release, [self.services.exceptions.context_value(), raw, details]
        )
        return status

    @dispatch
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
            status = self.services.exceptions.exception_call(
                "reraise", [self.services.exceptions.context_value()]
            )
            with self.services.llvm.ir_builder.if_then(
                self.services.llvm.ir_builder.icmp_signed(
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
            self.services.visit_child(node.exception)
            value = require_lowered_value(
                safe_pop(self.services.function_state.result_stack),
                node=node,
                context="raise operand",
            )
            assert resolution.exception_type is not None
            self.services.class_operation(node.exception, "require", value)
            # Cause evaluation may mutate the field/binding that provided the
            # operand. Keep that evaluated object alive until raise retains it.
            self.services.class_pin(node.exception, value)
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
                self.services.visit_child(node.cause)
                cause_value = require_lowered_value(
                    safe_pop(self.services.function_state.result_stack),
                    node=node.cause,
                    context="raise cause",
                )
                self.services.class_operation(
                    node.cause, "require", cause_value
                )
                cause = self.services.llvm.ir_builder.load(
                    self.exception_field_address(
                        cause_value, resolution.cause_type
                    )
                )
            status = self.services.exceptions.exception_call(
                "raise",
                [
                    self.services.exceptions.context_value(),
                    self.services.class_raw(value),
                    slot,
                    cause,
                    ir.Constant(ir.IntType(32), mode),
                    *self.exception_location(node),
                    self.exception_string(""),
                ],
            )
            self.fatal_status(node, status)
        self.services.exceptions.emit_exception_transfer(node)

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
        depth = len(self.services.function_state.result_stack)
        try:
            self.services.lower_statement_block(
                block, preserve_scope=preserve_scope
            )
        finally:
            del self.services.function_state.result_stack[depth:]

    @dispatch
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
        function = self.services.llvm.ir_builder.function
        dispatch = function.append_basic_block("except.dispatch")
        merge = function.append_basic_block("try.end")
        initial = self.services.exit_state.cleanup_stack
        depth = len(initial)
        self.services.exit_state.cleanup_stack = list(initial)
        if node.finally_handler is not None:
            finalizer = node.finally_handler.body
            outer_targets = list(self.services.exit_state.exception_targets)

            def finalize() -> None:
                """
                title: Execute finalization with the suspended error active.
                """
                token = self.services.exceptions.exception_call(
                    "finally_enter", [self.services.exceptions.context_value()]
                )
                saved = self.services.exit_state.cleanup_stack
                saved_targets = self.services.exit_state.exception_targets
                self.services.exit_state.exception_targets = list(
                    outer_targets
                )

                def discard() -> None:
                    """
                    title: Discard a completion replaced by an explicit exit.
                    """
                    self.services.exceptions.exception_call(
                        "finally_leave",
                        [
                            self.services.exceptions.context_value(),
                            token,
                            ir.Constant(ir.IntType(32), 0),
                        ],
                    )

                self.services.exit_state.cleanup_stack = [
                    *saved,
                    CleanupAction(discard, kind=CleanupKind.HANDLER),
                ]
                self.lower_exception_suite(finalizer)
                self.services.exit_state.cleanup_stack = saved
                self.services.exit_state.exception_targets = saved_targets
                if not self.services.llvm.ir_builder.block.is_terminated:
                    self.services.exceptions.exception_call(
                        "finally_leave",
                        [
                            self.services.exceptions.context_value(),
                            token,
                            ir.Constant(ir.IntType(32), 1),
                        ],
                    )

            self.services.exit_state.cleanup_stack.append(
                CleanupAction(finalize, kind=CleanupKind.FINALLY)
            )
        # This boundary marks when an exiting return has completed the try.
        # Destruction beyond it must not reenter this region's handlers.
        self.services.exit_state.cleanup_stack.append(
            CleanupAction(
                lambda: None, kind=CleanupKind.HANDLER, fallible=False
            )
        )
        protected = list(self.services.exit_state.cleanup_stack)
        self.services.exit_state.exception_targets.append(
            ExceptionTarget(dispatch, len(protected))
        )
        self.lower_exception_suite(node.body, preserve_scope=True)
        self.services.exit_state.exception_targets.pop()
        if not self.services.llvm.ir_builder.block.is_terminated:
            if node.else_body is not None:
                self.lower_exception_suite(node.else_body)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.cleanup.emit_active(depth)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.llvm.ir_builder.branch(merge)
        self.services.exit_state.cleanup_stack = list(protected)
        self.services.llvm.ir_builder.position_at_end(dispatch)
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
                matches = self.services.exceptions.exception_call(
                    "matches",
                    [
                        self.services.exceptions.context_value(),
                        self.exception_string(
                            matched_type.class_.qualified_name
                        ),
                    ],
                )
                match = self.services.llvm.ir_builder.or_(
                    match,
                    self.services.llvm.ir_builder.icmp_signed(
                        "!=", matches, ir.Constant(ir.IntType(32), 0)
                    ),
                )
            self.services.llvm.ir_builder.cbranch(match, body, following)
            self.services.llvm.ir_builder.position_at_end(body)
            token = self.services.exceptions.exception_call(
                "handler_enter", [self.services.exceptions.context_value()]
            )

            def leave(token: ir.Value = token) -> None:
                """
                title: Restore the dynamically enclosing handler state.
                parameters:
                  token:
                    type: ir.Value
                """
                self.services.exceptions.exception_call(
                    "handler_leave",
                    [self.services.exceptions.context_value(), token],
                )

            self.services.exit_state.cleanup_stack = [
                *protected,
                CleanupAction(leave, kind=CleanupKind.HANDLER),
            ]
            if resolved.symbol is not None:
                type_ = self.services.types.llvm_type(resolved.binding_type)
                assert type_ is not None
                value = self.services.llvm.ir_builder.bitcast(
                    self.services.exceptions.exception_call(
                        "handled_payload",
                        [self.services.exceptions.context_value()],
                    ),
                    type_,
                )
                slot = self.services.create_entry_block_alloca(
                    resolved.symbol.name, type_
                )
                self.services.llvm.ir_builder.store(value, slot)
                self.services.function_state.named_values[
                    resolved.symbol.symbol_id
                ] = slot
                self.services.class_operation(handler, "retain", value)
                self.services.class_cleanup(
                    handler, slot, resolved.symbol.symbol_id, storage=True
                )
            self.lower_exception_suite(handler.body)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.cleanup.emit_active(depth)
            if not self.services.llvm.ir_builder.block.is_terminated:
                self.services.llvm.ir_builder.branch(merge)
            self.services.exit_state.cleanup_stack = list(protected)
            self.services.llvm.ir_builder.position_at_end(following)
        self.services.exceptions.emit_exception_transfer(node)
        self.services.exit_state.cleanup_stack = initial
        self.services.llvm.ir_builder.position_at_end(merge)
        if not any(
            merge in block.terminator.operands
            for block in function.blocks
            if block.terminator is not None
        ):
            self.services.llvm.ir_builder.unreachable()
