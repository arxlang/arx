"""
title: Status-ABI calls, pending completion, and checked control transfer.
summary: >-
  All mutable ledgers arrive through the active function's ExitState. This
  service does not traverse ASTs or rediscover call binding, ownership, types,
  or source locations. It consumes resolved signatures and explicit backend
  callbacks, loading result slots only on a successful status edge.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import FunctionSignature
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.services.control_state import ExitState
from irx.builder.state import LoopTargets, PendingReturn
from irx.typecheck import typechecked


@private
@typechecked
class ExceptionService:
    """
    title: >-
      Emit resolved calls and route failures through one lexical exit model.
    summary: >-
      checked_facade selects only trusted resolved native ABI metadata;
      checked_native emits that family's status/output primitive. General calls
      and generated status calls share this entry point without privileging the
      source spelling of a function name.
    attributes:
      state:
        type: ExitState
      builder:
        type: Callable[[], ir.IRBuilder]
      runtime_symbol:
        type: Callable[[str, str], ir.Function]
      location:
        type: Callable[[astx.AST], list[ir.Value]]
      representation:
        type: Callable[[astx.DataType | None], ir.Type | None]
      output_slot:
        type: Callable[[str, ir.Type], ir.Value]
      checked_facade:
        type: Callable[[FunctionSignature], bool]
      checked_native:
        type: Callable[[astx.AST, ir.Function, list[ir.Value]], ir.Value]
      emit_cleanups:
        type: Callable[[int], None]
    """

    state: ExitState
    builder: Callable[[], ir.IRBuilder]
    runtime_symbol: Callable[[str, str], ir.Function]
    location: Callable[[astx.AST], list[ir.Value]]
    representation: Callable[[astx.DataType | None], ir.Type | None]
    output_slot: Callable[[str, ir.Type], ir.Value]
    checked_facade: Callable[[FunctionSignature], bool]
    checked_native: Callable[[astx.AST, ir.Function, list[ir.Value]], ir.Value]
    emit_cleanups: Callable[[int], None]

    def __init__(
        self,
        state: ExitState,
        builder: Callable[[], ir.IRBuilder],
        runtime_symbol: Callable[[str, str], ir.Function],
        location: Callable[[astx.AST], list[ir.Value]],
        representation: Callable[[astx.DataType | None], ir.Type | None],
        output_slot: Callable[[str, ir.Type], ir.Value],
        checked_facade: Callable[[FunctionSignature], bool],
        checked_native: Callable[
            [astx.AST, ir.Function, list[ir.Value]], ir.Value
        ],
        emit_cleanups: Callable[[int], None],
    ) -> None:
        """
        title: >-
          Bind only the emission and resolved-ABI services required by control
          transfer.
        parameters:
          state:
            type: ExitState
          builder:
            type: Callable[[], ir.IRBuilder]
          runtime_symbol:
            type: Callable[[str, str], ir.Function]
          location:
            type: Callable[[astx.AST], list[ir.Value]]
          representation:
            type: Callable[[astx.DataType | None], ir.Type | None]
          output_slot:
            type: Callable[[str, ir.Type], ir.Value]
          checked_facade:
            type: Callable[[FunctionSignature], bool]
          checked_native:
            type: Callable[[astx.AST, ir.Function, list[ir.Value]], ir.Value]
          emit_cleanups:
            type: Callable[[int], None]
        """
        self.state = state
        self.builder = builder
        self.runtime_symbol = runtime_symbol
        self.location = location
        self.representation = representation
        self.output_slot = output_slot
        self.checked_facade = checked_facade
        self.checked_native = checked_native
        self.emit_cleanups = emit_cleanups

    def exception_call(self, operation: str, args: list[ir.Value]) -> ir.Value:
        """
        title: Call a registered opaque exception-runtime primitive.
        parameters:
          operation:
            type: str
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        function = self.runtime_symbol(
            "exceptions", "irx_exception_" + operation
        )
        return self.builder().call(function, args)

    def context_value(self) -> ir.Value:
        """
        title: Require the execution context of the active generated frame.
        returns:
          type: ir.Value
        """
        context = self.state.exception_context
        if context is None:
            raise_lowering_internal_error(
                "exception emission requires an active execution context"
            )
        return context

    def emit_resolved_call(
        self,
        node: astx.AST,
        callee: ir.Value,
        signature: FunctionSignature,
        args: list[ir.Value],
    ) -> ir.Value | None:
        """
        title: >-
          Read generated/native output storage only after successful
          completion.
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
            if self.checked_facade(signature):
                if not isinstance(callee, ir.Function):
                    raise_lowering_internal_error(
                        "checked native facades require "
                        "a resolved direct function",
                        node=node,
                    )
                value = self.checked_native(node, callee, args)
                return (
                    None
                    if isinstance(signature.return_type, astx.NoneType)
                    else value
                )
            value = self.builder().call(callee, args)
            return None if isinstance(value.type, ir.VoidType) else value
        result_type = self.representation(signature.return_type)
        if result_type is None:
            raise_lowering_internal_error(
                "resolved call result has no LLVM representation", node=node
            )
        output = None
        operands = [self.context_value(), *args]
        if not isinstance(result_type, ir.VoidType):
            output = self.output_slot("call.result", result_type)
            operands.append(output)
        status = self.builder().call(callee, operands, "call.status")
        self.propagate_status(node, status)
        return None if output is None else self.builder().load(output)

    def propagate_status(self, node: astx.AST, status: ir.Value) -> None:
        """
        title: >-
          Propagate a failed call through the active lexical cleanup regions.
        parameters:
          node:
            type: astx.AST
          status:
            type: ir.Value
        """
        builder = self.builder()
        function = builder.function
        success = function.append_basic_block("call.success")
        failure = function.append_basic_block("call.failure")
        builder.cbranch(
            builder.icmp_signed("==", status, ir.Constant(status.type, 0)),
            success,
            failure,
        )
        builder.position_at_end(failure)
        self.exception_call(
            "trace", [self.context_value(), *self.location(node)]
        )
        self.emit_exception_transfer(node)
        builder.position_at_end(success)

    def abandon_pending_returns(
        self,
        completions: tuple[PendingReturn, ...] | None = None,
        *,
        preserved_depth: int | None = None,
    ) -> None:
        """
        title: >-
          Release only suspended results replaced by the current control
          transfer.
        parameters:
          completions:
            type: tuple[PendingReturn, Ellipsis] | None
          preserved_depth:
            type: int | None
        """
        saved = self.state.pending_returns
        selected = tuple(saved) if completions is None else completions
        self.state.pending_returns = [
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
            self.state.pending_returns = saved

    def abandon_loop_returns(self, target: LoopTargets) -> None:
        """
        title: Replace only suspended returns outside a loop's local regions.
        parameters:
          target:
            type: LoopTargets
        """
        self.abandon_pending_returns(
            tuple(
                completion
                for completion in self.state.pending_returns
                if any(target is loop for loop in completion.loops)
            ),
            preserved_depth=target.cleanup_depth,
        )

    def propagate_pending_exception(self) -> None:
        """
        title: Stop normal cleanup at the nearest still-active handler.
        """
        pending = self.exception_call("pending", [self.context_value()])
        builder = self.builder()
        with builder.if_then(
            builder.icmp_signed("!=", pending, ir.Constant(ir.IntType(32), 0))
        ):
            self.emit_exception_transfer(None)

    def emit_exception_transfer(self, node: astx.AST | None) -> None:
        """
        title: Unwind lexical cleanup without crossing native stack frames.
        parameters:
          node:
            type: astx.AST | None
        """
        target = next(
            (
                item
                for item in reversed(self.state.exception_targets)
                if item.cleanup_depth <= len(self.state.cleanup_stack)
            ),
            None,
        )
        self.abandon_pending_returns(
            tuple(
                completion
                for completion in self.state.pending_returns
                if target is None
                or any(target is item for item in completion.exception_targets)
            ),
            preserved_depth=None if target is None else target.cleanup_depth,
        )
        previous = self.state.emitting_failure_cleanup
        self.state.emitting_failure_cleanup = True
        try:
            self.emit_cleanups(0 if target is None else target.cleanup_depth)
        finally:
            self.state.emitting_failure_cleanup = previous
        builder = self.builder()
        if builder.block.is_terminated:
            return
        if target is not None:
            builder.branch(target.block)
        else:
            builder.ret(ir.Constant(ir.IntType(32), 1))

    def emit_success_return(self, value: ir.Value | None) -> None:
        """
        title: >-
          Publish a result only after the caller has completed every exit
          region.
        parameters:
          value:
            type: ir.Value | None
        """
        builder = self.builder()
        if self.state.exception_context is None:
            if value is None:
                builder.ret_void()
            else:
                builder.ret(value)
            return
        if value is not None:
            slot = self.state.exception_result_slot
            if slot is None:
                raise_lowering_internal_error(
                    "non-void status return requires an output slot"
                )
            builder.store(value, slot)
        builder.ret(ir.Constant(ir.IntType(32), 0))


@private
@runtime_checkable
class RaiseRuntimeException(Protocol):
    """
    title: Typed runtime-failure delivery without exposing a compiler owner.
    """

    def __call__(
        self, node: astx.AST, role: str, message: ir.Value, *, code: str
    ) -> None:
        """
        title: Raise a resolved builtin exception and transfer control.
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
        del node, role, message, code
        raise NotImplementedError


@private
@typechecked
class RuntimeGuardService:
    """
    title: >-
      Checked branch emission shared by allocation, arithmetic, and native
      callers.
    attributes:
      builder:
        type: Callable[[], ir.IRBuilder]
      text:
        type: Callable[[str], ir.Value]
      raise_exception:
        type: RaiseRuntimeException
    """

    builder: Callable[[], ir.IRBuilder]
    text: Callable[[str], ir.Value]
    raise_exception: RaiseRuntimeException

    def __init__(
        self,
        builder: Callable[[], ir.IRBuilder],
        text: Callable[[str], ir.Value],
        raise_exception: RaiseRuntimeException,
    ) -> None:
        """
        title: >-
          Inject only the active builder, diagnostic strings, and exception
          delivery.
        parameters:
          builder:
            type: Callable[[], ir.IRBuilder]
          text:
            type: Callable[[str], ir.Value]
          raise_exception:
            type: RaiseRuntimeException
        """
        self.builder = builder
        self.text = text
        self.raise_exception = raise_exception

    def guard(
        self,
        node: astx.AST,
        condition: ir.Value,
        *,
        code: str,
        message: str,
        block_name: str,
        exception_role: str = "RuntimeError",
    ) -> None:
        """
        title: >-
          Enter a successful continuation only when a checked runtime condition
          holds.
        parameters:
          node:
            type: astx.AST
          condition:
            type: ir.Value
          code:
            type: str
          message:
            type: str
          block_name:
            type: str
          exception_role:
            type: str
        """
        builder = self.builder()
        function = builder.function
        fail_block = function.append_basic_block(f"{block_name}.fail")
        pass_block = function.append_basic_block(f"{block_name}.pass")
        builder.cbranch(condition, pass_block, fail_block)
        builder.position_at_start(fail_block)
        self.raise_exception(
            node, exception_role, self.text(message), code=code
        )
        builder.position_at_start(pass_block)
