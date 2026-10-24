"""
title: Registered opaque exception-context and diagnostic-record runtime.
"""

from pathlib import Path

from llvmlite import ir
from public import private, public

from irx.builder.protocols import VisitorProtocol
from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.typecheck import typechecked


@private
@typechecked
def exception_signature(operation: str) -> ir.FunctionType:
    """
    title: Return one opaque C ABI signature without exposing native layouts.
    parameters:
      operation:
        type: str
    returns:
      type: ir.FunctionType
    """
    pointer = ir.IntType(8).as_pointer()
    output = pointer.as_pointer()
    integer = ir.IntType(32)
    void = ir.VoidType()
    signatures: dict[str, tuple[ir.Type, list[ir.Type]]] = {
        "info_create": (integer, [pointer, pointer, output, integer, output]),
        "info_retain": (void, [pointer]),
        "info_release": (void, [pointer]),
        "info_message": (pointer, [pointer]),
        "context_create": (integer, [output]),
        "context_destroy": (void, [pointer]),
        "raise": (
            integer,
            [
                pointer,
                pointer,
                output,
                pointer,
                integer,
                pointer,
                integer,
                integer,
                pointer,
            ],
        ),
        "reraise": (integer, [pointer]),
        "pending": (integer, [pointer]),
        "matches": (integer, [pointer, pointer]),
        "handled_payload": (pointer, [pointer]),
        "pending_info": (pointer, [pointer]),
        "handler_enter": (pointer, [pointer]),
        "handler_leave": (void, [pointer, pointer]),
        "finally_enter": (pointer, [pointer]),
        "finally_leave": (void, [pointer, pointer, integer]),
        "cleanup_enter": (pointer, [pointer]),
        "cleanup_leave": (void, [pointer, pointer]),
        "pending_take": (pointer, [pointer]),
        "pending_restore": (void, [pointer, pointer]),
        "pending_discard": (void, [pointer, pointer]),
        "trace": (void, [pointer, pointer, integer, integer]),
        "report": (void, [pointer]),
    }
    result, arguments = signatures[operation]
    return ir.FunctionType(result, arguments)


@public
@typechecked
def build_exception_runtime_feature() -> RuntimeFeature:
    """
    title: Register exception ownership and reports without Arrow.
    returns:
      type: RuntimeFeature
    """
    native = Path(__file__).parent / "native"
    classes = native.parents[1] / "classes" / "native"
    symbols: dict[str, ExternalSymbolSpec] = {}
    for operation in (
        "info_create",
        "info_retain",
        "info_release",
        "info_message",
        "context_create",
        "context_destroy",
        "raise",
        "reraise",
        "pending",
        "matches",
        "handled_payload",
        "pending_info",
        "handler_enter",
        "handler_leave",
        "finally_enter",
        "finally_leave",
        "cleanup_enter",
        "cleanup_leave",
        "pending_take",
        "pending_restore",
        "pending_discard",
        "trace",
        "report",
    ):

        def declare(
            visitor: VisitorProtocol, name: str = operation
        ) -> ir.Function:
            """
            title: Declare one checked exception runtime function.
            parameters:
              visitor:
                type: VisitorProtocol
              name:
                type: str
            returns:
              type: ir.Function
            """
            return declare_external_function(
                visitor._llvm.module,
                "irx_exception_" + name,
                exception_signature(name),
            )

        name = "irx_exception_" + operation
        symbols[name] = ExternalSymbolSpec(name, declare)
    return RuntimeFeature(
        name="exceptions",
        symbols=symbols,
        dependencies=("class",),
        artifacts=(
            NativeArtifact(
                "c_source",
                native / "irx_exception_runtime.c",
                include_dirs=(native, classes),
                compile_flags=("-std=c99",),
            ),
        ),
        metadata={
            "protocol": "ARX_EXCEPTION|role|code|type|source|line|col|message",
            "ownership": (
                "retained class payload; immutable diagnostic snapshots"
            ),
            "chain_limit": 32,
            "trace_limit": 64,
        },
    )
