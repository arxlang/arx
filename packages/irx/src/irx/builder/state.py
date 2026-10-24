"""
title: Shared state typing for llvmlite-based codegen.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from llvmlite import ir

from irx.typecheck import typechecked

ResultStackValue = ir.Value | ir.Function | None
NamedValueMap = dict[str, Any]
CleanupEmitter = Callable[[], None]


@typechecked
class CleanupKind(str, Enum):
    """
    title: Distinguish implicit destruction from explicit finalization.
    """

    RESOURCE = "resource"
    FINALLY = "finally"
    HANDLER = "handler"


@typechecked
@dataclass(frozen=True)
class CleanupAction:
    """
    title: One active cleanup emitter with optional semantic owner identity.
    summary: >-
      Infallible actions neither install a pending exception nor transfer
      control; only audited native free/release operations use that contract.
    attributes:
      emitter:
        type: CleanupEmitter
      owner_symbol_id:
        type: str | None
      kind:
        type: CleanupKind
      fallible:
        type: bool
    """

    emitter: CleanupEmitter
    owner_symbol_id: str | None = None
    kind: CleanupKind = CleanupKind.RESOURCE
    fallible: bool = True


@typechecked
@dataclass(frozen=True)
class ExceptionTarget:
    """
    title: One lexical handler target and the cleanup depth it preserves.
    attributes:
      block:
        type: ir.Block
      cleanup_depth:
        type: int
    """

    block: ir.Block
    cleanup_depth: int


@typechecked
@dataclass(frozen=True)
class LoopTargets:
    """
    title: Canonical break/continue targets for one active loop.
    attributes:
      break_target:
        type: ir.Block
      continue_target:
        type: ir.Block
      cleanup_depth:
        type: int
    """

    break_target: ir.Block
    continue_target: ir.Block
    cleanup_depth: int = 0


@typechecked
@dataclass(frozen=True)
class PendingReturn:
    """
    title: Owned result and lexical boundaries of a suspended return.
    summary: >-
      Restore an affine source binding when cancellation stays inside its
      scope; otherwise release the abandoned result. Nested candidates remain
      independent until an actual return commits.
    attributes:
      actions:
        type: tuple[CleanupEmitter, Ellipsis]
      exception_targets:
        type: tuple[ExceptionTarget, Ellipsis]
      loops:
        type: tuple[LoopTargets, Ellipsis]
      restore_depth:
        type: int | None
    """

    actions: tuple[CleanupEmitter, ...]
    exception_targets: tuple[ExceptionTarget, ...]
    loops: tuple[LoopTargets, ...]
    restore_depth: int | None = None


__all__ = [
    "CleanupAction",
    "CleanupEmitter",
    "CleanupKind",
    "ExceptionTarget",
    "LoopTargets",
    "NamedValueMap",
    "PendingReturn",
    "ResultStackValue",
]
