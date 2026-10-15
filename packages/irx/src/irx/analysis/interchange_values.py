"""
title: Closed source interchange signatures with checked expected field types.
"""

from __future__ import annotations

import astx

from public import public

from irx.analysis.array_values import array_storage
from irx.analysis.schema_types import BIT_WIDTHS
from irx.analysis.types import is_signed_integer_type, same_type
from irx.typecheck import typechecked


@public
@typechecked
def interchange_signature(
    node: astx.TabularQuery, types: tuple[astx.DataType, ...]
) -> tuple[str, astx.DataType] | None:
    """
    title: Validate owner categories and exact bitmap/value buffer storage.
    parameters:
      node:
        type: astx.TabularQuery
      types:
        type: tuple[astx.DataType, Ellipsis]
    returns:
      type: tuple[str, astx.DataType] | None
    """
    operation = node.operation
    if operation not in {
        astx.TabularOperation.EXPORT_C_DATA,
        astx.TabularOperation.IMPORT_C_DATA,
        astx.TabularOperation.WITH_VALIDITY,
        astx.TabularOperation.FROM_BUFFERS,
    }:
        return None
    byte_type = astx.ArrayType(astx.LogicalType(astx.LogicalKind.UINT8))
    if operation is astx.TabularOperation.EXPORT_C_DATA:
        if not isinstance(types[0], astx.ArrayType):
            raise ValueError("export_c_data requires an array")
        return "irx_arrow_c_data_from_array", astx.CDataType()
    if operation is astx.TabularOperation.WITH_VALIDITY:
        if (
            not isinstance(types[0], astx.ArrayType)
            or not same_type(types[1], byte_type)
            or not is_signed_integer_type(types[2])
        ):
            raise ValueError(
                "array_with_validity requires an array, array[u8] "
                "and bit offset"
            )
        return "irx_arrow_array_with_validity", astx.ArrayType(
            types[0].element_type, nullable=True
        )
    index = 1 if operation is astx.TabularOperation.IMPORT_C_DATA else 0
    field = node.arguments[index]
    if not isinstance(field, astx.FieldLiteral):
        raise ValueError("array import requires a literal expected field")
    result = astx.ArrayType(field.value.type_, nullable=field.value.nullable)
    if array_storage(result) is None:
        raise ValueError("array import storage is not executable")
    if operation is astx.TabularOperation.IMPORT_C_DATA:
        if not isinstance(types[0], astx.CDataType):
            raise ValueError("array_from_c_data requires a c_data owner")
    elif not all(same_type(t, byte_type) for t in types[1:3]) or not all(
        is_signed_integer_type(t) for t in types[3:]
    ):
        raise ValueError(
            "array_from_buffers requires byte arrays and signed length/offset"
        )
    elif field.value.type_.kind not in set(BIT_WIDTHS) | {
        astx.LogicalKind.FIXED_BINARY
    }:
        raise ValueError(
            "array_from_buffers requires fixed-width or packed Boolean storage"
        )
    return f"irx_arrow_{operation.value}", result
