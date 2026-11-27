"""
title: Bridge existing LLVM services to the narrow call-plan interface.
summary: This adapter contains no operation selection or algorithms. It is
  constructed by the concrete visitor and never imported by semantic analysis.
"""

import astx

from llvmlite import ir
from public import private

from irx.analysis.compute import ComputePlan
from irx.analysis.memory import ClassHandlePlan
from irx.analysis.resolved_nodes import (
    ResolvedClassConstruction,
    ResolvedMethodCall,
)
from irx.builder.backend import Visitor
from irx.builder.diagnostics import require_lowered_value
from irx.builder.runtime import safe_pop
from irx.builder.state import CleanupAction
from irx.typecheck import typechecked


@private
@typechecked
class VisitorCallServices:
    """
    title: Per-visitor service bindings with explicit compilation lifetime.
    attributes:
      owner: Owner keeping the resource alive.
      builder: Builder generating the intermediate representation.
    """

    owner: Visitor

    def __init__(self, owner: Visitor) -> None:
        """
        title: Bind one compiler instance for resolved call emission.
        parameters:
          owner: Owner keeping the resource alive.
        """
        self.owner = owner

    @property
    def builder(self) -> ir.IRBuilder:
        """
        title: Return the active instruction builder.
        returns: The active instruction builder.
        """
        return self.owner._llvm.ir_builder

    def text(self, value: str) -> ir.Value:
        """
        title: Reuse module-local string interning.
        parameters:
          value: Value to process.
        returns: 'Result of this operation: reuse module-local string
          interning.'
        """
        return self.owner._constant_c_string_pointer(
            value, name_hint="table_io"
        )

    def evaluate(self, node: astx.AST) -> ir.Value:
        """
        title: Evaluate and pin one argument without leaking stack entries.
        parameters:
          node: Syntax node to process.
        returns: 'Result of this operation: evaluate and pin one argument
          without leaking stack entries.'
        """
        self.owner.visit(node)
        value = require_lowered_value(
            safe_pop(self.owner.result_stack),
            node=node,
            context="resolved call argument",
        )
        self.owner.class_pin(node, value)
        return value

    def handle(self, node: astx.AST, value: ir.Value, index: int) -> ir.Value:
        """
        title: Load a resolved opaque-handle field after a lifetime check.
        parameters:
          node: Syntax node to process.
          value: Value to process.
          index: Index selecting the item.
        returns: Loaded a resolved opaque-handle field after a lifetime check.
        """
        self.owner.class_operation(node, "require", value)
        integer = ir.IntType(32)
        return self.builder.load(
            self.builder.gep(
                value, [ir.Constant(integer, 0), ir.Constant(integer, index)]
            )
        )

    def convert(
        self, node: astx.AST, value: ir.Value, target: astx.DataType
    ) -> ir.Value:
        """
        title: Reuse conversion emission with the operand's resolved type.
        parameters:
          node: Syntax node to process.
          value: Value to process.
          target: Destination of the operation.
        returns: 'Result of this operation: reuse conversion emission with
          the operand''s resolved type.'
        """
        return self.owner._cast_ast_value(
            value,
            source_type=self.owner._resolved_ast_type(node),
            target_type=target,
        )

    def invoke(
        self, node: astx.AST, feature: str, name: str, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: Reuse checked status/output ABI and registered runtime
          activation.
        parameters:
          node: Syntax node to process.
          feature: Feature.
          name: Name identifying the declaration or operation.
          args: Arguments supplied to the operation.
        returns: 'Result of this operation: reuse checked status/output
          ABI and registered runtime activation.'
        """
        return self.owner.checked_native_call(
            node, self.owner.require_runtime_symbol(feature, name), args
        )

    def compute(self, node: astx.AST, plan: ComputePlan) -> None:
        """
        title: Reuse typed scalar transport and Arrow ownership emission.
        parameters:
          node: Syntax node to process.
          plan: Resolved semantic execution plan.
        """
        self.owner.lower_compute(node, plan)

    def copy_list(self, node: astx.AST, source: astx.DataType) -> None:
        """
        title: Reuse the checked native list copy and rollback implementation.
        parameters:
          node: Copy call to lower.
          source: Resolved dynamic list operand.
        """
        self.owner.lower_list_clone(node, source)

    def copy_class(
        self, node: astx.AST, source: astx.DataType, method: ResolvedMethodCall
    ) -> None:
        """
        title: Reuse resolved instance dispatch and class result cleanup.
        parameters:
          node: Copy call to lower.
          source: Resolved receiver expression.
          method: Bound copy hook.
        """
        self.owner.lower_class_copy(node, source, method)

    def convert_class_handle(
        self, node: astx.AST, plan: ClassHandlePlan
    ) -> None:
        """
        title: Delegate a checked class handle conversion to the LLVM visitor.
        parameters:
          node: Memory call to lower.
          plan: Resolved reference conversion.
        """
        self.owner.lower_class_handle(node, plan)

    def track(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Register existing native cleanup behavior.
        parameters:
          node: Syntax node to process.
          feature: Feature.
          destroy: Destroy.
          value: Value to process.
        returns: 'Result of this operation: register existing native cleanup
          behavior.'
        """
        return self.owner.track_native_handle(node, feature, destroy, value)

    def release(self, cleanup: CleanupAction) -> None:
        """
        title: Discharge a native temporary on the success path.
        parameters:
          cleanup: Cleanup.
        """
        self.owner.release_native_handle(cleanup)

    def publish(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Produce one owned Arrow result.
        parameters:
          node: Syntax node to process.
          value: Value to process.
        """
        self.owner.arrow_temporary(node, value)
        self.owner.result_stack.append(value)

    def construct(
        self, node: astx.AST, resolution: ResolvedClassConstruction
    ) -> ir.Value:
        """
        title: Produce one resolved class construction and return
          its value.
        parameters:
          node: Syntax node to process.
          resolution: Resolution.
        returns: 'Result of this operation: produce one resolved
          class construction and return its value.'
        """
        self.owner.lower_class_construct(node, resolution)
        return require_lowered_value(
            self.owner.result_stack[-1],
            node=node,
            context="resolved class construction",
        )
