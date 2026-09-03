"""
title: LLVM declarations for the generated Arrow runtime ABI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from llvmlite import ir

from irx.builder.runtime.arrow.llvm_abi_generated import (
    LLVM_FEATURE_SYMBOLS,
    LLVM_HANDLE_TYPES,
    LLVM_SIGNATURES,
)
from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    declare_external_function,
)
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@typechecked
def arrow_llvm_type(visitor: VisitorProtocol, type_token: str) -> ir.Type:
    """
    title: Resolve one generated Arrow ABI token to an LLVM type.
    parameters:
      visitor:
        type: VisitorProtocol
      type_token:
        type: str
    returns:
      type: ir.Type
    """
    scalar_types = {
        "status": visitor._llvm.INT32_TYPE,
        "status_category": visitor._llvm.INT32_TYPE,
        "uint32": visitor._llvm.UINT32_TYPE,
        "int32": visitor._llvm.INT32_TYPE,
        "int64": visitor._llvm.INT64_TYPE,
        "uint64": visitor._llvm.UINT64_TYPE,
        "double": visitor._llvm.DOUBLE_TYPE,
        "void": visitor._llvm.VOID_TYPE,
    }
    scalar_type = scalar_types.get(type_token)
    if scalar_type is not None:
        return scalar_type

    if type_token in {
        "c_string",
        "const_void",
        "void_pointer",
        "const_arrow_schema",
        "arrow_schema",
        "const_arrow_array",
        "arrow_array",
    }:
        return visitor._llvm.OPAQUE_POINTER_TYPE
    if type_token == "c_string_pointer":
        return visitor._llvm.ASCII_STRING_TYPE.as_pointer()
    if type_token in {"int64_pointer", "const_int64_pointer"}:
        return visitor._llvm.INT64_TYPE.as_pointer()
    if type_token == "const_int64_output":
        return visitor._llvm.INT64_TYPE.as_pointer().as_pointer()
    if type_token in {
        "handle_kind_pointer",
        "int32_pointer",
        "ownership_pointer",
        "status_pointer",
    }:
        return visitor._llvm.INT32_TYPE.as_pointer()
    if type_token == "const_void_pointer":
        return visitor._llvm.OPAQUE_POINTER_TYPE.as_pointer()
    if type_token == "buffer_view":
        return visitor._llvm.BUFFER_VIEW_TYPE.as_pointer()

    for handle_name in LLVM_HANDLE_TYPES:
        if type_token in {handle_name, f"const_{handle_name}"}:
            return visitor._llvm.OPAQUE_POINTER_TYPE
        if type_token == f"{handle_name}_pointer":
            return visitor._llvm.OPAQUE_POINTER_TYPE.as_pointer()
    raise ValueError(f"Unknown generated Arrow ABI type '{type_token}'")


@typechecked
@dataclass(frozen=True)
class ArrowSymbolDeclaration:
    """
    title: Declare one generated Arrow runtime symbol in an LLVM module.
    attributes:
      name:
        type: str
      return_type:
        type: str
      parameter_types:
        type: tuple[str, Ellipsis]
    """

    name: str
    return_type: str
    parameter_types: tuple[str, ...]

    def __call__(self, visitor: VisitorProtocol) -> ir.Function:
        """
        title: Materialize the generated symbol declaration.
        parameters:
          visitor:
            type: VisitorProtocol
        returns:
          type: ir.Function
        """
        function_type = ir.FunctionType(
            arrow_llvm_type(visitor, self.return_type),
            [
                arrow_llvm_type(visitor, type_token)
                for type_token in self.parameter_types
            ],
        )
        return declare_external_function(
            visitor._llvm.module,
            self.name,
            function_type,
        )


@typechecked
def arrow_external_symbol_specs(
    feature_name: str,
) -> dict[str, ExternalSymbolSpec]:
    """
    title: Build generated LLVM symbol specifications for a runtime feature.
    parameters:
      feature_name:
        type: str
    returns:
      type: dict[str, ExternalSymbolSpec]
    """
    names = LLVM_FEATURE_SYMBOLS.get(feature_name)
    if names is None:
        raise ValueError(f"Unknown Arrow runtime feature '{feature_name}'")

    result: dict[str, ExternalSymbolSpec] = {}
    for name in names:
        return_type, parameter_types = LLVM_SIGNATURES[name]
        declaration = ArrowSymbolDeclaration(
            name,
            return_type,
            parameter_types,
        )
        result[name] = ExternalSymbolSpec(name, declaration)
    return result


__all__ = [
    "ArrowSymbolDeclaration",
    "arrow_external_symbol_specs",
    "arrow_llvm_type",
]
