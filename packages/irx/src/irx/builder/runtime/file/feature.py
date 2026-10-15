"""
title: Registered native text-file runtime declarations.
"""

from pathlib import Path

from llvmlite import ir
from public import public

from irx.builder.protocols import VisitorProtocol
from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.typecheck import typechecked

FILE_ERROR_CAPACITY = 256


@public
@typechecked
def build_file_runtime_feature() -> RuntimeFeature:
    """
    title: Declare the optional checked C stdio runtime.
    returns:
      type: RuntimeFeature
    """
    native = Path(__file__).resolve().parent / "native"
    symbols: dict[str, ExternalSymbolSpec] = {}
    for name in ("open", "read", "write", "flush", "close", "release"):
        symbol_name = f"irx_file_{name}"

        def declare(
            visitor: VisitorProtocol,
            operation: str = name,
        ) -> ir.Function:
            """
            title: Declare a file operation with fixed-width output slots.
            parameters:
              visitor:
                type: VisitorProtocol
              operation:
                type: str
            returns:
              type: ir.Function
            """
            pointer = visitor._llvm.OPAQUE_POINTER_TYPE
            cstring = visitor._llvm.INT8_TYPE.as_pointer()
            parameters: list[ir.Type]
            if operation == "open":
                parameters = [cstring, cstring, pointer.as_pointer(), cstring]
            elif operation == "read":
                parameters = [pointer, cstring.as_pointer(), cstring]
            elif operation == "write":
                parameters = [
                    pointer,
                    cstring,
                    visitor._llvm.INT64_TYPE.as_pointer(),
                    cstring,
                ]
            else:
                parameters = [pointer, cstring]
            return declare_external_function(
                visitor._llvm.module,
                f"irx_file_{operation}",
                ir.FunctionType(visitor._llvm.INT32_TYPE, parameters),
            )

        symbols[symbol_name] = ExternalSymbolSpec(symbol_name, declare)
    return RuntimeFeature(
        name="file",
        symbols=symbols,
        artifacts=(
            NativeArtifact(
                kind="c_source",
                path=native / "irx_file_runtime.c",
                include_dirs=(native,),
                compile_flags=("-std=c99",),
            ),
        ),
        metadata={
            "ownership": "single owner; close then release",
            "encoding": "UTF-8",
        },
    )
