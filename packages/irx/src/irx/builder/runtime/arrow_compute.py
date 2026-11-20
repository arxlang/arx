"""
title: Focused versioned Arrow Compute runtime feature.
summary: >-
  Only shared compute, scalar transport and chunked-handle lifetime code is
  linked. LLVM transports primitive bits and validity, never Arrow C++ layouts.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from llvmlite import ir
from public import private

from irx.builder.runtime.arrowcpp import (
    arrowcpp_compile_flags,
    arrowcpp_include_dirs,
    arrowcpp_linker_flags,
    arrowcpp_runtime_metadata,
)
from irx.builder.runtime.features import (
    ExternalSymbolSpec,
    NativeArtifact,
    RuntimeFeature,
    declare_external_function,
)
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol

COMPUTE_ABI_VERSION = 2

# Return type first; the flat ABI never embeds Arrow or descriptor layouts.
COMPUTE_SIGNATURES: dict[str, tuple[str, ...]] = {
    "irx_arrow_compute_abi_version": ("i32",),
    "irx_arrow_compute_supports": ("i32",) * 8,
    "irx_arrow_compute": (
        *("i32",) * 8,
        "p",
        "i64",
        "i32",
        "i32",
        "p",
        "i64",
        "i32",
        "i32",
        "pp",
        "i64p",
        "i32p",
    ),
    "irx_arrow_chunked_array_retain": ("i32", "p"),
    "irx_arrow_chunked_array_release": ("v", "p"),
    "irx_arrow_last_error": ("p",),
}


@private
@typechecked
def declare_compute_symbol(
    visitor: VisitorProtocol, *, name: str, signature: tuple[str, ...]
) -> ir.Function:
    """
    title: Declare one closed compute ABI signature.
    parameters:
      visitor:
        type: VisitorProtocol
      name:
        type: str
      signature:
        type: tuple[str, Ellipsis]
    returns:
      type: ir.Function
    """
    pointer = ir.IntType(8).as_pointer()
    types: dict[str, ir.Type] = {
        "v": ir.VoidType(),
        "p": pointer,
        "pp": pointer.as_pointer(),
        "i32": ir.IntType(32),
        "i64": ir.IntType(64),
        "i32p": ir.IntType(32).as_pointer(),
        "i64p": ir.IntType(64).as_pointer(),
    }
    return declare_external_function(
        visitor._llvm.module,
        name,
        ir.FunctionType(
            types[signature[0]], [types[item] for item in signature[1:]]
        ),
    )


@private
@typechecked
def build_arrow_compute_runtime_feature() -> RuntimeFeature:
    """
    title: Register shared compute without DataFrame or Parquet dependencies.
    returns:
      type: RuntimeFeature
    """
    native = Path(__file__).parent / "arrow" / "native"
    return RuntimeFeature(
        name="arrow_compute",
        symbols={
            name: ExternalSymbolSpec(
                name,
                partial(
                    declare_compute_symbol, name=name, signature=signature
                ),
            )
            for name, signature in COMPUTE_SIGNATURES.items()
        },
        artifacts=(
            NativeArtifact(
                kind="cxx_source",
                path=native / "irx_arrow_compute.cc",
                include_dirs=(native, *arrowcpp_include_dirs()),
                compile_flags=arrowcpp_compile_flags(),
            ),
        ),
        linker_flags=arrowcpp_linker_flags(),
        metadata={
            "compute_abi": COMPUTE_ABI_VERSION,
            **arrowcpp_runtime_metadata(),
        },
    )
