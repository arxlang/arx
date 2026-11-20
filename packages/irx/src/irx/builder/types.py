"""
title: LLVM type helpers for llvmliteir codegen.
"""

from __future__ import annotations

from llvmlite import ir
from llvmlite.ir import DoubleType, FloatType, HalfType

try:  # FP128 may not exist depending on llvmlite build.
    from llvmlite.ir import FP128Type
except ImportError:  # pragma: no cover - optional
    FP128Type = None

from irx.typecheck import typechecked


@typechecked
def is_fp_type(type_: ir.Type) -> bool:
    """
    title: Is fp type.
    parameters:
      type_: Type expression to process.
    returns: 'Result of this operation: is fp type.'
    """
    fp_types = [HalfType, FloatType, DoubleType]
    if FP128Type is not None:
        fp_types.append(FP128Type)
    return isinstance(type_, tuple(fp_types))


@typechecked
def is_int_type(type_: ir.Type) -> bool:
    """
    title: Is int type.
    parameters:
      type_: Type expression to process.
    returns: 'Result of this operation: is int type.'
    """
    return isinstance(type_, ir.IntType)


@typechecked
class VariablesLLVM:
    """
    title: Define LLVM representations for supported runtime types.
    attributes:
      FLOAT_TYPE: Float type.
      FLOAT16_TYPE: Float16 type.
      DOUBLE_TYPE: Double type.
      INT8_TYPE: Int8 type.
      INT64_TYPE: Int64 type.
      INT16_TYPE: Int16 type.
      INT32_TYPE: Int32 type.
      VOID_TYPE: Void type.
      BOOLEAN_TYPE: Boolean type.
      UINT8_TYPE: Uint8 type.
      UINT16_TYPE: Uint16 type.
      UINT32_TYPE: Uint32 type.
      UINT64_TYPE: Uint64 type.
      UINT128_TYPE: Uint128 type.
      ASCII_STRING_TYPE: Ascii string type.
      UTF8_STRING_TYPE: Utf8 string type.
      TIME_TYPE: Time type.
      TIMESTAMP_TYPE: Timestamp type.
      DATETIME_TYPE: Datetime type.
      SIZE_T_TYPE: Size t type.
      POINTER_BITS: Pointer bits.
      OPAQUE_POINTER_TYPE: Opaque pointer type.
      BUFFER_OWNER_HANDLE_TYPE: Buffer owner handle type.
      BUFFER_VIEW_TYPE: Buffer view type.
      ARRAY_BUILDER_HANDLE_TYPE: Array builder handle type.
      ARRAY_HANDLE_TYPE: Array handle type.
      ARROW_ARRAY_BUILDER_HANDLE_TYPE: Arrow array builder handle type.
      ARROW_ARRAY_HANDLE_TYPE: Arrow array handle type.
      TENSOR_BUILDER_HANDLE_TYPE: Tensor builder handle type.
      TENSOR_HANDLE_TYPE: Tensor handle type.
      ARROW_TENSOR_BUILDER_HANDLE_TYPE: Arrow tensor builder handle type.
      ARROW_TENSOR_HANDLE_TYPE: Arrow tensor handle type.
      TABLE_HANDLE_TYPE: Table handle type.
      CHUNKED_ARRAY_HANDLE_TYPE: Chunked array handle type.
      ARROW_TABLE_HANDLE_TYPE: Arrow table handle type.
      ARROW_CHUNKED_ARRAY_HANDLE_TYPE: Arrow chunked array handle type.
      context: Context for the operation.
      module: Module to process.
      ir_builder: IR builder.
    """

    FLOAT_TYPE: ir.types.Type
    FLOAT16_TYPE: ir.types.Type
    DOUBLE_TYPE: ir.types.Type
    INT8_TYPE: ir.types.Type
    INT64_TYPE: ir.types.Type
    INT16_TYPE: ir.types.Type
    INT32_TYPE: ir.types.Type
    VOID_TYPE: ir.types.Type
    BOOLEAN_TYPE: ir.types.Type
    UINT8_TYPE: ir.types.Type
    UINT16_TYPE: ir.types.Type
    UINT32_TYPE: ir.types.Type
    UINT64_TYPE: ir.types.Type
    UINT128_TYPE: ir.types.Type
    ASCII_STRING_TYPE: ir.types.Type
    UTF8_STRING_TYPE: ir.types.Type
    TIME_TYPE: ir.types.Type
    TIMESTAMP_TYPE: ir.types.Type
    DATETIME_TYPE: ir.types.Type
    SIZE_T_TYPE: ir.types.Type | None
    POINTER_BITS: int
    OPAQUE_POINTER_TYPE: ir.types.Type
    BUFFER_OWNER_HANDLE_TYPE: ir.types.Type
    BUFFER_VIEW_TYPE: ir.types.Type
    ARRAY_BUILDER_HANDLE_TYPE: ir.types.Type
    ARRAY_HANDLE_TYPE: ir.types.Type
    ARROW_ARRAY_BUILDER_HANDLE_TYPE: ir.types.Type
    ARROW_ARRAY_HANDLE_TYPE: ir.types.Type
    TENSOR_BUILDER_HANDLE_TYPE: ir.types.Type
    TENSOR_HANDLE_TYPE: ir.types.Type
    ARROW_TENSOR_BUILDER_HANDLE_TYPE: ir.types.Type
    ARROW_TENSOR_HANDLE_TYPE: ir.types.Type
    TABLE_HANDLE_TYPE: ir.types.Type
    CHUNKED_ARRAY_HANDLE_TYPE: ir.types.Type
    ARROW_TABLE_HANDLE_TYPE: ir.types.Type
    ARROW_CHUNKED_ARRAY_HANDLE_TYPE: ir.types.Type

    context: ir.context.Context
    module: ir.module.Module
    ir_builder: ir.builder.IRBuilder

    def get_data_type(self, type_name: str) -> ir.types.Type:
        """
        title: Get data type.
        parameters:
          type_name: Name of type.
        returns: Data type.
        """
        if type_name == "float32":
            return self.FLOAT_TYPE
        if type_name == "float16":
            return self.FLOAT16_TYPE
        if type_name in ("double", "float64"):
            return self.DOUBLE_TYPE
        if type_name == "boolean":
            return self.BOOLEAN_TYPE
        if type_name == "int8":
            return self.INT8_TYPE
        if type_name == "int16":
            return self.INT16_TYPE
        if type_name == "int32":
            return self.INT32_TYPE
        if type_name == "int64":
            return self.INT64_TYPE
        if type_name == "char":
            return self.INT8_TYPE
        if type_name in ("string", "stringascii"):
            return self.ASCII_STRING_TYPE
        if type_name == "utf8string":
            return self.UTF8_STRING_TYPE
        if type_name == "uint8":
            return self.UINT8_TYPE
        if type_name == "uint16":
            return self.UINT16_TYPE
        if type_name == "uint32":
            return self.UINT32_TYPE
        if type_name == "uint64":
            return self.UINT64_TYPE
        if type_name == "uint128":
            return self.UINT128_TYPE
        if type_name == "nonetype":
            return self.VOID_TYPE
        if type_name == "date":
            return self.INT32_TYPE
        if type_name == "time":
            return self.TIME_TYPE
        if type_name == "timestamp":
            return self.TIMESTAMP_TYPE
        if type_name == "datetime":
            return self.DATETIME_TYPE

        raise Exception(f"[EE]: Type name {type_name} not valid.")


__all__ = ["VariablesLLVM", "is_fp_type", "is_int_type"]
