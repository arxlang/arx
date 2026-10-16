"""
title: Native class lifetime feature declarations.
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


@public
@typechecked
def build_class_runtime_feature() -> RuntimeFeature:
    """
    title: Declare checked reference-counted class operations.
    returns:
      type: RuntimeFeature
    """
    native = Path(__file__).parent / "native"
    symbols: dict[str, ExternalSymbolSpec] = {}
    for name in (
        "create",
        "retain",
        "release",
        "require",
        "complete",
        "completed",
        "record",
    ):

        def declare(
            visitor: VisitorProtocol, operation: str = name
        ) -> ir.Function:
            """
            title: Declare one native class ABI entry point.
            parameters:
              visitor:
                type: VisitorProtocol
              operation:
                type: str
            returns:
              type: ir.Function
            """
            pointer = visitor._llvm.INT8_TYPE.as_pointer()
            integer = visitor._llvm.INT32_TYPE
            result: ir.Type = integer
            parameters: list[ir.Type] = [pointer, pointer]
            if operation == "create":
                drop = ir.FunctionType(
                    integer, [pointer, pointer]
                ).as_pointer()
                parameters = [
                    visitor._llvm.SIZE_T_TYPE,
                    drop,
                    pointer.as_pointer(),
                    pointer,
                ]
            elif operation in {"complete", "completed"}:
                parameters = [pointer]
                if operation == "complete":
                    result = visitor._llvm.VOID_TYPE
            elif operation == "record":
                parameters = [integer, pointer, integer.as_pointer(), pointer]
                result = visitor._llvm.VOID_TYPE
            return declare_external_function(
                visitor._llvm.module,
                f"irx_class_{operation}",
                ir.FunctionType(result, parameters),
            )

        symbol = f"irx_class_{name}"
        symbols[symbol] = ExternalSymbolSpec(symbol, declare)
    return RuntimeFeature(
        name="class",
        symbols=symbols,
        artifacts=(
            NativeArtifact(
                "c_source",
                native / "irx_class_runtime.c",
                include_dirs=(native,),
                compile_flags=("-std=c99",),
            ),
        ),
    )
