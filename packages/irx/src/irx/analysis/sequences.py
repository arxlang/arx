# mypy: disable-error-code=no-redef

"""
title: Borrowed, exact numeric sequence adaptation and access contracts.
"""

from dataclasses import replace
from typing import Literal

import astx

from plum import dispatch
from public import private

from irx.analysis.handlers.base import SemanticAnalyzerCore
from irx.analysis.ownership import list_resource_ownership
from irx.analysis.resolved_nodes import (
    IterationKind,
    OwnershipKind,
    ResolvedMaterialization,
    ResolvedSequenceAccess,
)
from irx.analysis.types import (
    is_integer_type,
    is_sequence_element,
    sequence_element_type,
)
from irx.builtins.collections.dataframe import dataframe_type_id
from irx.diagnostics import DiagnosticCodes
from irx.typecheck import typechecked


@private
@typechecked
def sequence_access(
    kind: Literal["list", "tensor", "series", "sequence"],
    element: astx.DataType | None,
    node: astx.AST | None,
) -> ResolvedSequenceAccess | None:
    """
    title: Validate exact numeric storage without widening or null erasure.
    parameters:
      kind:
        type: Literal[list, tensor, series, sequence]
      element:
        type: astx.DataType | None
      node:
        type: astx.AST | None
    returns:
      type: ResolvedSequenceAccess | None
    """
    if element is None or not is_sequence_element(element):
        return None
    if kind in {"list", "tensor"} and isinstance(element, astx.NullableType):
        return None
    inner = (
        element.value_type
        if isinstance(element, astx.NullableType)
        else element
    )
    type_id = dataframe_type_id(inner)
    if type_id is None:
        return None
    return ResolvedSequenceAccess(
        kind,
        element,
        type_id,
        node if isinstance(node, astx.LiteralList) else None,
    )


@private
@dispatch
@typechecked
def resolve_sequence_access(
    type_: astx.DataType | None,
    node: astx.AST | None = None,
) -> ResolvedSequenceAccess | None:
    """
    title: Reject unsupported storage before constructing a borrowed view.
    parameters:
      type_:
        type: astx.DataType | None
      node:
        type: astx.AST | None
    returns:
      type: ResolvedSequenceAccess | None
    """
    del type_, node
    return None


@dispatch
@typechecked
def resolve_sequence_access(
    type_: astx.ListType,
    node: astx.AST | None = None,
) -> ResolvedSequenceAccess | None:
    """
    title: Borrow exact homogeneous list storage without conversion.
    parameters:
      type_:
        type: astx.ListType
      node:
        type: astx.AST | None
    returns:
      type: ResolvedSequenceAccess | None
    """
    return sequence_access("list", sequence_element_type(type_), node)


@dispatch
@typechecked
def resolve_sequence_access(
    type_: astx.TensorType,
    node: astx.AST | None = None,
) -> ResolvedSequenceAccess | None:
    """
    title: Borrow rank-one tensors and defer unknown rank to a checked view.
    parameters:
      type_:
        type: astx.TensorType
      node:
        type: astx.AST | None
    returns:
      type: ResolvedSequenceAccess | None
    """
    return sequence_access("tensor", sequence_element_type(type_), node)


@dispatch
@typechecked
def resolve_sequence_access(
    type_: astx.SeriesType,
    node: astx.AST | None = None,
) -> ResolvedSequenceAccess | None:
    """
    title: Snapshot numeric chunks while preserving their nullability.
    parameters:
      type_:
        type: astx.SeriesType
      node:
        type: astx.AST | None
    returns:
      type: ResolvedSequenceAccess | None
    """
    return sequence_access("series", sequence_element_type(type_), node)


@dispatch
@typechecked
def resolve_sequence_access(
    type_: astx.SequenceType,
    node: astx.AST | None = None,
) -> ResolvedSequenceAccess | None:
    """
    title: Forward an already borrowed descriptor within its owning call.
    parameters:
      type_:
        type: astx.SequenceType
      node:
        type: astx.AST | None
    returns:
      type: ResolvedSequenceAccess | None
    """
    return sequence_access("sequence", type_.element_type, node)


@private
@typechecked
def resolve_materialization(
    analyzer: SemanticAnalyzerCore, node: astx.FunctionCall
) -> None:
    """
    title: >-
      Resolve numeric list construction without treating iterators as views.
    parameters:
      analyzer:
        type: SemanticAnalyzerCore
      node:
        type: astx.FunctionCall
    """
    from irx.analysis.iterables import (  # noqa: PLC0415
        resolve_iteration_capability,
    )

    info = analyzer._semantic(node)
    values = list(node.args)
    if (
        len(values) != 1
        or len(node.keywords) > 1
        or any(item.name != "max_items" for item in node.keywords)
        or astx.get_template_args(node)
    ):
        analyzer.context.diagnostics.add(
            "list expects one input and optional max_items=integer",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    source = values[0]
    analyzer.visit(source)
    source_type = analyzer._expr_type(source)
    iteration = resolve_iteration_capability(source, source_type)
    element = None if iteration is None else iteration.element_type
    if (
        iteration is None
        or not is_sequence_element(element)
        or isinstance(element, astx.NullableType)
    ):
        analyzer.context.diagnostics.add(
            "list materialization requires nonnullable numeric items; "
            "fill or filter nullable input explicitly",
            node=source,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    limit = node.keywords[0].value if node.keywords else None
    if limit is None and iteration.kind is IterationKind.GENERATOR:
        analyzer.context.diagnostics.add(
            "single-pass list materialization requires max_items",
            node=node,
            code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
        )
        return
    if limit is not None:
        analyzer.visit(limit)
        limit_type = analyzer._expr_type(limit)
        if not is_integer_type(limit_type) or isinstance(
            limit_type, (astx.UInt64, astx.UInt128)
        ):
            analyzer.context.diagnostics.add(
                "max_items requires an integer representable in i64",
                node=limit,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
        if (
            isinstance(
                limit,
                (astx.LiteralInteger, astx.LiteralInt64, astx.LiteralInt32),
            )
            and limit.value < 0
        ):
            analyzer.context.diagnostics.add(
                "max_items must be nonnegative",
                node=limit,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
    if iteration.kind is not IterationKind.GENERATOR:
        adapter = resolve_sequence_access(source_type, source)
        if adapter is None:
            analyzer.context.diagnostics.add(
                "list input requires an ordered numeric sequence",
                node=source,
                code=DiagnosticCodes.SEMANTIC_TYPE_MISMATCH,
            )
            return
        iteration = replace(iteration, sequence_access=adapter)
    info.materialization = ResolvedMaterialization(iteration, limit)
    analyzer._set_type(node, astx.ListType([iteration.element_type]))
    analyzer._set_resource_ownership(
        node, list_resource_ownership(OwnershipKind.OWNED)
    )
