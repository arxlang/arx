"""
title: Narrow call-analysis dependencies and fail-closed static dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

import astx

from plum import dispatch
from public import private, public

from irx.analysis.extensions.records import CallOperation
from irx.analysis.resolved_nodes import (
    SemanticClass,
    SemanticFunction,
    SemanticInfo,
)
from irx.diagnostics import DiagnosticBag, DiagnosticCodes
from irx.typecheck import typechecked


@public
@runtime_checkable
class CallAnalysisServices(Protocol):
    """
    title: Expression and nominal-class services needed by the table pilot.
    """

    @property
    def registered_classes(self) -> tuple[astx.ClassDefStmt, ...]:
        """
        title: Return trusted host-provided Arrow declarations.
        returns:
          type: tuple[astx.ClassDefStmt, Ellipsis]
        """
        ...

    @property
    def allowed(self) -> bool:
        """
        title: Whether the current function supports resource-bearing calls.
        returns:
          type: bool
        """
        ...

    def evaluate(self, node: astx.AST) -> astx.DataType | None:
        """
        title: Analyze an operand and return its resolved type.
        parameters:
          node:
            type: astx.AST
        returns:
          type: astx.DataType | None
        """
        ...

    def resolve_class(
        self, type_: astx.ClassType, node: astx.AST
    ) -> SemanticClass | None:
        """
        title: Resolve a nominal class through analysis-owned rules.
        parameters:
          type_:
            type: astx.ClassType
          node:
            type: astx.AST
        returns:
          type: SemanticClass | None
        """
        ...

    def construct(
        self, node: astx.ClassConstruct, class_: SemanticClass
    ) -> None:
        """
        title: Resolve a class construction and its lifecycle dependencies.
        parameters:
          node:
            type: astx.ClassConstruct
          class_:
            type: SemanticClass
        """
        ...


@private
@typechecked
@dataclass(frozen=True)
class AnalysisServices:
    """
    title: Explicit per-call dependencies with compilation-local lifetime.
    attributes:
      analyze_operand:
        type: Callable[[astx.AST], astx.DataType | None]
      find_class:
        type: Callable[[astx.ClassType, astx.AST], SemanticClass | None]
      analyze_construction:
        type: Callable[[astx.ClassConstruct, SemanticClass], None]
      registered_classes:
        type: tuple[astx.ClassDefStmt, Ellipsis]
      allowed:
        type: bool
    """

    analyze_operand: Callable[[astx.AST], astx.DataType | None]
    find_class: Callable[[astx.ClassType, astx.AST], SemanticClass | None]
    analyze_construction: Callable[[astx.ClassConstruct, SemanticClass], None]
    registered_classes: tuple[astx.ClassDefStmt, ...]
    allowed: bool

    def __post_init__(self) -> None:
        """
        title: Validate callback and collection arguments at construction.
        """
        validate_services(
            self.analyze_operand,
            self.find_class,
            self.analyze_construction,
            self.registered_classes,
            self.allowed,
        )

    def evaluate(self, node: astx.AST) -> astx.DataType | None:
        """
        title: Invoke the typed expression-analysis dependency.
        parameters:
          node:
            type: astx.AST
        returns:
          type: astx.DataType | None
        """
        return self.analyze_operand(node)

    def resolve_class(
        self, type_: astx.ClassType, node: astx.AST
    ) -> SemanticClass | None:
        """
        title: Invoke the typed class-resolution dependency.
        parameters:
          type_:
            type: astx.ClassType
          node:
            type: astx.AST
        returns:
          type: SemanticClass | None
        """
        return self.find_class(type_, node)

    def construct(
        self, node: astx.ClassConstruct, class_: SemanticClass
    ) -> None:
        """
        title: Invoke the typed construction-analysis dependency.
        parameters:
          node:
            type: astx.ClassConstruct
          class_:
            type: SemanticClass
        """
        self.analyze_construction(node, class_)


@private
@typechecked
def validate_services(
    evaluate: Callable[[astx.AST], astx.DataType | None],
    resolve_class: Callable[[astx.ClassType, astx.AST], SemanticClass | None],
    construct: Callable[[astx.ClassConstruct, SemanticClass], None],
    registered_classes: tuple[astx.ClassDefStmt, ...],
    allowed: bool,
) -> None:
    """
    title: Check generated service-bundle constructor fields.
    parameters:
      evaluate:
        type: Callable[[astx.AST], astx.DataType | None]
      resolve_class:
        type: Callable[[astx.ClassType, astx.AST], SemanticClass | None]
      construct:
        type: Callable[[astx.ClassConstruct, SemanticClass], None]
      registered_classes:
        type: tuple[astx.ClassDefStmt, Ellipsis]
      allowed:
        type: bool
    """


@public
@typechecked
@dataclass(frozen=True)
class AnalysisCall:
    """
    title: >-
      Bound callable identity and narrow services for one analysis invocation.
    attributes:
      node:
        type: astx.FunctionCall | astx.MethodCall
      function:
        type: SemanticFunction
      info:
        type: SemanticInfo
      diagnostics:
        type: DiagnosticBag
      services:
        type: CallAnalysisServices
    """

    node: astx.FunctionCall | astx.MethodCall
    function: SemanticFunction
    info: SemanticInfo
    diagnostics: DiagnosticBag
    services: CallAnalysisServices

    def __post_init__(self) -> None:
        """
        title: Validate invocation arguments, not merely Protocol presence.
        """
        validate_call(
            self.node,
            self.function,
            self.info,
            self.diagnostics,
            self.services,
        )


@private
@typechecked
def validate_call(
    node: astx.FunctionCall | astx.MethodCall,
    function: SemanticFunction,
    info: SemanticInfo,
    diagnostics: DiagnosticBag,
    services: CallAnalysisServices,
) -> None:
    """
    title: Check the nominal analysis-call envelope and service collections.
    parameters:
      node:
        type: astx.FunctionCall | astx.MethodCall
      function:
        type: SemanticFunction
      info:
        type: SemanticInfo
      diagnostics:
        type: DiagnosticBag
      services:
        type: CallAnalysisServices
    """
    validate_services(
        services.evaluate,
        services.resolve_class,
        services.construct,
        services.registered_classes,
        services.allowed,
    )


@private
@typechecked
class CallAnalysisVisitor:
    """
    title: Reject unsupported semantic operations through nominal dispatch.
    summary: Concrete visitors supply a fixed set of typed visit overloads.
    """

    @dispatch
    def visit(self, operation: CallOperation, call: AnalysisCall) -> None:
        """
        title: Diagnose unknown trusted operations before lowering.
        parameters:
          operation:
            type: CallOperation
          call:
            type: AnalysisCall
        """
        call.diagnostics.add(
            f"unsupported call operation: {type(operation).__name__}",
            node=call.node,
            code=DiagnosticCodes.SEMANTIC_UNSUPPORTED_NODE,
        )
