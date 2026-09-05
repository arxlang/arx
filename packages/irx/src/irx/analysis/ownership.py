"""
title: Semantic ownership helpers for runtime-managed values.
summary: >-
  Centralize typed access to ownership sidecars without allowing lowering to
  rediscover resource lifetime from AST shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType

import astx

from public import public

from irx.analysis.resolved_nodes import (
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResourceContract,
    ResourceKind,
    ResourceMutability,
    ResourceOwnership,
    ResourceSharingKind,
    SemanticInfo,
    SemanticSymbol,
)
from irx.typecheck import typechecked

ARROW_RESOURCE_CONTRACTS: Mapping[ResourceKind, ResourceContract] = (
    MappingProxyType(
        {
            ResourceKind.ERROR: ResourceContract(
                ResourceKind.ERROR,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_error_release",
                "irx_arrow_error_retain",
            ),
            ResourceKind.TYPE: ResourceContract(
                ResourceKind.TYPE,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_type_release",
                "irx_arrow_type_retain",
            ),
            ResourceKind.SCHEMA: ResourceContract(
                ResourceKind.SCHEMA,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_schema_release",
                "irx_arrow_schema_retain",
            ),
            ResourceKind.SCALAR: ResourceContract(
                ResourceKind.SCALAR,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_scalar_release",
                "irx_arrow_scalar_retain",
            ),
            ResourceKind.ARRAY_BUILDER: ResourceContract(
                ResourceKind.ARRAY_BUILDER,
                ResourceSharingKind.UNIQUE,
                ResourceMutability.MUTABLE,
                "irx_arrow_array_builder_release",
                None,
            ),
            ResourceKind.ARRAY: ResourceContract(
                ResourceKind.ARRAY,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_array_release",
                "irx_arrow_array_retain",
            ),
            ResourceKind.CHUNKED_ARRAY: ResourceContract(
                ResourceKind.CHUNKED_ARRAY,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_chunked_array_release",
                "irx_arrow_chunked_array_retain",
            ),
            ResourceKind.RECORD_BATCH: ResourceContract(
                ResourceKind.RECORD_BATCH,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_record_batch_release",
                "irx_arrow_record_batch_retain",
            ),
            ResourceKind.TABLE: ResourceContract(
                ResourceKind.TABLE,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_table_release",
                "irx_arrow_table_retain",
            ),
            ResourceKind.TENSOR_BUILDER: ResourceContract(
                ResourceKind.TENSOR_BUILDER,
                ResourceSharingKind.UNIQUE,
                ResourceMutability.MUTABLE,
                "irx_arrow_tensor_builder_release",
                None,
            ),
            ResourceKind.TENSOR: ResourceContract(
                ResourceKind.TENSOR,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_tensor_release",
                "irx_arrow_tensor_retain",
            ),
            ResourceKind.STREAM: ResourceContract(
                ResourceKind.STREAM,
                ResourceSharingKind.UNIQUE,
                ResourceMutability.MUTABLE,
                "irx_arrow_stream_release",
                None,
            ),
            ResourceKind.DATASET: ResourceContract(
                ResourceKind.DATASET,
                ResourceSharingKind.SHARED,
                ResourceMutability.IMMUTABLE,
                "irx_arrow_dataset_release",
                "irx_arrow_dataset_retain",
            ),
            ResourceKind.EXECUTION_PLAN: ResourceContract(
                ResourceKind.EXECUTION_PLAN,
                ResourceSharingKind.UNIQUE,
                ResourceMutability.MUTABLE,
                "irx_arrow_execution_plan_release",
                None,
            ),
        }
    )
)

LIST_RESOURCE_CONTRACT = ResourceContract(
    ResourceKind.LIST,
    ResourceSharingKind.UNIQUE,
    ResourceMutability.MUTABLE,
    "irx_list_destroy",
    None,
)
STRING_RESOURCE_CONTRACT = ResourceContract(
    ResourceKind.STRING,
    ResourceSharingKind.UNIQUE,
    ResourceMutability.IMMUTABLE,
    "free",
    None,
)


@public
@typechecked
def resource_ownership(node: astx.AST | None) -> ResourceOwnership | None:
    """
    title: Return one node's typed resource-ownership sidecar.
    parameters:
      node:
        type: astx.AST | None
    returns:
      type: ResourceOwnership | None
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
      symbol:
        type: SemanticSymbol | None
    returns:
      type: ResourceOwnership | None
    """
    if symbol is None or symbol.declaration is None:
        return None
    return resource_ownership(symbol.declaration)


@public
@typechecked
def build_resource_ownership(
    contract: ResourceContract,
    kind: OwnershipKind,
    *,
    owner_symbol_id: str | None = None,
    owner_root_symbol_id: str | None = None,
    source_symbol_id: str | None = None,
    transfer_kind: OwnershipTransferKind = OwnershipTransferKind.NONE,
    escape_kind: OwnershipEscapeKind = OwnershipEscapeKind.NONE,
) -> ResourceOwnership:
    """
    title: Build ownership metadata from one canonical resource contract.
    parameters:
      contract:
        type: ResourceContract
      kind:
        type: OwnershipKind
      owner_symbol_id:
        type: str | None
      owner_root_symbol_id:
        type: str | None
      source_symbol_id:
        type: str | None
      transfer_kind:
        type: OwnershipTransferKind
      escape_kind:
        type: OwnershipEscapeKind
    returns:
      type: ResourceOwnership
    """
    resolved_root = owner_root_symbol_id
    if resolved_root is None:
        resolved_root = owner_symbol_id
    if resolved_root is None:
        resolved_root = source_symbol_id
    return ResourceOwnership(
        resource_kind=contract.resource_kind,
        kind=kind,
        sharing_kind=contract.sharing_kind,
        mutability=contract.mutability,
        cleanup_intrinsic=contract.cleanup_intrinsic,
        retain_intrinsic=contract.retain_intrinsic,
        owner_symbol_id=owner_symbol_id,
        owner_root_symbol_id=resolved_root,
        source_symbol_id=source_symbol_id,
        transfer_kind=transfer_kind,
        escape_kind=escape_kind,
    )


@public
@typechecked
def arrow_resource_contract(resource_kind: ResourceKind) -> ResourceContract:
    """
    title: Return the canonical lifecycle contract for one Arrow handle kind.
    parameters:
      resource_kind:
        type: ResourceKind
    returns:
      type: ResourceContract
    """
    contract = ARROW_RESOURCE_CONTRACTS.get(resource_kind)
    if contract is None:
        raise ValueError(
            f"resource kind '{resource_kind.value}' is not an Arrow handle"
        )
    return contract


@public
@typechecked
def arrow_resource_ownership(
    resource_kind: ResourceKind,
    kind: OwnershipKind,
    *,
    owner_symbol_id: str | None = None,
    owner_root_symbol_id: str | None = None,
    source_symbol_id: str | None = None,
    transfer_kind: OwnershipTransferKind = OwnershipTransferKind.NONE,
    escape_kind: OwnershipEscapeKind = OwnershipEscapeKind.NONE,
) -> ResourceOwnership:
    """
    title: Build semantic ownership for one canonical Arrow handle family.
    parameters:
      resource_kind:
        type: ResourceKind
      kind:
        type: OwnershipKind
      owner_symbol_id:
        type: str | None
      owner_root_symbol_id:
        type: str | None
      source_symbol_id:
        type: str | None
      transfer_kind:
        type: OwnershipTransferKind
      escape_kind:
        type: OwnershipEscapeKind
    returns:
      type: ResourceOwnership
    """
    return build_resource_ownership(
        arrow_resource_contract(resource_kind),
        kind,
        owner_symbol_id=owner_symbol_id,
        owner_root_symbol_id=owner_root_symbol_id,
        source_symbol_id=source_symbol_id,
        transfer_kind=transfer_kind,
        escape_kind=escape_kind,
    )


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
      kind:
        type: OwnershipKind
      owner_symbol_id:
        type: str | None
      source_symbol_id:
        type: str | None
      transfer_kind:
        type: OwnershipTransferKind
      escape_kind:
        type: OwnershipEscapeKind
    returns:
      type: ResourceOwnership
    """
    return build_resource_ownership(
        LIST_RESOURCE_CONTRACT,
        kind,
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
      kind:
        type: OwnershipKind
      owner_symbol_id:
        type: str | None
      source_symbol_id:
        type: str | None
      transfer_kind:
        type: OwnershipTransferKind
      escape_kind:
        type: OwnershipEscapeKind
    returns:
      type: ResourceOwnership
    """
    return build_resource_ownership(
        STRING_RESOURCE_CONTRACT,
        kind,
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
      ownership:
        type: ResourceOwnership
      owner_symbol_id:
        type: str | None
      transfer_kind:
        type: OwnershipTransferKind
      escape_kind:
        type: OwnershipEscapeKind
    returns:
      type: ResourceOwnership
    """
    resolved_owner = (
        ownership.owner_symbol_id
        if owner_symbol_id is None
        else owner_symbol_id
    )
    resolved_root = ownership.owner_root_symbol_id
    if resolved_root is None:
        resolved_root = resolved_owner
    if resolved_root is None:
        resolved_root = ownership.source_symbol_id
    return replace(
        ownership,
        owner_symbol_id=resolved_owner,
        owner_root_symbol_id=resolved_root,
        transfer_kind=transfer_kind,
        escape_kind=escape_kind,
    )


__all__ = [
    "ARROW_RESOURCE_CONTRACTS",
    "LIST_RESOURCE_CONTRACT",
    "STRING_RESOURCE_CONTRACT",
    "arrow_resource_contract",
    "arrow_resource_ownership",
    "build_resource_ownership",
    "list_resource_ownership",
    "resource_ownership",
    "string_resource_ownership",
    "symbol_resource_ownership",
    "transfer_resource_ownership",
]
