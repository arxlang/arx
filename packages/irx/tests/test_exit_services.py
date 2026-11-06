"""
title: >-
  Exit-state lifetimes, cleanup ordering, and success-only ABI publication.
summary: No native build is needed for the emission-service contracts.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx
import pytest

from irx.analysis.resolved_nodes import CallingConvention, FunctionSignature
from irx.builder.services.cleanup import CleanupService
from irx.builder.services.control_state import (
    ExceptionModuleState,
    ExitState,
    FunctionValueState,
    GeneratorFrameState,
    GeneratorModuleState,
)
from irx.builder.services.exceptions import (
    ExceptionService,
    RuntimeGuardService,
)
from irx.builder.state import CleanupAction, ExceptionTarget, PendingReturn
from llvmlite import binding as llvm
from llvmlite import ir
from public import private
from typeguard import TypeCheckError

OUTER_RESUME_STATE = 4


@private
@dataclass
class Emission:
    """
    title: Isolated LLVM module, active builder, and call recording fixture.
    attributes:
      module:
        type: ir.Module
      builder:
        type: ir.IRBuilder
      calls:
        type: list[str]
    """

    module: ir.Module
    builder: ir.IRBuilder
    calls: list[str]

    def runtime_symbol(self, feature: str, name: str) -> ir.Function:
        """
        title: >-
          Supply test runtime declarations without activating native artifacts.
        parameters:
          feature:
            type: str
          name:
            type: str
        returns:
          type: ir.Function
        """
        assert feature in {"exceptions", "errors", "libc"}
        pointer = ir.IntType(8).as_pointer()
        types = {
            "irx_exception_cleanup_enter": [pointer],
            "irx_exception_cleanup_leave": [pointer, ir.IntType(32)],
            "irx_exception_pending": [pointer],
            "irx_exception_trace": [
                pointer,
                pointer,
                ir.IntType(32),
                ir.IntType(32),
            ],
            "free": [pointer],
        }
        existing = self.module.globals.get(name)
        if isinstance(existing, ir.Function):
            return existing
        return ir.Function(
            self.module,
            ir.FunctionType(ir.IntType(32), types[name]),
            name,
        )

    def exception_call(
        self, operation: str, arguments: list[ir.Value]
    ) -> ir.Value:
        """
        title: Record which cleanup runtime region was entered or left.
        parameters:
          operation:
            type: str
          arguments:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        self.calls.append(operation)
        return self.builder.call(
            self.runtime_symbol("exceptions", "irx_exception_" + operation),
            arguments,
        )


@pytest.fixture
def emission() -> Emission:
    """
    title: Create fresh mutable state for each cleanup-emission contract.
    returns:
      type: Emission
    """
    module = ir.Module()
    function = ir.Function(module, ir.FunctionType(ir.VoidType(), []), "test")
    builder = ir.IRBuilder(function.append_basic_block("entry"))
    return Emission(module, builder, [])


def cleanup_service(state: ExitState, emission: Emission) -> CleanupService:
    """
    title: Compose the service with explicit dependencies used by this fixture.
    parameters:
      state:
        type: ExitState
      emission:
        type: Emission
    returns:
      type: CleanupService
    """
    return CleanupService(
        state,
        GeneratorFrameState(),
        lambda: emission.builder,
        emission.runtime_symbol,
        emission.exception_call,
        lambda: emission.calls.append("propagate"),
    )


def exception_service(
    state: ExitState, emission: Emission
) -> ExceptionService:
    """
    title: Bind only explicit call and status-emission dependencies.
    parameters:
      state:
        type: ExitState
      emission:
        type: Emission
    returns:
      type: ExceptionService
    """
    pointer = ir.IntType(8).as_pointer()
    integer = ir.IntType(32)

    def checked_native(
        node: astx.AST, function: ir.Function, arguments: list[ir.Value]
    ) -> ir.Value:
        """
        title: The fixture has no checked native facade to invoke.
        parameters:
          node:
            type: astx.AST
          function:
            type: ir.Function
          arguments:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        del node, function, arguments
        raise AssertionError("unexpected checked native call")

    def slot(name: str, type_: ir.Type) -> ir.Value:
        """
        title: Allocate the fixture's caller-owned result slot.
        parameters:
          name:
            type: str
          type_:
            type: ir.Type
        returns:
          type: ir.Value
        """
        return emission.builder.alloca(type_, name=name)

    return ExceptionService(
        state,
        lambda: emission.builder,
        emission.runtime_symbol,
        lambda node: [
            ir.Constant(pointer, None),
            ir.Constant(integer, 1),
            ir.Constant(integer, 1),
        ],
        lambda type_: integer,
        slot,
        lambda signature: False,
        checked_native,
        lambda depth: emission.calls.append("cleanup"),
    )


def test_cleanup_prefix_prevents_recursive_reexecution(
    emission: Emission,
) -> None:
    """
    title: Abrupt nested cleanup sees only actions not already being executed.
    parameters:
      emission:
        type: Emission
    """
    state = ExitState()
    service = cleanup_service(state, emission)
    events: list[str] = []

    def outer() -> None:
        """
        title: Record the outermost cleanup action.
        """
        events.append("outer")

    def inner() -> None:
        """
        title: Transfer from cleanup without executing this action again.
        """
        events.append("inner")
        assert len(state.cleanup_stack) == 1
        service.emit_active()
        emission.builder.ret_void()

    original = [
        CleanupAction(outer, fallible=False),
        CleanupAction(inner, fallible=False),
    ]
    state.cleanup_stack = original
    service.emit_active()
    assert events == ["inner", "outer"]
    assert state.cleanup_stack is original
    llvm.parse_assembly(str(emission.module)).verify()


def test_temporary_cleanup_keeps_named_owners(emission: Emission) -> None:
    """
    title: >-
      Expression temporaries drop in reverse order without consuming named
      owners.
    parameters:
      emission:
        type: Emission
    """
    state = ExitState()
    service = cleanup_service(state, emission)
    events: list[str] = []
    owner = CleanupAction(
        lambda: events.append("owner"), "symbol", fallible=False
    )
    state.cleanup_stack = [
        CleanupAction(lambda: events.append("first"), fallible=False),
        owner,
        CleanupAction(lambda: events.append("last"), fallible=False),
    ]
    service.emit_temporary(0)
    assert events == ["last", "first"]
    assert state.cleanup_stack == [owner]
    service.emit_active(excluded_owner_symbol_ids=frozenset({"symbol"}))
    assert events == ["last", "first"]
    emission.builder.ret_void()
    llvm.parse_assembly(str(emission.module)).verify()


def test_fallible_cleanup_isolates_pending_return(emission: Emission) -> None:
    """
    title: >-
      Resource cleanup gets its own exception target and cannot abandon a
      pending result.
    parameters:
      emission:
        type: Emission
    """
    pointer = ir.Constant(ir.IntType(8).as_pointer(), None)
    completion = PendingReturn((), (), ())
    state = ExitState(exception_context=pointer, pending_returns=[completion])
    service = cleanup_service(state, emission)

    def destroy() -> None:
        """
        title: Observe the nested runtime cleanup region without modifying it.
        """
        assert state.pending_returns == []
        assert len(state.exception_targets) == 1
        assert state.exception_targets[0].cleanup_depth == 0

    state.cleanup_stack.append(CleanupAction(destroy))
    service.emit_active()
    assert state.pending_returns == [completion]
    assert state.exception_targets == []
    assert emission.calls == ["cleanup_enter", "cleanup_leave", "propagate"]
    emission.builder.ret_void()
    llvm.parse_assembly(str(emission.module)).verify()


def test_emission_failure_restores_cleanup_ledger(emission: Emission) -> None:
    """
    title: >-
      A failed Python emission attempt does not retain a shortened cleanup
      prefix.
    parameters:
      emission:
        type: Emission
    """
    state = ExitState()
    service = cleanup_service(state, emission)

    def fail() -> None:
        """
        title: Simulate a compiler error while emitting an action.
        """
        raise RuntimeError("emission failed")

    original = [CleanupAction(fail, fallible=False)]
    state.cleanup_stack = original
    with pytest.raises(RuntimeError, match="emission failed"):
        service.emit_active()
    assert state.cleanup_stack is original


def test_function_and_generator_state_restore_after_failure() -> None:
    """
    title: >-
      Nested function emission restores exact outer state after an exception.
    """
    outer = PendingReturn((), (), ())
    state = ExitState(pending_returns=[outer], emitting_failure_cleanup=True)
    pending = state.pending_returns
    frame = GeneratorFrameState(
        frame_slots={"outer": 1}, next_state=OUTER_RESUME_STATE
    )
    slots = frame.frame_slots
    visible = ir.Constant(ir.IntType(32), 7)
    values = FunctionValueState(
        named_values={"global": visible}, result_stack=[visible]
    )
    bindings = values.named_values
    results = values.result_stack
    signature = FunctionSignature(
        "inner", (), astx.Int32(), CallingConvention.IRX_DEFAULT
    )
    with pytest.raises(RuntimeError, match="cancel"):
        with (
            state.function_scope(),
            frame.function_scope(),
            values.function_scope(signature),
        ):
            assert not state.pending_returns
            assert not state.emitting_failure_cleanup
            assert frame.frame_slots == {}
            assert frame.next_state is None
            assert values.signature is signature
            assert values.named_values == {"global": visible}
            assert values.named_values is not bindings
            assert values.result_stack == []
            values.named_values["local"] = visible
            values.result_stack.append(visible)
            state.pending_returns.append(PendingReturn((), (), ()))
            frame.frame_slots["inner"] = 2
            raise RuntimeError("cancel")
    assert state.pending_returns is pending
    assert state.pending_returns == [outer]
    assert state.emitting_failure_cleanup
    assert frame.frame_slots is slots
    assert frame.next_state == OUTER_RESUME_STATE
    assert values.signature is None
    assert values.named_values is bindings
    assert values.named_values == {"global": visible}
    assert values.result_stack is results
    assert values.result_stack == [visible]
    assert GeneratorModuleState().frame_slots_by_symbol_id == {}
    assert ExceptionModuleState().runtime_exception_types == {}


def test_state_constructors_validate_every_collection_item() -> None:
    """
    title: >-
      Invalid non-first items never enter a module or function state record.
    """
    with pytest.raises(TypeCheckError):
        ExitState(pending_returns=[PendingReturn((), (), ()), object()])  # type: ignore[list-item]
    with pytest.raises(TypeCheckError):
        GeneratorModuleState(
            frame_slots_by_symbol_id={"frame": {"good": 0, "bad": "slot"}}
        )  # type: ignore[dict-item]


def test_resolved_call_loads_result_only_on_success(
    emission: Emission,
) -> None:
    """
    title: >-
      Failed generated calls transfer before caller output storage is read.
    parameters:
      emission:
        type: Emission
    """
    pointer = ir.IntType(8).as_pointer()
    integer = ir.IntType(32)
    failure = emission.builder.function.append_basic_block("failed")
    state = ExitState(
        exception_context=ir.Constant(pointer, None),
        exception_targets=[ExceptionTarget(failure, 0)],
    )
    service = exception_service(state, emission)
    callee = ir.Function(
        emission.module,
        ir.FunctionType(integer, [pointer, integer.as_pointer()]),
        "callee",
    )
    signature = FunctionSignature(
        "callee", (), astx.Int32(), CallingConvention.IRX_DEFAULT
    )
    result = service.emit_resolved_call(
        astx.LiteralInt32(0), callee, signature, []
    )
    assert isinstance(result, ir.LoadInstr)
    assert result.parent.name == "call.success"
    failed_call = next(
        block
        for block in emission.builder.function.blocks
        if block.name == "call.failure"
    )
    assert not any(
        isinstance(instruction, ir.LoadInstr)
        for instruction in failed_call.instructions
    )
    assert emission.calls == ["cleanup"]
    emission.builder.ret_void()
    emission.builder.position_at_end(failure)
    emission.builder.ret_void()
    llvm.parse_assembly(str(emission.module)).verify()


def test_pending_return_cancellation_preserves_enclosing_region(
    emission: Emission,
) -> None:
    """
    title: >-
      Local transfer preserves a suspended outer return and cancels only
      selected results.
    parameters:
      emission:
        type: Emission
    """
    released: list[str] = []
    outer = PendingReturn(
        (lambda: released.append("outer"),), (), (), restore_depth=0
    )
    inner = PendingReturn(
        (lambda: released.append("inner"),), (), (), restore_depth=2
    )
    state = ExitState(pending_returns=[outer, inner])
    original = state.pending_returns
    service = exception_service(state, emission)
    service.abandon_pending_returns((outer, inner), preserved_depth=1)
    assert released == ["inner"]
    assert state.pending_returns is original
    service.abandon_pending_returns((outer,))
    assert released == ["inner", "outer"]


def test_guard_failure_block_terminates_before_success(
    emission: Emission,
) -> None:
    """
    title: >-
      Guards keep failure instructions separate from the successful
      continuation.
    parameters:
      emission:
        type: Emission
    """
    calls: list[tuple[str, str]] = []

    def text(value: str) -> ir.Value:
        """
        title: Supply diagnostic storage without a native string runtime.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        assert value == "allocation failed"
        return ir.Constant(ir.IntType(8).as_pointer(), None)

    def raise_exception(
        node: astx.AST, role: str, message: ir.Value, *, code: str
    ) -> None:
        """
        title: Simulate exception delivery as a terminating generated path.
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
        del node, message
        calls.append((role, code))
        emission.builder.unreachable()

    guards = RuntimeGuardService(
        lambda: emission.builder, text, raise_exception
    )
    guards.guard(
        astx.LiteralInt32(1),
        ir.Constant(ir.IntType(1), 1),
        code="TEST-001",
        message="allocation failed",
        block_name="allocation",
    )
    assert calls == [("RuntimeError", "TEST-001")]
    assert emission.builder.block.name == "allocation.pass"
    emission.builder.ret_void()
    llvm.parse_assembly(str(emission.module)).verify()
