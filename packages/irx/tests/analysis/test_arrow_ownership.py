"""
title: Semantic ownership contracts for Arrow handle families.
"""

from __future__ import annotations

import json

from pathlib import Path
from typing import cast

import pytest

from irx.analysis import (
    ARROW_RESOURCE_CONTRACTS,
    LIST_RESOURCE_CONTRACT,
    STRING_RESOURCE_CONTRACT,
    OwnershipEscapeKind,
    OwnershipKind,
    OwnershipTransferKind,
    ResourceKind,
    ResourceMutability,
    ResourceSharingKind,
    arrow_resource_contract,
    arrow_resource_ownership,
    list_resource_ownership,
    string_resource_ownership,
    transfer_resource_ownership,
)
from typeguard import TypeCheckError

ROOT = Path(__file__).parents[4]
ABI_MANIFEST = (
    ROOT
    / "packages"
    / "irx"
    / "src"
    / "irx"
    / "builder"
    / "runtime"
    / "arrow"
    / "abi.json"
)


def arrow_handle_records() -> tuple[dict[str, object], ...]:
    """
    title: Load the canonical Arrow opaque-handle records for parity checks.
    returns:
      type: tuple[dict[str, object], Ellipsis]
    """
    manifest = cast(
        dict[str, object],
        json.loads(ABI_MANIFEST.read_text(encoding="utf-8")),
    )
    records = manifest.get("handles")
    assert isinstance(records, list)
    assert all(isinstance(record, dict) for record in records)
    return tuple(cast(list[dict[str, object]], records))


def test_resource_kinds_cover_every_arrow_handle_family() -> None:
    """
    title: Semantic resource kinds should exactly cover the ABI handle set.
    """
    manifest_kinds = {record["name"] for record in arrow_handle_records()}
    semantic_kinds = {kind.value for kind in ARROW_RESOURCE_CONTRACTS}

    assert semantic_kinds == manifest_kinds
    assert ResourceKind.LIST not in ARROW_RESOURCE_CONTRACTS
    assert ResourceKind.STRING not in ARROW_RESOURCE_CONTRACTS


def test_arrow_resource_contracts_match_the_canonical_abi_manifest() -> None:
    """
    title: Arrow semantic cleanup and retain contracts should match the ABI.
    """
    for record in arrow_handle_records():
        name = record["name"]
        ownership = record["ownership"]
        assert isinstance(name, str)
        assert isinstance(ownership, str)
        resource_kind = ResourceKind(name)
        contract = arrow_resource_contract(resource_kind)

        assert contract.resource_kind is resource_kind
        assert contract.cleanup_intrinsic == record["release"]
        assert contract.retain_intrinsic == record["retain"]
        assert contract.sharing_kind.value == ownership
        expected_mutability = (
            ResourceMutability.IMMUTABLE
            if ownership == "shared"
            else ResourceMutability.MUTABLE
        )
        assert contract.mutability is expected_mutability


def test_owned_arrow_resource_has_complete_descriptor_and_root() -> None:
    """
    title: Owned Arrow values should carry complete static and flow metadata.
    """
    ownership = arrow_resource_ownership(
        ResourceKind.ARRAY,
        OwnershipKind.OWNED,
        owner_symbol_id="array-owner",
    )

    assert ownership.resource_kind is ResourceKind.ARRAY
    assert ownership.kind is OwnershipKind.OWNED
    assert ownership.sharing_kind is ResourceSharingKind.SHARED
    assert ownership.mutability is ResourceMutability.IMMUTABLE
    assert ownership.cleanup_intrinsic == "irx_arrow_array_release"
    assert ownership.retain_intrinsic == "irx_arrow_array_retain"
    assert ownership.owner_symbol_id == "array-owner"
    assert ownership.owner_root_symbol_id == "array-owner"
    assert ownership.transfer_kind is OwnershipTransferKind.NONE
    assert ownership.escape_kind is OwnershipEscapeKind.NONE


def test_unique_arrow_resource_is_affine_and_mutable() -> None:
    """
    title: Arrow builders should be mutable unique resources without retain.
    """
    ownership = arrow_resource_ownership(
        ResourceKind.ARRAY_BUILDER,
        OwnershipKind.OWNED,
    )

    assert ownership.sharing_kind is ResourceSharingKind.UNIQUE
    assert ownership.mutability is ResourceMutability.MUTABLE
    assert ownership.retain_intrinsic is None
    assert ownership.cleanup_intrinsic == "irx_arrow_array_builder_release"


def test_transfer_preserves_contract_and_explicit_owner_root() -> None:
    """
    title: Transfers should retain their descriptor and original owner root.
    """
    borrowed = arrow_resource_ownership(
        ResourceKind.TENSOR,
        OwnershipKind.BORROWED,
        owner_symbol_id="view",
        owner_root_symbol_id="tensor-root",
        source_symbol_id="tensor-source",
        transfer_kind=OwnershipTransferKind.BORROW,
    )

    moved = transfer_resource_ownership(
        borrowed,
        owner_symbol_id="result",
        transfer_kind=OwnershipTransferKind.MOVE,
        escape_kind=OwnershipEscapeKind.RETURN,
    )

    assert moved.resource_kind is ResourceKind.TENSOR
    assert moved.cleanup_intrinsic == "irx_arrow_tensor_release"
    assert moved.retain_intrinsic == "irx_arrow_tensor_retain"
    assert moved.owner_symbol_id == "result"
    assert moved.owner_root_symbol_id == "tensor-root"
    assert moved.transfer_kind is OwnershipTransferKind.MOVE
    assert moved.escape_kind is OwnershipEscapeKind.RETURN


def test_existing_resource_helpers_populate_complete_contracts() -> None:
    """
    title: Existing list and string ownership should use typed descriptors.
    """
    list_ownership = list_resource_ownership(
        OwnershipKind.OWNED,
        owner_symbol_id="list-owner",
    )
    string_ownership = string_resource_ownership(OwnershipKind.STATIC)

    assert list_ownership.cleanup_intrinsic == "irx_list_destroy"
    assert list_ownership.owner_root_symbol_id == "list-owner"
    assert list_ownership.sharing_kind is ResourceSharingKind.UNIQUE
    assert list_ownership.mutability is ResourceMutability.MUTABLE
    assert string_ownership.cleanup_intrinsic == "free"
    assert string_ownership.sharing_kind is ResourceSharingKind.UNIQUE
    assert string_ownership.mutability is ResourceMutability.IMMUTABLE
    assert LIST_RESOURCE_CONTRACT.resource_kind is ResourceKind.LIST
    assert STRING_RESOURCE_CONTRACT.resource_kind is ResourceKind.STRING


def test_non_arrow_resource_kind_is_rejected() -> None:
    """
    title: Arrow ownership construction should reject other resource families.
    """
    with pytest.raises(ValueError, match="is not an Arrow handle"):
        arrow_resource_ownership(ResourceKind.LIST, OwnershipKind.OWNED)


def test_arrow_resource_factory_runtime_checks_enum_arguments() -> None:
    """
    title: Arrow ownership factories should reject invalid runtime enum values.
    """
    with pytest.raises(TypeCheckError):
        arrow_resource_ownership(
            "array",  # type: ignore[arg-type]
            OwnershipKind.OWNED,
        )


def test_moved_is_an_explicit_semantic_ownership_state() -> None:
    """
    title: Moved Arrow bindings should have a fail-closed semantic state.
    """
    ownership = arrow_resource_ownership(
        ResourceKind.STREAM,
        OwnershipKind.MOVED,
        owner_symbol_id="stream",
        transfer_kind=OwnershipTransferKind.MOVE,
    )

    assert ownership.kind is OwnershipKind.MOVED
    assert ownership.sharing_kind is ResourceSharingKind.UNIQUE
    assert ownership.retain_intrinsic is None
