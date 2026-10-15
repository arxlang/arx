"""
title: Semantic cleanup shape for nullable by-value resource payloads.
"""

import astx
import pytest

from irx.analysis import analyze, resource_ownership, typed_resource_ownership
from irx.analysis.nullability import aggregate_nullable, managed_nullable
from irx.analysis.ownership import transfer_resource_ownership
from irx.analysis.resolved_nodes import OwnershipKind, OwnershipTransferKind


@pytest.mark.parametrize(
    "payload",
    [
        astx.ListType([astx.Int32()]),
        astx.TensorType(astx.Int32(), shape=(2,)),
        astx.BufferViewType(astx.Int32()),
    ],
)
def test_nullable_aggregate_cleanup_is_explicit(
    payload: astx.DataType,
) -> None:
    """
    title: Preserve aggregate validity through ownership transfers and unwrap.
    parameters:
      payload:
        type: astx.DataType
    """
    optional = astx.NullableType(payload)
    ownership = typed_resource_ownership(optional, OwnershipKind.OWNED)
    assert aggregate_nullable(optional)
    assert not managed_nullable(optional)
    assert ownership.nullable_aggregate
    assert transfer_resource_ownership(
        ownership, transfer_kind=OwnershipTransferKind.MOVE
    ).nullable_aggregate
    argument = astx.Argument("value", optional)
    unwrap = astx.NullableQuery(
        astx.NullableOperation.EXPECT_VALID, astx.Identifier("value")
    )
    body = astx.Block()
    body.append(unwrap)
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype(
                "inspect", astx.Arguments(argument), astx.Int32()
            ),
            body,
        )
    )
    analyze(module)
    borrowed = resource_ownership(unwrap)
    assert borrowed is not None
    assert borrowed.kind is OwnershipKind.BORROWED
    assert not borrowed.nullable_aggregate
