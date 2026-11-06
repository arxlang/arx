"""
title: Explicit ordered cleanup emission through lexical exit ledgers.
summary: >-
  A cleanup is removed from the active prefix before its emitter executes.
  Failure and replacement transfers therefore see only still-active regions.
  Services depend on a builder getter, typed exception callbacks, and state,
  not a compiler visitor or a universal service locator.
"""

from __future__ import annotations

from collections.abc import Callable

import astx

from llvmlite import ir
from public import private

from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
)
from irx.builder.diagnostics import raise_lowering_internal_error
from irx.builder.services.control_state import ExitState, GeneratorFrameState
from irx.builder.state import CleanupAction, CleanupKind, ExceptionTarget
from irx.builtins.collections.list import (
    LIST_DESTROY_SYMBOL,
    LIST_RUNTIME_FEATURE,
)
from irx.typecheck import typechecked


@private
@typechecked
class CleanupService:
    """
    title: One route for success, failure, and abrupt-completion cleanup.
    summary: >-
      Runtime callbacks are supplied explicitly during composition. They must
      emit into the same active builder and share this ExitState. Native
      releases use registered symbols; publication and ownership facts remain
      analysis/feature responsibilities.
    attributes:
      state:
        type: ExitState
      frame:
        type: GeneratorFrameState
      builder:
        type: Callable[[], ir.IRBuilder]
      runtime_symbol:
        type: Callable[[str, str], ir.Function]
      exception_call:
        type: Callable[[str, list[ir.Value]], ir.Value]
      propagate_pending_exception:
        type: Callable[[], None]
    """

    state: ExitState
    frame: GeneratorFrameState
    builder: Callable[[], ir.IRBuilder]
    runtime_symbol: Callable[[str, str], ir.Function]
    exception_call: Callable[[str, list[ir.Value]], ir.Value]
    propagate_pending_exception: Callable[[], None]

    def __init__(
        self,
        state: ExitState,
        frame: GeneratorFrameState,
        builder: Callable[[], ir.IRBuilder],
        runtime_symbol: Callable[[str, str], ir.Function],
        exception_call: Callable[[str, list[ir.Value]], ir.Value],
        propagate_pending_exception: Callable[[], None],
    ) -> None:
        """
        title: Bind only the state and callbacks required by cleanup emission.
        parameters:
          state:
            type: ExitState
          frame:
            type: GeneratorFrameState
          builder:
            type: Callable[[], ir.IRBuilder]
          runtime_symbol:
            type: Callable[[str, str], ir.Function]
          exception_call:
            type: Callable[[str, list[ir.Value]], ir.Value]
          propagate_pending_exception:
            type: Callable[[], None]
        """
        self.state = state
        self.frame = frame
        self.builder = builder
        self.runtime_symbol = runtime_symbol
        self.exception_call = exception_call
        self.propagate_pending_exception = propagate_pending_exception

    def emit_active(
        self,
        start_depth: int = 0,
        excluded_owner_symbol_ids: frozenset[str] = frozenset(),
    ) -> None:
        """
        title: >-
          Emit active actions in reverse lexical order without executing one
          twice.
        parameters:
          start_depth:
            type: int
          excluded_owner_symbol_ids:
            type: frozenset[str]
        """
        if start_depth < 0:
            raise_lowering_internal_error("cleanup depth cannot be negative")
        original = self.state.cleanup_stack
        try:
            for index in reversed(range(start_depth, len(original))):
                if self.builder().block.is_terminated:
                    break
                cleanup = original[index]
                self.state.cleanup_stack = original[:index]
                if cleanup.owner_symbol_id in excluded_owner_symbol_ids:
                    continue
                if (
                    cleanup.kind is CleanupKind.RESOURCE
                    and cleanup.fallible
                    and self.state.exception_context is not None
                ):
                    token = self.exception_call(
                        "cleanup_enter", [self.state.exception_context]
                    )
                    done = self.builder().function.append_basic_block(
                        "cleanup.done"
                    )
                    self.state.exception_targets.append(
                        ExceptionTarget(done, len(self.state.cleanup_stack))
                    )
                    previous_pending = self.state.pending_returns
                    self.state.pending_returns = []
                    try:
                        cleanup.emitter()
                    finally:
                        self.state.pending_returns = previous_pending
                        self.state.exception_targets.pop()
                    if not self.builder().block.is_terminated:
                        self.builder().branch(done)
                    self.builder().position_at_end(done)
                    self.exception_call(
                        "cleanup_leave", [self.state.exception_context, token]
                    )
                else:
                    cleanup.emitter()
                if (
                    cleanup.fallible
                    and self.state.exception_context is not None
                    and not self.state.emitting_failure_cleanup
                    and not self.builder().block.is_terminated
                ):
                    self.propagate_pending_exception()
        finally:
            self.state.cleanup_stack = original

    def emit_temporary(self, start_depth: int) -> None:
        """
        title: >-
          Emit and discharge temporaries while retaining named resource owners.
        parameters:
          start_depth:
            type: int
        """
        if start_depth < 0:
            raise_lowering_internal_error(
                "temporary cleanup depth cannot be negative"
            )
        new_actions = self.state.cleanup_stack[start_depth:]
        retained = [
            item for item in new_actions if item.owner_symbol_id is not None
        ]
        temporaries = [
            item for item in new_actions if item.owner_symbol_id is None
        ]
        self.state.cleanup_stack[start_depth:] = [*retained, *temporaries]
        self.emit_active(start_depth + len(retained))
        self.state.cleanup_stack[start_depth:] = retained

    def register_owned_list_temporary(
        self, node: astx.AST, pointer: ir.Value
    ) -> None:
        """
        title: >-
          Register one non-transferred owned list through its analysis facts.
        parameters:
          node:
            type: astx.AST
          pointer:
            type: ir.Value
        """
        self.register_owned_temporary(
            node,
            pointer,
            ResourceKind.LIST,
            LIST_RUNTIME_FEATURE,
            LIST_DESTROY_SYMBOL,
        )

    def register_owned_string_temporary(
        self, node: astx.AST, pointer: ir.Value
    ) -> None:
        """
        title: >-
          Register one non-transferred malloc-owned string through its analysis
          facts.
        parameters:
          node:
            type: astx.AST
          pointer:
            type: ir.Value
        """
        self.register_owned_temporary(
            node, pointer, ResourceKind.STRING, "libc", "free"
        )

    def register_owned_temporary(
        self,
        node: astx.AST,
        pointer: ir.Value,
        kind: ResourceKind,
        feature: str,
        destroy: str,
    ) -> None:
        """
        title: >-
          Track a supported temporary without changing transfer or escape
          policy.
        summary: >-
          This reads resolved ownership, never infers ownership from runtime
          representation. Owned generator temporaries still require a future
          lifecycle contract and are rejected with an internal diagnostic.
        parameters:
          node:
            type: astx.AST
          pointer:
            type: ir.Value
          kind:
            type: ResourceKind
          feature:
            type: str
          destroy:
            type: str
        """
        ownership = resource_ownership(node)
        if (
            ownership is None
            or ownership.resource_kind is not kind
            or ownership.kind is not OwnershipKind.OWNED
        ):
            return
        if (
            ownership.transfer_kind is OwnershipTransferKind.MOVE
            or ownership.escape_kind is OwnershipEscapeKind.RETURN
        ):
            return
        if self.frame.frame_ptr is not None:
            raise_lowering_internal_error(
                f"owned {kind.value} temporaries in generator frames require "
                "generator lifecycle cleanup",
                node=node,
            )
        release = self.runtime_symbol(feature, destroy)

        def emit_release() -> None:
            """
            title: >-
              Release the captured storage in the active generated function.
            """
            self.builder().call(release, [pointer])

        self.state.cleanup_stack.append(
            CleanupAction(emit_release, fallible=False)
        )
