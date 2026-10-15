"""
title: >-
  Semantic storage contracts for first-class primitive and logical Arrow
  arrays.
"""

from __future__ import annotations

from dataclasses import dataclass

import astx

from public import public

from irx.builtins.collections.array_primitives import (
    ARRAY_PRIMITIVE_TYPE_SPECS,
    AST_LOGICAL_KINDS,
)
from irx.typecheck import typechecked

ARRAY_VALUE_TYPES = {
    kind: scalar
    for scalar, kind in AST_LOGICAL_KINDS.items()
    if kind.value in ARRAY_PRIMITIVE_TYPE_SPECS
}


@public
@typechecked
@dataclass(frozen=True)
class ResolvedArray:
    """
    title: Resolved native operation, conversions and owned result type.
    attributes:
      symbol:
        type: str
      result_type:
        type: astx.DataType
      element_type:
        type: astx.DataType
      scalar_abi_type:
        type: astx.DataType
      type_id:
        type: int
      argument_types:
        type: tuple[astx.DataType, Ellipsis]
      operation:
        type: astx.ArrayOperation | None
      required_features:
        type: tuple[str, Ellipsis]
      required_feature_version:
        type: int
      descriptor:
        type: astx.TypeDescriptorLiteral | None
      arguments:
        type: tuple[astx.Expr, Ellipsis] | None
    """

    symbol: str
    result_type: astx.DataType
    element_type: astx.DataType
    scalar_abi_type: astx.DataType
    type_id: int
    argument_types: tuple[astx.DataType, ...]
    operation: astx.ArrayOperation | None = None
    required_features: tuple[str, ...] = ("core", "array")
    required_feature_version: int = 0x00010600
    descriptor: astx.TypeDescriptorLiteral | None = None
    arguments: tuple[astx.Expr, ...] | None = None


@public
@typechecked
def array_storage(
    type_: astx.LogicalValueType,
) -> tuple[astx.DataType, astx.DataType, int, str] | None:
    """
    title: Resolve native payload or opaque logical scalar array storage.
    parameters:
      type_:
        type: astx.LogicalValueType
    returns:
      type: tuple[astx.DataType, astx.DataType, int, str] | None
    """
    kind = type_.element_type.kind
    scalar = ARRAY_VALUE_TYPES.get(kind)
    if scalar is None:
        return (
            astx.ScalarType(type_.element_type),
            astx.ScalarType(type_.element_type),
            0,
            "scalar",
        )
    spec = ARRAY_PRIMITIVE_TYPE_SPECS[kind.value]
    if kind.value.startswith("float"):
        return scalar(), astx.Float64(), spec.type_id, "double"
    if kind.value.startswith("uint"):
        return scalar(), astx.UInt64(), spec.type_id, "uint"
    return scalar(), astx.Int64(), spec.type_id, "int"
