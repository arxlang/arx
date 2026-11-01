"""
title: Narrow LLVM services for resolved call-plan emission.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, runtime_checkable

import astx

from llvmlite import ir
from public import private, public

from irx.analysis.resolved_nodes import ResolvedClassConstruction
from irx.builder.state import CleanupAction
from irx.extensions import HandlerConfiguration
from irx.typecheck import typechecked


@public
@runtime_checkable
class CallLoweringServices(Protocol):
    """
    title: Only the value, checked-call, and lifetime services the pilot needs.
    """

    @property
    def builder(self) -> ir.IRBuilder:
        """
        title: Return the active function instruction builder.
        returns:
          type: ir.IRBuilder
        """
        ...

    def text(self, value: str) -> ir.Value:
        """
        title: Intern a configuration string in the current LLVM module.
        parameters:
          value:
            type: str
        returns:
          type: ir.Value
        """
        ...

    def evaluate(self, node: astx.AST) -> ir.Value:
        """
        title: Evaluate once and pin aliases across later operand side effects.
        parameters:
          node:
            type: astx.AST
        returns:
          type: ir.Value
        """
        ...

    def handle(self, node: astx.AST, value: ir.Value, index: int) -> ir.Value:
        """
        title: Require a live class and load its semantically resolved handle.
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
        ...

    def convert(
        self, node: astx.AST, value: ir.Value, target: astx.DataType
    ) -> ir.Value:
        """
        title: Emit the conversion selected by the resolved operand contract.
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
        ...

    def invoke(
        self, node: astx.AST, feature: str, name: str, args: list[ir.Value]
    ) -> ir.Value:
        """
        title: >-
          Activate a registered symbol and read its output only on success.
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
        ...

    def track(
        self, node: astx.AST, feature: str, destroy: str, value: ir.Value
    ) -> CleanupAction:
        """
        title: Register a temporary native handle for abrupt-exit cleanup.
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
        ...

    def release(self, cleanup: CleanupAction) -> None:
        """
        title: Release a temporary and discharge its pending cleanup.
        parameters:
          cleanup:
            type: CleanupAction
        """
        ...

    def publish(self, node: astx.AST, value: ir.Value) -> None:
        """
        title: Register an owned Arrow result and produce exactly one value.
        parameters:
          node:
            type: astx.AST
          value:
            type: ir.Value
        """
        ...

    def construct(
        self, node: astx.AST, resolution: ResolvedClassConstruction
    ) -> ir.Value:
        """
        title: Produce a class value using its resolved construction plan.
        parameters:
          node:
            type: astx.AST
          resolution:
            type: ResolvedClassConstruction
        returns:
          type: ir.Value
        """
        ...


@public
@typechecked
@dataclass(frozen=True)
class LoweringCall:
    """
    title: One lowering invocation, not configuration or semantic state.
    attributes:
      node:
        type: astx.FunctionCall | astx.MethodCall
      services:
        type: CallLoweringServices
    """

    node: astx.FunctionCall | astx.MethodCall
    services: CallLoweringServices

    def __post_init__(self) -> None:
        """
        title: Validate generated constructor arguments at the phase boundary.
        """
        validate_lowering_call(self.node, self.services)


@private
@typechecked
def validate_lowering_call(
    node: astx.FunctionCall | astx.MethodCall, services: CallLoweringServices
) -> None:
    """
    title: Require a typed service implementation and valid call syntax.
    parameters:
      node:
        type: astx.FunctionCall | astx.MethodCall
      services:
        type: CallLoweringServices
    """


@public
@lru_cache(maxsize=1)
@typechecked
def default_lowering_configuration() -> HandlerConfiguration:
    """
    title: Load only LLVM providers for the finite built-in pilot.
    returns:
      type: HandlerConfiguration
    """
    from irx.builder.lowering.table_io import (  # noqa: PLC0415
        lowering_contributions,
    )

    return HandlerConfiguration("lowering", lowering_contributions())
