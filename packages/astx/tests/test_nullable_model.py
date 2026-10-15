"""
title: Reusable nullable types and validity expression contracts.
"""

from __future__ import annotations

from typing import cast

import pytest

from typeguard import TypeCheckError

import astx

from astx.types import AnyType


def test_nullable_type_and_queries_preserve_model() -> None:
    """
    title: Model nullable function results without choosing an ABI layout.
    """
    payload = astx.Int32()
    optional = astx.NullableType(payload, alias_name="OptionalCount")
    assert optional.payload_type is payload
    assert optional.alias_name == "OptionalCount"
    assert "NullableType" in optional.get_struct()
    prototype = astx.FunctionPrototype("count", astx.Arguments(), optional)
    assert prototype.return_type is optional
    for operation in astx.NullableOperation:
        query = astx.NullableQuery(operation, astx.Identifier("count"))
        assert query.operation is operation
        assert f"NullableQuery[{operation.value}]" in query.get_struct()
        if operation is astx.NullableOperation.EXPECT_VALID:
            assert type(query.type_) is AnyType
        else:
            assert isinstance(query.type_, astx.Boolean)


def test_nullable_model_rejects_invalid_runtime_inputs() -> None:
    """
    title: Enforce ASTx argument contracts through the owning wrapper.
    """
    with pytest.raises(TypeCheckError):
        astx.NullableType(cast(astx.DataType, object()))
    with pytest.raises(TypeCheckError):
        astx.NullableQuery(
            cast(astx.NullableOperation, "is_null"), astx.LiteralNone()
        )
    with pytest.raises(TypeCheckError):
        astx.NullableQuery(
            astx.NullableOperation.IS_VALID, cast(astx.Expr, object())
        )


def test_bare_return_is_distinct_from_literal_null() -> None:
    """
    title: >-
      Preserve absence of a return expression independently of null values.
    """
    bare = astx.FunctionReturn(None)
    explicit = astx.FunctionReturn(astx.LiteralNone())
    assert bare.value is None
    assert isinstance(explicit.value, astx.LiteralNone)
    assert bare.get_struct(simplified=True) == {"RETURN": {}}
