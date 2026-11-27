"""
title: Minimal dynamic-list metadata and type helpers.
summary: Centralize the small IRX-side list layout contract plus the AST-type
  helpers shared by semantic analysis and lowering.
attributes:
  LIST_FIELD_INDICES: List field indices.
"""

from __future__ import annotations

import astx

from public import private

from irx.typecheck import typechecked

LIST_FIELD_INDICES: dict[str, int] = {
    "data": 0,
    "length": 1,
    "capacity": 2,
    "element_size": 3,
    "element_kind": 4,
}
LIST_RUNTIME_FEATURE = "list"
LIST_APPEND_SYMBOL = "irx_list_append"
LIST_AT_SYMBOL = "irx_list_at"
LIST_CLONE_SYMBOL = "irx_list_clone"
LIST_DESTROY_SYMBOL = "irx_list_destroy"
LIST_STATUS_MESSAGE_SYMBOL = "irx_list_status_message"


@typechecked
def list_element_type(type_: astx.DataType | None) -> astx.DataType | None:
    """
    title: Return one concrete list element type when available.
    parameters:
      type_: Type expression to process.
    returns: One concrete list element type when available.
    """
    if not isinstance(type_, astx.ListType):
        return None
    if len(type_.element_types) != 1:
        return None
    element_type = type_.element_types[0]
    return element_type if isinstance(element_type, astx.DataType) else None


@typechecked
def list_has_concrete_element_type(type_: astx.DataType | None) -> bool:
    """
    title: Return whether one list type has a single concrete element type.
    parameters:
      type_: Type expression to process.
    returns: Whether one list type has a single concrete element type.
    """
    return list_element_type(type_) is not None


@private
@typechecked
def list_supports_owned_element(type_: astx.DataType | None) -> bool:
    """
    title: Check element forms with implemented native copy and drop behavior.
    summary: Numeric and Boolean values copy inline. Strings copy their bytes
      and destroy independently. Nested owners and handles need recursive
      plans.
    parameters:
      type_: Type expression to process.
    returns: 'Result of this operation: check element forms with implemented
      native copy and drop behavior.'
    """
    return isinstance(
        type_,
        (
            astx.Int8,
            astx.Int16,
            astx.Int32,
            astx.Int64,
            astx.UInt8,
            astx.UInt16,
            astx.UInt32,
            astx.UInt64,
            astx.Float16,
            astx.Float32,
            astx.Float64,
            astx.Boolean,
            astx.String,
            astx.UTF8String,
        ),
    )
