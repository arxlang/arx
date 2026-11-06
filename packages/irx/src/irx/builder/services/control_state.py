"""
title: Function, region, and module lifetimes for control-transfer emission.
summary: >-
  These records contain mutable emission state only. Provider descriptors and
  dispatch catalogs never retain them. A module creates independent cache
  records; function scopes replace region collections and restore enclosing
  state even when emission raises a Python exception.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import (
    FunctionSignature,
    ResolvedExceptionType,
)
from irx.builder.state import (
    CleanupAction,
    ExceptionTarget,
    LoopTargets,
    PendingReturn,
    ResultStackValue,
)
from irx.typecheck import typechecked


@private
@typechecked
@dataclass
class ModuleEmissionState:
    """
    title: >-
      Emitted identities and resolved object representations for one LLVM
      module.
    attributes:
      function_protos:
        type: dict[str, astx.FunctionPrototype]
      llvm_functions_by_symbol_id:
        type: dict[str, ir.Function]
      struct_types:
        type: dict[str, ir.Type]
      llvm_structs_by_qualified_name:
        type: dict[str, ir.IdentifiedStructType]
      emitted_function_bodies:
        type: set[str]
      entry_function_symbol_id:
        type: str | None
      module_display_names:
        type: dict[int, str]
      current_module_display_name:
        type: str | None
    """

    function_protos: dict[str, astx.FunctionPrototype] = field(
        default_factory=dict
    )
    llvm_functions_by_symbol_id: dict[str, ir.Function] = field(
        default_factory=dict
    )
    struct_types: dict[str, ir.Type] = field(default_factory=dict)
    llvm_structs_by_qualified_name: dict[str, ir.IdentifiedStructType] = field(
        default_factory=dict
    )
    emitted_function_bodies: set[str] = field(default_factory=set)
    entry_function_symbol_id: str | None = None
    module_display_names: dict[int, str] = field(default_factory=dict)
    current_module_display_name: str | None = None

    def __post_init__(self) -> None:
        """
        title: Validate each emitted identity and representation cache entry.
        """
        validate_module_emission(
            self.function_protos,
            self.llvm_functions_by_symbol_id,
            self.struct_types,
            self.llvm_structs_by_qualified_name,
            self.emitted_function_bodies,
            self.entry_function_symbol_id,
            self.module_display_names,
            self.current_module_display_name,
        )


@private
@typechecked
def validate_module_emission(
    function_protos: dict[str, astx.FunctionPrototype],
    functions: dict[str, ir.Function],
    structs: dict[str, ir.Type],
    qualified_structs: dict[str, ir.IdentifiedStructType],
    emitted: set[str],
    entry: str | None,
    display_names: dict[int, str],
    current_display_name: str | None,
) -> None:
    """
    title: >-
      Check every constructor collection member before owning module state.
    parameters:
      function_protos:
        type: dict[str, astx.FunctionPrototype]
      functions:
        type: dict[str, ir.Function]
      structs:
        type: dict[str, ir.Type]
      qualified_structs:
        type: dict[str, ir.IdentifiedStructType]
      emitted:
        type: set[str]
      entry:
        type: str | None
      display_names:
        type: dict[int, str]
      current_display_name:
        type: str | None
    """
    del (
        function_protos,
        functions,
        structs,
        qualified_structs,
        emitted,
        entry,
        display_names,
        current_display_name,
    )


@private
@typechecked
@dataclass
class ExitState:
    """
    title: Active generated-function context and its lexical exit regions.
    summary: >-
      Collections are ordered ledgers, not runtime values. Cleanup emission may
      temporarily shorten a ledger so an abrupt exit cannot execute its own
      action twice. Context and result slots belong to the active function.
    attributes:
      cleanup_stack:
        type: list[CleanupAction]
      loop_stack:
        type: list[LoopTargets]
      exception_context:
        type: ir.Value | None
      exception_result_slot:
        type: ir.Value | None
      exception_targets:
        type: list[ExceptionTarget]
      pending_returns:
        type: list[PendingReturn]
      emitting_failure_cleanup:
        type: bool
    """

    cleanup_stack: list[CleanupAction] = field(default_factory=list)
    loop_stack: list[LoopTargets] = field(default_factory=list)
    exception_context: ir.Value | None = None
    exception_result_slot: ir.Value | None = None
    exception_targets: list[ExceptionTarget] = field(default_factory=list)
    pending_returns: list[PendingReturn] = field(default_factory=list)
    emitting_failure_cleanup: bool = False

    def __post_init__(self) -> None:
        """
        title: >-
          Validate every collection item supplied to the generated constructor.
        """
        validate_exit_state(
            self.cleanup_stack,
            self.loop_stack,
            self.exception_context,
            self.exception_result_slot,
            self.exception_targets,
            self.pending_returns,
            self.emitting_failure_cleanup,
        )

    @contextmanager
    def function_scope(
        self,
        context: ir.Value | None = None,
        result_slot: ir.Value | None = None,
    ) -> Iterator[None]:
        """
        title: >-
          Isolate generated function ledgers and restore the enclosing frame.
        summary: >-
          Nested cold helpers and generator functions cannot inherit callers'
          handler targets, pending returns, loops, or cleanup state. Restoring
          the exact original collections preserves lexical identity tests.
        parameters:
          context:
            type: ir.Value | None
          result_slot:
            type: ir.Value | None
        returns:
          type: Iterator[None]
        """
        saved = (
            self.cleanup_stack,
            self.loop_stack,
            self.exception_context,
            self.exception_result_slot,
            self.exception_targets,
            self.pending_returns,
            self.emitting_failure_cleanup,
        )
        self.cleanup_stack = []
        self.loop_stack = []
        self.exception_context = context
        self.exception_result_slot = result_slot
        self.exception_targets = []
        self.pending_returns = []
        self.emitting_failure_cleanup = False
        try:
            yield
        finally:
            (
                self.cleanup_stack,
                self.loop_stack,
                self.exception_context,
                self.exception_result_slot,
                self.exception_targets,
                self.pending_returns,
                self.emitting_failure_cleanup,
            ) = saved


@private
@typechecked
def validate_exit_state(
    cleanup_stack: list[CleanupAction],
    loop_stack: list[LoopTargets],
    exception_context: ir.Value | None,
    exception_result_slot: ir.Value | None,
    exception_targets: list[ExceptionTarget],
    pending_returns: list[PendingReturn],
    emitting_failure_cleanup: bool,
) -> None:
    """
    title: >-
      Check generated ExitState arguments, including all collection members.
    parameters:
      cleanup_stack:
        type: list[CleanupAction]
      loop_stack:
        type: list[LoopTargets]
      exception_context:
        type: ir.Value | None
      exception_result_slot:
        type: ir.Value | None
      exception_targets:
        type: list[ExceptionTarget]
      pending_returns:
        type: list[PendingReturn]
      emitting_failure_cleanup:
        type: bool
    """
    del (
        cleanup_stack,
        loop_stack,
        exception_context,
        exception_result_slot,
        exception_targets,
        pending_returns,
        emitting_failure_cleanup,
    )


@private
@typechecked
@dataclass
class ExceptionModuleState:
    """
    title: >-
      Resolved exception declarations and emitted signatures for one LLVM
      module.
    attributes:
      runtime_exception_types:
        type: dict[str, ResolvedExceptionType]
      llvm_function_signatures:
        type: dict[str, FunctionSignature]
    """

    runtime_exception_types: dict[str, ResolvedExceptionType] = field(
        default_factory=dict
    )
    llvm_function_signatures: dict[str, FunctionSignature] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """
        title: Validate module catalogs without sharing mutable defaults.
        """
        validate_exception_module(
            self.runtime_exception_types, self.llvm_function_signatures
        )


@private
@typechecked
def validate_exception_module(
    types: dict[str, ResolvedExceptionType],
    signatures: dict[str, FunctionSignature],
) -> None:
    """
    title: Validate all nominal exception and function signature entries.
    parameters:
      types:
        type: dict[str, ResolvedExceptionType]
      signatures:
        type: dict[str, FunctionSignature]
    """
    del types, signatures


@private
@typechecked
@dataclass
class GeneratorModuleState:
    """
    title: Frame layouts and resume symbols owned by one LLVM module.
    attributes:
      frame_types:
        type: dict[str, ir.IdentifiedStructType]
      frame_slots_by_symbol_id:
        type: dict[str, dict[str, int]]
      resume_functions:
        type: dict[str, ir.Function]
    """

    frame_types: dict[str, ir.IdentifiedStructType] = field(
        default_factory=dict
    )
    frame_slots_by_symbol_id: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    resume_functions: dict[str, ir.Function] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """
        title: Check nested frame-slot maps and cached LLVM value types.
        """
        validate_generator_module(
            self.frame_types,
            self.frame_slots_by_symbol_id,
            self.resume_functions,
        )


@private
@typechecked
def validate_generator_module(
    frame_types: dict[str, ir.IdentifiedStructType],
    frame_slots: dict[str, dict[str, int]],
    resume_functions: dict[str, ir.Function],
) -> None:
    """
    title: Validate every module cache key and nested collection member.
    parameters:
      frame_types:
        type: dict[str, ir.IdentifiedStructType]
      frame_slots:
        type: dict[str, dict[str, int]]
      resume_functions:
        type: dict[str, ir.Function]
    """
    del frame_types, frame_slots, resume_functions


@private
@typechecked
@dataclass
class GeneratorFrameState:
    """
    title: Active factory/resume frame values, never retained by a descriptor.
    attributes:
      frame_ptr:
        type: ir.Value | None
      frame_slots:
        type: dict[str, int]
      out_ptr:
        type: ir.Value | None
      next_state:
        type: int | None
    """

    frame_ptr: ir.Value | None = None
    frame_slots: dict[str, int] = field(default_factory=dict)
    out_ptr: ir.Value | None = None
    next_state: int | None = None

    def __post_init__(self) -> None:
        """
        title: Validate function-owned values and every frame slot.
        """
        validate_generator_frame(
            self.frame_ptr, self.frame_slots, self.out_ptr, self.next_state
        )

    @contextmanager
    def function_scope(self) -> Iterator[None]:
        """
        title: >-
          Prevent nested function emission from retaining active generator
          slots.
        returns:
          type: Iterator[None]
        """
        saved = (
            self.frame_ptr,
            self.frame_slots,
            self.out_ptr,
            self.next_state,
        )
        self.frame_ptr = None
        self.frame_slots = {}
        self.out_ptr = None
        self.next_state = None
        try:
            yield
        finally:
            self.frame_ptr, self.frame_slots, self.out_ptr, self.next_state = (
                saved
            )


@private
@typechecked
def validate_generator_frame(
    frame_ptr: ir.Value | None,
    frame_slots: dict[str, int],
    out_ptr: ir.Value | None,
    next_state: int | None,
) -> None:
    """
    title: Validate all active generator-frame constructor fields.
    parameters:
      frame_ptr:
        type: ir.Value | None
      frame_slots:
        type: dict[str, int]
      out_ptr:
        type: ir.Value | None
      next_state:
        type: int | None
    """
    del frame_ptr, frame_slots, out_ptr, next_state


@private
@typechecked
@dataclass
class FunctionValueState:
    """
    title: >-
      Function-local bindings, result values, and resolved return contracts.
    attributes:
      return_type:
        type: astx.DataType | None
      signature:
        type: FunctionSignature | None
      named_values:
        type: dict[str, ir.Value]
      const_vars:
        type: set[str]
      result_stack:
        type: list[ResultStackValue]
      class_construction_stack:
        type: list[ir.Value]
    """

    return_type: astx.DataType | None = None
    signature: FunctionSignature | None = None
    named_values: dict[str, ir.Value] = field(default_factory=dict)
    const_vars: set[str] = field(default_factory=set)
    result_stack: list[ResultStackValue] = field(default_factory=list)
    class_construction_stack: list[ir.Value] = field(default_factory=list)

    def __post_init__(self) -> None:
        """
        title: Validate function contracts and every construction receiver.
        """
        validate_function_value_state(
            self.return_type,
            self.signature,
            self.named_values,
            self.const_vars,
            self.result_stack,
            self.class_construction_stack,
        )

    @contextmanager
    def function_scope(self, signature: FunctionSignature) -> Iterator[None]:
        """
        title: Isolate function bindings while retaining visible module values.
        summary: >-
          Each generated body inherits a snapshot of visible module bindings,
          not prior bodies' locals. Result and construction stacks start empty.
          The enclosing records are restored even if nested emission fails.
        parameters:
          signature:
            type: FunctionSignature
        returns:
          type: Iterator[None]
        """
        saved = (
            self.return_type,
            self.signature,
            self.named_values,
            self.const_vars,
            self.result_stack,
            self.class_construction_stack,
        )
        self.return_type = signature.return_type
        self.signature = signature
        self.named_values = self.named_values.copy()
        self.const_vars = self.const_vars.copy()
        self.result_stack = []
        self.class_construction_stack = []
        try:
            yield
        finally:
            (
                self.return_type,
                self.signature,
                self.named_values,
                self.const_vars,
                self.result_stack,
                self.class_construction_stack,
            ) = saved


@private
@typechecked
def validate_function_value_state(
    return_type: astx.DataType | None,
    signature: FunctionSignature | None,
    named_values: dict[str, ir.Value],
    const_vars: set[str],
    result_stack: list[ResultStackValue],
    construction_stack: list[ir.Value],
) -> None:
    """
    title: Validate the typed active-function value contract.
    parameters:
      return_type:
        type: astx.DataType | None
      signature:
        type: FunctionSignature | None
      named_values:
        type: dict[str, ir.Value]
      const_vars:
        type: set[str]
      result_stack:
        type: list[ResultStackValue]
      construction_stack:
        type: list[ir.Value]
    """
    del (
        return_type,
        signature,
        named_values,
        const_vars,
        result_stack,
        construction_stack,
    )
