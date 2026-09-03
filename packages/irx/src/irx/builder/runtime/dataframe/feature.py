"""
title: Builtin dataframe runtime feature declarations backed by Arrow.
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


@typechecked
def build_dataframe_runtime_feature() -> RuntimeFeature:
    """
    title: Build the builtin dataframe runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    runtime_root = Path(__file__).resolve().parent
    native_root = (runtime_root.parent / "arrow" / "native").resolve()
    buffer_native_root = (runtime_root.parent / "buffer" / "native").resolve()
    include_dirs = (
        native_root,
        buffer_native_root,
        *arrowcpp_include_dirs(),
    )
    artifacts = (
        NativeArtifact(
            kind="cxx_source",
            path=native_root / "irx_arrow_runtime.cc",
            include_dirs=include_dirs,
            compile_flags=arrowcpp_compile_flags(),
        ),
    )

    return RuntimeFeature(
        name="dataframe",
        symbols=arrow_external_symbol_specs("dataframe"),
        artifacts=artifacts,
        metadata={
            "opaque_handles": {
                "table": "irx_arrow_table_handle",
                "chunked_array": "irx_arrow_chunked_array_handle",
            },
            "canonical_name": "dataframe",
            **arrowcpp_runtime_metadata(),
        },
        linker_flags=arrowcpp_linker_flags(),
    )


__all__ = ["build_dataframe_runtime_feature"]
