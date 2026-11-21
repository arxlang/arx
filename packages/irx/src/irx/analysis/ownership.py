"""
title: Semantic ownership helpers for runtime-managed values.
summary: Centralize typed access to ownership sidecars without allowing
  lowering to rediscover resource lifetime from AST shape.
"""

from __future__ import annotations

from dataclasses import replace

import astx

from public import public

from irx.analysis.resolved_nodes import (
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    ResourceOwnership,
    SemanticInfo,
    SemanticSymbol,
)
from irx.typecheck import typechecked


@public
@typechecked
def resource_ownership(node: astx.AST | None) -> ResourceOwnership | None:
    """
    title: Return one node's typed resource-ownership sidecar.
    parameters:
      node: Syntax node to process.
    returns: One node's typed resource-ownership sidecar.
    """
    if node is None:
        return None
    semantic = getattr(node, "semantic", None)
    if not isinstance(semantic, SemanticInfo):
        return None
    ownership = semantic.resource_ownership
    return ownership if isinstance(ownership, ResourceOwnership) else None


@public
@typechecked
def symbol_resource_ownership(
    symbol: SemanticSymbol | None,
) -> ResourceOwnership | None:
    """
    title: Return the ownership contract attached to a symbol declaration.
    parameters:
      symbol: Resolved symbol for the operation.
    returns: The ownership contract attached to a symbol declaration.
    """
    if symbol is None or symbol.declaration is None:
        return None
    return resource_ownership(symbol.declaration)


@public
@typechecked
def list_resource_ownership(
    kind: OwnershipKind,
    *,
    owner_symbol_id: str | None = None,
    source_symbol_id: str | None = None,
    transfer_kind: OwnershipTransferKind = OwnershipTransferKind.NONE,
    escape_kind: OwnershipEscapeKind = OwnershipEscapeKind.NONE,
) -> ResourceOwnership:
    """
    title: Build one dynamic-list ownership contract.
    parameters:
      kind: Kind of value or operation.
      owner_symbol_id: Identifier for owner symbol.
      source_symbol_id: Identifier for source symbol.
      transfer_kind: Transfer kind.
      escape_kind: Escape kind.
    returns: Constructed one dynamic-list ownership contract.
    """
    return ResourceOwnership(
        resource_kind=ResourceKind.LIST,
        kind=kind,
        owner_symbol_id=owner_symbol_id,
        source_symbol_id=source_symbol_id,
        transfer_kind=transfer_kind,
        escape_kind=escape_kind,
    )


@public
@typechecked
def string_resource_ownership(
    kind: OwnershipKind,
    *,
    owner_symbol_id: str | None = None,
    source_symbol_id: str | None = None,
    transfer_kind: OwnershipTransferKind = OwnershipTransferKind.NONE,
    escape_kind: OwnershipEscapeKind = OwnershipEscapeKind.NONE,
) -> ResourceOwnership:
    """
    title: Build one string ownership contract.
    parameters:
      kind: Kind of value or operation.
      owner_symbol_id: Identifier for owner symbol.
      source_symbol_id: Identifier for source symbol.
      transfer_kind: Transfer kind.
      escape_kind: Escape kind.
    returns: Constructed one string ownership contract.
    """
    return ResourceOwnership(
        resource_kind=ResourceKind.STRING,
        kind=kind,
        owner_symbol_id=owner_symbol_id,
        source_symbol_id=source_symbol_id,
        transfer_kind=transfer_kind,
        escape_kind=escape_kind,
    )


@public
@typechecked
def transfer_resource_ownership(
    ownership: ResourceOwnership,
    *,
    owner_symbol_id: str | None = None,
    transfer_kind: OwnershipTransferKind,
    escape_kind: OwnershipEscapeKind = OwnershipEscapeKind.NONE,
) -> ResourceOwnership:
    """
    title: Derive one ownership record for a validated transfer boundary.
    parameters:
      ownership: Resolved resource ownership contract.
      owner_symbol_id: Identifier for owner symbol.
      transfer_kind: Transfer kind.
      escape_kind: Escape kind.
    returns: 'Result of this operation: derive one ownership record for a
      validated transfer boundary.'
    """
    return replace(
        ownership,
        owner_symbol_id=(
            ownership.owner_symbol_id
            if owner_symbol_id is None
            else owner_symbol_id
        ),
        transfer_kind=transfer_kind,
        escape_kind=escape_kind,
    )


__all__ = [
    "list_resource_ownership",
    "resource_ownership",
    "string_resource_ownership",
    "symbol_resource_ownership",
    "transfer_resource_ownership",
]
