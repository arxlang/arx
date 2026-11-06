"""
title: Bridge existing LLVM services to the narrow call-plan interface.
summary: >-
  This adapter contains no operation selection or algorithms. It is constructed
  by the concrete visitor and never imported by semantic analysis.
"""

import astx

from llvmlite import ir
from public import private

from irx.analysis.resolved_nodes import ResolvedClassConstruction
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
      owner:
        type: Visitor
    """

    owner: Visitor

    def __init__(self, owner: Visitor) -> None:
        """
        title: Bind one compiler instance for resolved call emission.
        parameters:
          owner:
            type: Visitor
        """
        self.owner = owner

    @property
    def builder(self) -> ir.IRBuilder:
        """
        title: Return the active instruction builder.
        returns:
          type: ir.IRBuilder
        """
        return self.owner._llvm.ir_builder

    def text(self, value: str) -> ir.Value:
        """
        title: Reuse module-local string interning.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        return self.owner._constant_c_string_pointer(
            value, name_hint="table_io"
        )

    def evaluate(self, node: astx.AST) -> ir.Value:
        """
        title: Evaluate and pin one argument without leaking stack entries.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Value
        """
        self.owner.visit_child(node)
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
          node:
            type: astx.AST
          value:
            type: ir.Value
          index:
            type: int
        returns:
          type: ir.Value
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
          node:
            type: astx.AST
          value:
            type: ir.Value
          target:
            type: astx.DataType
        returns:
          type: ir.Value
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
        title: >-
          Reuse checked status/output ABI and registered runtime activation.
        parameters:
          node:
            type: astx.AST
          feature:
            type: str
          name:
            type: str
          args:
            type: list[ir.Value]
        returns:
          type: ir.Value
        """
        return self.owner.checked_native_call(
            node, self.owner.require_runtime_symbol(feature, name), args
        )

    def track(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Register existing native cleanup behavior.
        parameters:
          node:
            type: astx.AST
          feature:
            type: str
          destroy:
            type: str
          value:
            type: ir.Value
        returns:
          type: CleanupAction
        """
        return self.owner.track_native_handle(node, feature, destroy, value)

    def release(self, cleanup: CleanupAction) -> None:
        """
        title: Discharge a native temporary on the success path.
        parameters:
          cleanup:
            type: CleanupAction
        """
        self.owner.release_native_handle(cleanup)

    def publish(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Produce one owned Arrow result.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        self.owner.arrow_temporary(node, value)
        self.owner.result_stack.append(value)

    def construct(
        self, node: astx.AST, resolution: ResolvedClassConstruction
    ) -> ir.Value:
        """
        title: Produce one resolved class construction and return its value.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedClassConstruction
        returns:
          type: ir.Value
        """
        self.owner.lower_class_construct(node, resolution)
        return require_lowered_value(
            self.owner.result_stack[-1],
            node=node,
            context="resolved class construction",
        )
