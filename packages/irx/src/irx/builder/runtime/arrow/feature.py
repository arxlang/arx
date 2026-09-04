"""
title: Arrow native runtime feature construction.
"""

from __future__ import annotations

from pathlib import Path

from irx.builder.runtime.arrow.declarations import (
    arrow_external_symbol_specs,
)
from irx.builder.runtime.arrowcpp import (
    arrowcpp_compile_flags,
    arrowcpp_include_dirs,
    arrowcpp_linker_flags,
    arrowcpp_runtime_metadata,
)
from irx.builder.runtime.features import NativeArtifact, RuntimeFeature
from irx.typecheck import typechecked

ARROW_RUNTIME_CAPABILITIES = frozenset(
    {"core", "array", "tensor", "dataframe", "record_batch"}
)


@typechecked
def arrow_native_source_dir() -> Path:
    """
    title: Return the native Arrow runtime source directory.
    returns:
      type: Path
    """
    return (Path(__file__).resolve().parent / "native").resolve()


@typechecked
def build_arrow_native_artifact(capability: str) -> NativeArtifact:
    """
    title: Build the native artifact for one Arrow capability.
    parameters:
      capability:
        type: str
    returns:
      type: NativeArtifact
    """
    if capability not in ARROW_RUNTIME_CAPABILITIES:
        raise ValueError(f"Unknown Arrow runtime capability '{capability}'")

    native_root = arrow_native_source_dir()
    buffer_native_root = native_root.parent.parent / "buffer" / "native"
    return NativeArtifact(
        kind="cxx_source",
        path=native_root / f"irx_arrow_{capability}_runtime.cc",
        include_dirs=(
            native_root,
            buffer_native_root.resolve(),
            *arrowcpp_include_dirs(),
        ),
        compile_flags=arrowcpp_compile_flags(),
    )


@typechecked
def build_arrow_core_runtime_feature() -> RuntimeFeature:
    """
    title: Build the shared Arrow runtime core feature.
    returns:
      type: RuntimeFeature
    """
    return RuntimeFeature(
        name="core",
        symbols=arrow_external_symbol_specs("core"),
        artifacts=(build_arrow_native_artifact("core"),),
        linker_flags=arrowcpp_linker_flags(),
        metadata={
            "canonical_name": "core",
            "opaque_handles": {"error": "irx_arrow_error_handle"},
            **arrowcpp_runtime_metadata(),
        },
    )


__all__ = [
    "ARROW_RUNTIME_CAPABILITIES",
    "arrow_native_source_dir",
    "build_arrow_core_runtime_feature",
    "build_arrow_native_artifact",
]
