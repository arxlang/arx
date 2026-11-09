# mypy: disable-error-code=no-redef

"""
title: Iterable capability helpers for semantic analysis.
summary: >-
  Resolve known IRx collection types into backend-neutral iteration sidecars so
  loop and comprehension analysis share one semantic authority.
"""

from __future__ import annotations

import astx

from plum import dispatch
from public import private, public

from irx.analysis.ownership import resource_ownership
from irx.analysis.resolved_nodes import (
    CursorProtocol,
    IterationKind,
    IterationOrder,
    ResolvedIteration,
    ResourceKind,
)
from irx.analysis.sequences import resolve_sequence_access
from irx.analysis.types import is_string_type
from irx.builtins.collections.list import list_element_type
from irx.typecheck import typechecked


@private
@dispatch
@typechecked
def list_iteration_owner(node: astx.AST) -> str | None:
    """
    title: Resolve the named storage owner of a list-valued iterable.
    summary: >-
      Identifiers borrow their owner's storage; assignment expressions also
      expose their destination's storage despite producing an owned result.
      Fresh temporaries and static lists do not borrow a named owner.
    parameters:
      node:
        type: astx.AST
    returns:
      type: str | None
    """
    ownership = resource_ownership(node)
    if ownership is None or ownership.resource_kind is not ResourceKind.LIST:
        return None
    return ownership.owner_symbol_id


@private
@dispatch
@typechecked
def list_iteration_owner(node: astx.Cast) -> str | None:
    """
    title: Identity list casts do not retain or copy the source storage.
    parameters:
      node:
        type: astx.Cast
    returns:
      type: str | None
    """
    return list_iteration_owner(node.value)


@public
@typechecked
def resolve_iteration_capability(
    iterable_node: astx.AST,
    iterable_type: astx.DataType | None,
) -> ResolvedIteration | None:
    """
    title: Resolve one iterable semantic capability.
    summary: >-
      Return the canonical iteration sidecar for known concrete iterable types,
      or None when the expression is not iterable in the current IRx contract.
    parameters:
      iterable_node:
        type: astx.AST
      iterable_type:
        type: astx.DataType | None
    returns:
      type: ResolvedIteration | None
    """
    if iterable_type is None:
        return None

    if isinstance(iterable_type, astx.RangeType):
        return ResolvedIteration(
            iterable_node=iterable_node,
            iterable_type=iterable_type,
            element_type=astx.Int32(),
            kind=IterationKind.RANGE,
            order=IterationOrder.INDEX,
            cursor_protocol=CursorProtocol.RANGE,
        )

    if isinstance(
        iterable_type,
        (astx.SequenceType, astx.SeriesType, astx.TensorType, astx.Bytes),
    ):
        adapter = resolve_sequence_access(iterable_type)
        if adapter is None:
            return None
        return ResolvedIteration(
            iterable_node=iterable_node,
            iterable_type=iterable_type,
            element_type=adapter.element_type,
            kind=IterationKind.SEQUENCE,
            order=IterationOrder.INDEX,
            sequence_access=adapter,
            cursor_protocol=CursorProtocol.INDEXED,
        )

    list_type = list_element_type(iterable_type)
    if list_type is not None:
        return ResolvedIteration(
            iterable_node=iterable_node,
            iterable_type=iterable_type,
            element_type=list_type,
            kind=IterationKind.LIST,
            order=IterationOrder.INDEX,
            borrowed_owner_symbol_id=list_iteration_owner(iterable_node),
            cursor_protocol=CursorProtocol.INDEXED,
            element_ownership="borrowed"
            if is_string_type(list_type)
            else "value",
        )

    if isinstance(iterable_type, astx.DictType) and isinstance(
        iterable_type.key_type,
        astx.DataType,
    ):
        return ResolvedIteration(
            iterable_node=iterable_node,
            iterable_type=iterable_type,
            element_type=iterable_type.key_type,
            kind=IterationKind.DICT_KEYS,
            order=IterationOrder.INSERTION,
        )

    if isinstance(iterable_type, astx.SetType) and isinstance(
        iterable_type.element_type,
        astx.DataType,
    ):
        return ResolvedIteration(
            iterable_node=iterable_node,
            iterable_type=iterable_type,
            element_type=iterable_type.element_type,
            kind=IterationKind.SET,
            order=IterationOrder.UNSPECIFIED,
        )

    if isinstance(iterable_type, astx.GeneratorType):
        return ResolvedIteration(
            iterable_node=iterable_node,
            iterable_type=iterable_type,
            element_type=iterable_type.yield_type,
            kind=IterationKind.GENERATOR,
            is_reiterable=False,
            order=IterationOrder.STABLE,
            cursor_protocol=CursorProtocol.GENERATOR,
        )

    return None


__all__ = ["resolve_iteration_capability"]
