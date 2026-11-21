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
    attributes:
      registered_classes: Registered classes.
      allowed: Whether to use allowed.
    """

    @property
    def registered_classes(self) -> tuple[astx.ClassDefStmt, ...]:
        """
        title: Return trusted host-provided Arrow declarations.
        returns: Trusted host-provided Arrow declarations.
        """
        ...

    @property
    def allowed(self) -> bool:
        """
        title: Whether the current function supports resource-bearing calls.
        returns: 'Result of this operation: whether the current function
          supports resource-bearing calls.'
        """
        ...

    def evaluate(self, node: astx.AST) -> astx.DataType | None:
        """
        title: Analyze an operand and return its resolved type.
        parameters:
          node: Syntax node to process.
        returns: 'Result of this operation: analyze an operand and return
          its resolved type.'
        """
        ...

    def resolve_class(
        self, type_: astx.ClassType, node: astx.AST
    ) -> SemanticClass | None:
        """
        title: Resolve a nominal class through analysis-owned rules.
        parameters:
          type_: Type expression to process.
          node: Syntax node to process.
        returns: Resolved a nominal class through analysis-owned rules.
        """
        ...

    def construct(
        self, node: astx.ClassConstruct, class_: SemanticClass
    ) -> None:
        """
        title: Resolve a class construction and its lifecycle dependencies.
        parameters:
          node: Syntax node to process.
          class_: Class being processed.
        """
        ...


@private
@typechecked
@dataclass(frozen=True)
class AnalysisServices:
    """
    title: Explicit per-call dependencies with compilation-local lifetime.
    attributes:
      analyze_operand: Analyze operand.
      find_class: Find class.
      analyze_construction: Analyze construction.
      registered_classes: Registered classes.
      allowed: Whether to use allowed.
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
          node: Syntax node to process.
        returns: 'Result of this operation: invoke the typed
          expression-analysis dependency.'
        """
        return self.analyze_operand(node)

    def resolve_class(
        self, type_: astx.ClassType, node: astx.AST
    ) -> SemanticClass | None:
        """
        title: Invoke the typed class-resolution dependency.
        parameters:
          type_: Type expression to process.
          node: Syntax node to process.
        returns: 'Result of this operation: invoke the typed class-resolution
          dependency.'
        """
        return self.find_class(type_, node)

    def construct(
        self, node: astx.ClassConstruct, class_: SemanticClass
    ) -> None:
        """
        title: Invoke the typed construction-analysis dependency.
        parameters:
          node: Syntax node to process.
          class_: Class being processed.
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
      evaluate: Evaluate.
      resolve_class: Resolve class.
      construct: Construct.
      registered_classes: Registered classes.
      allowed: Whether to use allowed.
    """


@public
@typechecked
@dataclass(frozen=True)
class AnalysisCall:
    """
    title: Bound callable identity and narrow services for one analysis
      invocation.
    attributes:
      node: Syntax node to process.
      function: Function to process.
      info: Resolved metadata for the operation.
      diagnostics: Collected structured diagnostics.
      services: Services.
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
      node: Syntax node to process.
      function: Function to process.
      info: Resolved metadata for the operation.
      diagnostics: Collected structured diagnostics.
      services: Services.
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
          operation: Operation to resolve or execute.
          call: Call being processed.
        """
        call.diagnostics.add(
            f"unsupported call operation: {type(operation).__name__}",
            node=call.node,
            code=DiagnosticCodes.SEMANTIC_UNSUPPORTED_NODE,
        )
