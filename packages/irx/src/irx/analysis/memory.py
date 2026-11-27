"""
title: Analyze resolved standard-library memory operations.
"""

from dataclasses import dataclass

import astx

from astx.types import AnyType
from plum import dispatch
from public import private

from irx.analysis.class_lifecycle import COPY_HOOK
from irx.analysis.compute import ComputeAnalysisVisitor
from irx.analysis.extensions.calls import AnalysisCall
from irx.analysis.extensions.records import CALL_PLAN, CallOperation, CallPlan
from irx.analysis.ownership import list_resource_ownership, resource_ownership
from irx.analysis.resolved_nodes import (
    FailedInferenceType,
    OwnershipKind,
    ResolvedMethodCall,
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
class CopyPlan(CallPlan):
    """
    title: A copy result with type and ownership supplied by the chosen path.
    """

    def invalidate(self, node: astx.AST) -> None:
        """
        title: Clear result metadata owned by the plan on reanalysis.
        parameters:
          node: Call with attached result metadata.
        """
        info = getattr(node, "semantic", None)
        if isinstance(info, SemanticInfo):
            info.resolved_type = None
            info.resource_ownership = None


@private
@typechecked
@dataclass(frozen=True)
class ListCopyPlan(CopyPlan):
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


@private
@typechecked
@dataclass(frozen=True)
class ClassCopyPlan(CopyPlan):
    """
    title: Call the resolved instance hook with the original operand.
    attributes:
      source: Analyzed class receiver.
      method: Bound hook with its dispatch and result ABI.
    """

    source: astx.DataType
    method: ResolvedMethodCall

    def validate(self) -> None:
        """
        title: Require a typed receiver and method plan at the fact boundary.
        """
        if not isinstance(self.source, astx.DataType) or not isinstance(
            self.method, ResolvedMethodCall
        ):
            raise TypeError("class copy requires a value and resolved method")

    def dependencies(self) -> tuple[astx.AST, ...]:
        """
        title: Retain the receiver and hook through declaration reachability.
        returns: Operand, receiver class, and selected method declaration.
        """
        return (
            self.source,
            self.method.class_.declaration,
            self.method.member.declaration,
        )


@private
@typechecked
def copy_bound_members(bound: astx.DataType) -> tuple[astx.DataType, ...]:
    """
    title: Get the alternatives of the trusted memory declaration.
    parameters:
      bound: Template bound, including the private class-capability marker.
    returns: Nominal alternatives supplied by the host.
    """
    return bound.members if isinstance(bound, astx.UnionType) else (bound,)


@private
@typechecked
def validate_copy_registration(declaration: astx.FunctionPrototype) -> None:
    """
    title: Validate the declaration of the trusted copy operation.
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
        raise ValueError("copy requires one matching template parameter")
    members = copy_bound_members(parameter.bound)
    # Exact AnyType is a host-only marker for the class copy protocol.
    if not members or not all(
        type(t) is AnyType or list_supports_owned_element(list_element_type(t))
        for t in members
    ):
        raise ValueError("copy requires supported lists or the class protocol")


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
        title: Resolve a copy of the same type as the source value.
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
                "copy expects one positional value and no templates",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        source = operands[0]
        source_type = call.services.evaluate(source)
        if isinstance(source_type, FailedInferenceType):
            return
        bound = call.function.template_params[0].bound
        if isinstance(source_type, astx.ClassType):
            resolve_class_copy(call, source, source_type, bound)
            return
        if source_type is None or not list_supports_owned_element(
            list_element_type(source_type)
        ):
            call.diagnostics.add(
                "copy requires a list of numeric, Boolean, or string values "
                "or a class with __copy__",
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
        if not is_type_member(bound, source_type):
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


@private
@typechecked
def resolve_class_copy(
    call: AnalysisCall,
    source: astx.DataType,
    source_type: astx.ClassType,
    bound: astx.DataType,
) -> None:
    """
    title: Bind the copy hook to the analyzed class receiver.
    parameters:
      call: Standard-library copy invocation.
      source: Original source expression.
      source_type: Resolved static type of the operand.
      bound: Copy declaration's host-provided bound.
    """
    if not any(type(t) is AnyType for t in copy_bound_members(bound)):
        call.diagnostics.add(
            "copy declaration does not admit class values",
            node=source,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    if not call.services.allowed:
        call.diagnostics.add(
            "copy requires a non-generator function with class cleanup",
            node=call.node,
            code=DiagnosticCodes.SEMANTIC_INVALID_OWNERSHIP,
        )
        return
    class_ = call.services.resolve_class(source_type, source)
    if class_ is None:
        return
    invocation = astx.MethodCall(source, COPY_HOOK.name, [])
    invocation.loc = call.node.loc
    call.services.bind_instance_method(invocation, class_, source_type, [])
    info = getattr(invocation, "semantic", None)
    if not isinstance(info, SemanticInfo) or info.resolved_method_call is None:
        return
    if not same_type(info.resolved_type, source_type):
        call.diagnostics.add(
            f"copy requires '{class_.name}.__copy__' to return "
            f"'{class_.name}'; define a copy hook for this class",
            node=call.node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    call.info.facts = call.info.facts.with_fact(
        CALL_PLAN, ClassCopyPlan(source, info.resolved_method_call)
    )
    call.info.resolved_type = source_type
    call.info.resource_ownership = info.resource_ownership
