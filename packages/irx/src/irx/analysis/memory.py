"""
title: Analyze resolved standard-library memory operations.
"""

from dataclasses import dataclass

import astx

from plum import dispatch
from public import private

from irx.analysis.compute import ComputeAnalysisVisitor
from irx.analysis.extensions.calls import AnalysisCall
from irx.analysis.extensions.records import CALL_PLAN, CallOperation, CallPlan
from irx.analysis.ownership import list_resource_ownership, resource_ownership
from irx.analysis.resolved_nodes import (
    FailedInferenceType,
    OwnershipKind,
    ResourceKind,
    SemanticInfo,
)
from irx.analysis.types import is_type_member, same_type
from irx.builtins.collections.list import (
    list_element_type,
    list_supports_owned_element,
)
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import copy_type, typechecked


@private
@typechecked
@dataclass(frozen=True)
class CopyOperation(CallOperation):
    """
    title: Explicit copy from the host-registered memory module.
    """


@private
@typechecked
@dataclass(frozen=True)
class ListCopyPlan(CallPlan):
    """
    title: Copy one resolved list operand into independently owned storage.
    attributes:
      source: Dynamic list value to read.
    """

    source: astx.DataType

    def validate(self) -> None:
        """
        title: Require a typed source expression at the fact boundary.
        """
        if not isinstance(self.source, astx.DataType):
            raise TypeError("list copy requires a value expression")

    def dependencies(self) -> tuple[astx.AST, ...]:
        """
        title: Expose the operand to reachability and invalidation.
        returns: Operand evaluated by the copy.
        """
        return (self.source,)

    def invalidate(self, node: astx.AST) -> None:
        """
        title: Clear result metadata owned by this plan on reanalysis.
        parameters:
          node: Call with attached result metadata.
        """
        info = getattr(node, "semantic", None)
        if isinstance(info, SemanticInfo):
            info.resolved_type = None
            info.resource_ownership = None


@private
@typechecked
def validate_copy_registration(declaration: astx.FunctionPrototype) -> None:
    """
    title: Validate the declaration of the trusted list copy operation.
    parameters:
      declaration: Bundled copy prototype to register.
    """
    args = declaration.args.nodes
    parameters = astx.get_template_params(declaration)
    if (
        len(args) != 1
        or args[0].name != "value"
        or args[0].borrow_access is not None
        or not isinstance(args[0].default, astx.Undefined)
        or getattr(declaration, "is_variadic", False)
        or len(parameters) != 1
        or not same_type(args[0].type_, declaration.return_type)
    ):
        raise ValueError("copy declaration requires (value: T) -> T")
    type_ = args[0].type_
    parameter = parameters[0]
    if (
        not isinstance(type_, astx.TemplateTypeVar)
        or type_.name != parameter.name
        or not same_type(type_.bound, parameter.bound)
    ):
        raise ValueError("copy requires one matching list element type")
    bound = parameter.bound
    members = bound.members if isinstance(bound, astx.UnionType) else (bound,)
    if not members or not all(
        list_supports_owned_element(list_element_type(t)) for t in members
    ):
        raise ValueError("copy declaration requires supported list elements")


@private
@typechecked
class MemoryAnalysisVisitor(ComputeAnalysisVisitor):
    """
    title: Resolve memory calls through the shared nominal call visitor.
    """

    @copy_type(ComputeAnalysisVisitor.visit)
    @dispatch
    def visit(self, operation: CopyOperation, call: AnalysisCall) -> None:
        """
        title: Validate a read into a new owned list of the same type.
        parameters:
          operation: Copy capability resolved through the call binding.
          call: Invocation with typed analysis services.
        """
        del operation
        node, info = call.node, call.info
        info.resolved_type = FailedInferenceType()
        info.resource_ownership = None
        operands = tuple(node.args)
        if len(operands) != 1 or node.keywords or astx.get_template_args(node):
            call.diagnostics.add(
                "copy expects one positional list value and no templates",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        source = operands[0]
        source_type = call.services.evaluate(source)
        if isinstance(source_type, FailedInferenceType):
            return
        if not list_supports_owned_element(list_element_type(source_type)):
            call.diagnostics.add(
                "copy requires a list of numeric, Boolean, or string values",
                node=source,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        ownership = resource_ownership(source)
        if (
            ownership is None
            or ownership.resource_kind is not ResourceKind.LIST
            or ownership.kind
            not in {OwnershipKind.OWNED, OwnershipKind.BORROWED}
        ):
            call.diagnostics.add(
                "copy requires a dynamic list value",
                node=source,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        if not is_type_member(
            call.function.template_params[0].bound, source_type
        ):
            call.diagnostics.add(
                "copy operand does not match its declared list domain",
                node=source,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        if not call.services.allowed:
            call.diagnostics.add(
                "copy requires a non-generator function with list cleanup",
                node=node,
                code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
            )
            return
        info.facts = info.facts.with_fact(CALL_PLAN, ListCopyPlan(source))
        info.resolved_type = source_type
        info.resource_ownership = list_resource_ownership(OwnershipKind.OWNED)
