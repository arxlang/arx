"""
title: Registered status-returning UTF-8 text runtime.
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
from irx.builder.runtime.list.feature import _list_llvm_type
from irx.typecheck import typechecked


@public
@typechecked
def build_text_runtime_feature() -> RuntimeFeature:
    """
    title: Register text operations and their owned-list ABI dependency.
    returns: 'Result of this operation: register text operations and their
      owned-list ABI dependency.'
    """
    native = Path(__file__).resolve().parent / "native"
    symbols: dict[str, ExternalSymbolSpec] = {}
    for name in (
        "validate",
        "len",
        "cached_len",
        "ord",
        "index",
        "cached_index",
        "cache_clear",
        "slice",
        "split",
        "strip",
        "int",
        "status_message",
    ):

        def declare(
            visitor: VisitorProtocol, operation: str = name
        ) -> ir.Function:
            """
            title: Declare one status-returning text operation.
            parameters:
              visitor: Visitor performing the traversal or lowering.
              operation: Operation to resolve or execute.
            returns: 'Result of this operation: declare one status-returning
              text operation.'
            """
            string = visitor._llvm.INT8_TYPE.as_pointer()
            integer = visitor._llvm.INT64_TYPE
            status = visitor._llvm.INT32_TYPE
            parameters: list[ir.Type]
            result: ir.Type = status
            if operation in {"len", "ord"}:
                parameters = [string, integer.as_pointer()]
            elif operation in {"validate", "int"}:
                parameters = [string, integer, integer.as_pointer()]
            elif operation == "index":
                parameters = [string, integer, string.as_pointer()]
            elif operation == "cached_len":
                parameters = [
                    string,
                    string.as_pointer(),
                    integer.as_pointer(),
                ]
            elif operation == "cached_index":
                parameters = [
                    string,
                    integer,
                    string.as_pointer(),
                    string.as_pointer(),
                ]
            elif operation == "cache_clear":
                parameters = [string.as_pointer()]
                result = visitor._llvm.VOID_TYPE
            elif operation == "slice":
                parameters = [
                    string,
                    integer,
                    integer,
                    integer,
                    string.as_pointer(),
                ]
            elif operation == "strip":
                parameters = [string, string, string.as_pointer()]
            elif operation == "split":
                parameters = [
                    string,
                    string,
                    integer,
                    _list_llvm_type(visitor).as_pointer(),
                ]
            elif operation == "status_message":
                parameters = [status]
                result = string
            else:
                raise ValueError(f"unknown text operation: {operation}")
            return declare_external_function(
                visitor._llvm.module,
                f"irx_text_{operation}",
                ir.FunctionType(result, parameters),
            )

        symbol = f"irx_text_{name}"
        symbols[symbol] = ExternalSymbolSpec(symbol, declare)
    return RuntimeFeature(
        name="text",
        symbols=symbols,
        dependencies=("list",),
        artifacts=(
            NativeArtifact(
                kind="c_source",
                path=native / "irx_text_runtime.c",
                include_dirs=(
                    native,
                    native.parent.parent / "list" / "native",
                ),
                compile_flags=("-std=c99",),
            ),
        ),
        metadata={"encoding": "NUL-free UTF-8", "index_unit": "code point"},
    )
