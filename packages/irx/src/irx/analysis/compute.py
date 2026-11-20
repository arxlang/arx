"""
title: Closed f64 math capabilities and compilation-local semantic call plans.
summary: >-
  Lowering consumes these plans through the shared versioned Arrow runtime.
  sqrt and exp use Arrow 26.0.1 unchecked IEEE kernels, with null propagation,
  no options or fast-math, and finite error budgets of 4 and 8 ULP
  respectively. sqrt preserves signed zero and maps negative inputs to NaN. exp
  overflow produces positive infinity; underflow produces subnormals or
  positive zero. NaN payloads and output chunk boundaries are not guaranteed.
  Scalars retain native transport; Series results own references and preserve
  order/length.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import astx
import pyarrow as pa

from plum import dispatch
from public import private

from irx.analysis.arrow_conversion import arrow_ownership
from irx.analysis.call_arguments import argument_slots, call_evaluations
from irx.analysis.extensions.calls import AnalysisCall
from irx.analysis.extensions.records import CALL_PLAN, CallOperation, CallPlan
from irx.analysis.numeric_literals import contextualize_literal
from irx.analysis.resolved_nodes import (
    ImplicitConversion,
    OwnershipKind,
    ResourceOwnership,
    SemanticFunction,
    SemanticInfo,
)
from irx.analysis.table_io import TableIOAnalysisVisitor
from irx.analysis.types import clone_type, is_assignable, same_type
from irx.builtins.collections.column_types import column_arrow_type
from irx.diagnostics import DiagnosticCodes
from irx.native import COMPUTE_CATALOG, ComputeKernel, validate_compute_kernel
from irx.typecheck import copy_type, typechecked

ComputeShape = Literal["scalar", "nullable_scalar", "series"]


@private
@typechecked
def compute_shape(type_: astx.DataType) -> ComputeShape | None:
    """
    title: Recognize only the approved f64 storage and compute shapes.
    parameters:
      type_:
        type: astx.DataType
    returns:
      type: ComputeShape | None
    """
    if isinstance(type_, astx.Float64):
        return "scalar"
    if isinstance(type_, astx.NullableType) and isinstance(
        type_.value_type, astx.Float64
    ):
        return "nullable_scalar"
    if isinstance(type_, astx.SeriesType) and isinstance(
        type_.element_type, astx.Float64
    ):
        return "series"
    return None


@private
@typechecked
@dataclass(frozen=True, init=False)
class ComputeOperation(CallOperation):
    """
    title: One approved kernel identity supplied by trusted host metadata.
    attributes:
      kernel:
        type: ComputeKernel
      operation_id:
        type: int
      arrow_version:
        type: Literal[26.0.1]
      arrow_type_id:
        type: int
      required_runtime_features:
        type: tuple[str, Ellipsis]
      null_policy:
        type: Literal[propagate]
      domain_policy:
        type: Literal[ieee]
      max_ulps:
        type: int
    """

    kernel: ComputeKernel
    operation_id: int
    arrow_version: Literal["26.0.1"]
    arrow_type_id: int
    required_runtime_features: tuple[str, ...]
    null_policy: Literal["propagate"]
    domain_policy: Literal["ieee"]
    max_ulps: int

    def __init__(self, kernel: ComputeKernel) -> None:
        """
        title: Validate the closed kernel identifier, including runtime inputs.
        parameters:
          kernel:
            type: ComputeKernel
        """
        validate_compute_kernel(kernel)
        object.__setattr__(self, "kernel", kernel)
        object.__setattr__(
            self, "operation_id", COMPUTE_CATALOG[kernel].operation_id
        )
        object.__setattr__(self, "arrow_version", "26.0.1")
        object.__setattr__(
            self, "arrow_type_id", column_arrow_type(astx.Float64()).id
        )
        object.__setattr__(
            self, "required_runtime_features", ("arrow_compute",)
        )
        object.__setattr__(self, "null_policy", "propagate")
        object.__setattr__(self, "domain_policy", "ieee")
        object.__setattr__(self, "max_ulps", COMPUTE_CATALOG[kernel].max_ulps)


@private
@typechecked
@dataclass(frozen=True)
class ComputePlan(CallPlan):
    """
    title: Resolved unary math meaning; no name or type lookup remains.
    attributes:
      operation:
        type: ComputeOperation
      function:
        type: SemanticFunction
      argument:
        type: astx.AST
      result_type:
        type: astx.DataType
      shape:
        type: ComputeShape
      conversion:
        type: ImplicitConversion
      ownership:
        type: ResourceOwnership | None
    """

    operation: ComputeOperation
    function: SemanticFunction
    argument: astx.AST
    result_type: astx.DataType
    shape: ComputeShape
    conversion: ImplicitConversion
    ownership: ResourceOwnership | None

    def __post_init__(self) -> None:
        """
        title: Validate generated constructor fields before publishing a plan.
        """
        self.validate()

    def validate(self) -> None:
        """
        title: Recheck the closed identity and type/ownership contract.
        """
        validate_compute_plan(
            self.operation,
            self.function,
            self.argument,
            self.result_type,
            self.shape,
            self.conversion,
            self.ownership,
        )

    def dependencies(self) -> tuple[astx.AST, ...]:
        """
        title: Expose the operand to declaration reachability and invalidation.
        returns:
          type: tuple[astx.AST, Ellipsis]
        """
        return (self.argument,)

    def invalidate(self, node: astx.AST) -> None:
        """
        title: Remove owned result metadata before analyzing a reused tree.
        parameters:
          node:
            type: astx.AST
        """
        info = getattr(node, "semantic", None)
        if isinstance(info, SemanticInfo):
            info.resource_ownership = None
            info.resolved_type = None


@private
@typechecked
def validate_compute_plan(
    operation: ComputeOperation,
    function: SemanticFunction,
    argument: astx.AST,
    result_type: astx.DataType,
    shape: ComputeShape,
    conversion: ImplicitConversion,
    ownership: ResourceOwnership | None,
) -> None:
    """
    title: Reject invalid record fields and lossy or mismatched conversions.
    parameters:
      operation:
        type: ComputeOperation
      function:
        type: SemanticFunction
      argument:
        type: astx.AST
      result_type:
        type: astx.DataType
      shape:
        type: ComputeShape
      conversion:
        type: ImplicitConversion
      ownership:
        type: ResourceOwnership | None
    """
    if operation != ComputeOperation(operation.kernel) or (
        function.signature.operation != operation
    ):
        raise ValueError("compute plan does not match its callable identity")
    if (
        compute_shape(result_type) != shape
        or conversion.source_type is None
        or compute_shape(conversion.source_type) is None
        or not is_assignable(result_type, conversion.source_type)
        or not same_type(conversion.target_type, result_type)
    ):
        raise ValueError("compute plans require compatible f64 input/output")
    expected = (
        arrow_ownership(result_type, OwnershipKind.OWNED)
        if shape == "series"
        else None
    )
    if ownership != expected:
        raise ValueError("compute result ownership does not match its shape")


@private
@typechecked
def validate_compute_registration(declaration: astx.FunctionPrototype) -> None:
    """
    title: Validate a unary shape-preserving declaration, including templates.
    parameters:
      declaration:
        type: astx.FunctionPrototype
    """
    args = declaration.args.nodes
    if any(
        getattr(declaration, name, None) is not None
        for name in (
            "runtime_feature",
            "runtime_features",
            "ffi_return_ownership",
        )
    ):
        raise ValueError("compute execution metadata belongs to its binding")
    if (
        len(args) != 1
        or args[0].name != "value"
        or not isinstance(args[0].default, astx.Undefined)
        or getattr(declaration, "is_variadic", False)
        or not same_type(args[0].type_, declaration.return_type)
    ):
        raise ValueError("compute declarations require (value: T) -> T")
    type_ = args[0].type_
    parameters = astx.get_template_params(declaration)
    if isinstance(type_, astx.TemplateTypeVar):
        if (
            len(parameters) != 1
            or parameters[0].name != type_.name
            or not same_type(parameters[0].bound, type_.bound)
        ):
            raise ValueError("compute templates require one matching type")
        type_ = parameters[0].bound
    elif parameters or isinstance(type_, astx.UnionType):
        raise ValueError("compute unions require one bounded template type")
    members = type_.members if isinstance(type_, astx.UnionType) else (type_,)
    if not members or any(compute_shape(member) is None for member in members):
        raise ValueError("compute declarations support only f64 shapes")


@private
@typechecked
class ComputeAnalysisVisitor(TableIOAnalysisVisitor):
    """
    title: Extend nominal call analysis without changing existing operations.
    """

    @copy_type(TableIOAnalysisVisitor.visit)
    @dispatch
    def visit(self, operation: ComputeOperation, call: AnalysisCall) -> None:
        """
        title: Resolve one typed unary call after ordinary symbol lookup.
        parameters:
          operation:
            type: ComputeOperation
          call:
            type: AnalysisCall
        """
        node, info = call.node, call.info
        info.resolved_type = None
        info.resource_ownership = None
        if (pa.__version__, pa.cpp_version) != (
            operation.arrow_version,
            operation.arrow_version,
        ):
            call.diagnostics.add(
                "compute calls require matching Arrow "
                f"{operation.arrow_version} "
                "Python and C++ runtimes",
                node=node,
                code=DiagnosticCodes.RUNTIME_FEATURE_UNAVAILABLE,
            )
            return
        if argument_slots(call.function, node, call.diagnostics) is None:
            return
        argument = call_evaluations(node)[0]
        contextualize_literal(argument, astx.Float64())
        source = call.services.evaluate(argument)
        if source is None:
            return
        shape = compute_shape(source)
        declared = call.function.signature.parameters[0].type_
        target = declared
        if isinstance(declared, astx.TemplateTypeVar):
            target = call.function.template_params[0].bound
        explicit = astx.get_template_args(node)
        if (
            shape is None
            or not is_assignable(target, source)
            or (
                explicit is not None
                and (
                    not call.function.template_params
                    or len(explicit) != 1
                    or not same_type(explicit[0], source)
                )
            )
        ):
            call.diagnostics.add(
                "compute call requires a supported f64 scalar/Series shape "
                "matching its declaration and explicit specialization",
                node=argument,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        if not call.services.allowed:
            call.diagnostics.add(
                "compute calls require a non-generator function",
                node=node,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        # Monomorphic nullable parameters box scalar inputs. A template instead
        # preserves its inferred concrete shape, including known Series length.
        result = clone_type(
            declared if isinstance(declared, astx.NullableType) else source
        )
        shape = compute_shape(result)
        assert shape is not None
        ownership = (
            arrow_ownership(result, OwnershipKind.OWNED)
            if shape == "series"
            else None
        )
        plan = ComputePlan(
            operation,
            call.function,
            argument,
            result,
            shape,
            ImplicitConversion(clone_type(source), result),
            ownership,
        )
        info.facts = info.facts.with_fact(CALL_PLAN, plan)
        info.resolved_type = result
        info.resource_ownership = ownership
