"""
title: Portable logical schema modeling tests.
"""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from typeguard import TypeCheckError

import astx

from astx.schema import Metadata, ParameterValue


@pytest.mark.parametrize("kind", list(astx.LogicalKind))
def test_logical_kind_is_backend_independent(kind: astx.LogicalKind) -> None:
    """
    title: Every logical family has a stable immutable AST representation.
    parameters:
      kind:
        type: astx.LogicalKind
    """
    descriptor = astx.LogicalType(kind)
    assert descriptor == astx.LogicalType(kind)
    assert hash(descriptor) == hash(astx.LogicalType(kind))
    with pytest.raises(FrozenInstanceError):
        setattr(descriptor, "kind", astx.LogicalKind.NULL)


def test_schema_preserves_binary_metadata_and_empty_fields() -> None:
    """
    title: Schema modeling must preserve binary values without coercion.
    """
    metadata = ((b"\x00\xff", b"\x00\x01\xff"),)
    field = astx.SchemaField(
        "λ",
        astx.LogicalType(astx.LogicalKind.BINARY),
        nullable=True,
        metadata=metadata,
    )
    schema = astx.Schema((field,), metadata=metadata)
    assert schema.fields[0].metadata == schema.metadata == metadata
    assert astx.Schema().fields == ()


def test_schema_runtime_checks_every_collection_item() -> None:
    """
    title: Invalid nested items must fail at the public modeling boundary.
    """
    valid = astx.SchemaField("x", astx.LogicalType(astx.LogicalKind.INT32))
    with pytest.raises(TypeCheckError):
        astx.Schema((valid, cast(astx.SchemaField, "not a field")))
    with pytest.raises(TypeCheckError):
        astx.SchemaField(
            "x", valid.type_, metadata=cast(Metadata, ((b"a", "bad"),))
        )
    with pytest.raises(TypeCheckError):
        astx.LogicalParameter(
            astx.ParameterKind.TYPE_CODES, cast(ParameterValue, (0, "bad"))
        )
    with pytest.raises(TypeCheckError):
        astx.LogicalType(cast(astx.LogicalKind, "int32"))


@pytest.mark.parametrize(
    "container", [astx.ArrayType, astx.ChunkedArrayType, astx.ScalarType]
)
def test_element_container_types_require_descriptors(
    container: type[astx.LogicalValueType],
) -> None:
    """
    title: Element containers carry recursive logical types and nullability.
    parameters:
      container:
        type: type[astx.LogicalValueType]
    """
    type_ = astx.LogicalType(astx.LogicalKind.INT64)
    assert container(type_, nullable=True).element_type == type_
    with pytest.raises(TypeCheckError):
        container(cast(astx.LogicalType, astx.Int64()))


@pytest.mark.parametrize(
    "container", [astx.TableType, astx.RecordBatchType, astx.StreamType]
)
def test_schema_container_types_distinguish_empty_and_dynamic(
    container: type[astx.SchemaValueType],
) -> None:
    """
    title: Unknown schema is not the same as a statically empty schema.
    parameters:
      container:
        type: type[astx.SchemaValueType]
    """
    assert container().schema is None
    assert container(astx.Schema()).schema == astx.Schema()


def test_schema_ast_snapshots_do_not_erase_parameters() -> None:
    """
    title: >-
      Structured AST output must distinguish logical parameters and schemas.
    """
    int_array = astx.ArrayType(astx.LogicalType(astx.LogicalKind.INT32))
    str_array = astx.ArrayType(astx.LogicalType(astx.LogicalKind.STRING))
    assert int_array.get_struct() != str_array.get_struct()
    assert (
        astx.TableType().get_struct()
        != astx.TableType(astx.Schema()).get_struct()
    )
