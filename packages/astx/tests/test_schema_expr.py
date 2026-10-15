"""
title: Reusable descriptor expression model and runtime type contracts.
"""

from __future__ import annotations

from typing import cast

import pytest

from typeguard import TypeCheckError

import astx


@pytest.mark.parametrize(
    "type_", [astx.SchemaType(), astx.FieldType(), astx.TypeDescriptorType()]
)
def test_descriptor_types_can_be_function_results(type_: astx.AnyType) -> None:
    """
    title: Descriptor type nodes satisfy the reusable callable type contract.
    parameters:
      type_:
        type: astx.AnyType
    """
    prototype = astx.FunctionPrototype("descriptor", astx.Arguments(), type_)
    assert prototype.return_type is type_


def test_literals_and_conversion_preserve_complete_snapshots() -> None:
    """
    title: >-
      Typed nodes retain metadata and canonical model input without a backend.
    """
    field = astx.SchemaField(
        "x",
        astx.LogicalType(astx.LogicalKind.INT32),
        nullable=True,
        metadata=((b"\0", b"\xff"),),
    )
    schema = astx.Schema((field,))
    assert "ff" in str(astx.SchemaLiteral(schema).get_struct())
    assert "FieldLiteral" in astx.FieldLiteral(field).get_struct()
    literal = astx.TypeDescriptorLiteral(field.type_)
    assert isinstance(literal.type_, astx.TypeDescriptorType)
    query = astx.DescriptorQuery(
        astx.DescriptorOperation.FIELD_NAME, (astx.FieldLiteral(field),)
    )
    assert isinstance(query.type_, astx.String)
    assert (
        "DescriptorCompatibility"
        in astx.DescriptorCompatibility(schema, schema).get_struct()
    )


def test_descriptor_collection_items_are_runtime_checked() -> None:
    """
    title: >-
      Incorrect collection items cannot bypass the ASTx typechecking wrapper.
    """
    arguments = cast(tuple[astx.Expr, ...], (astx.LiteralInt32(1), object()))
    with pytest.raises(TypeCheckError):
        astx.DescriptorQuery(astx.DescriptorOperation.EQUAL, arguments)
    with pytest.raises(TypeCheckError):
        astx.SchemaLiteral(cast(astx.Schema, object()))
    with pytest.raises(TypeCheckError):
        astx.DescriptorCompatibility(
            astx.Schema(), cast(astx.Schema, object())
        )
