"""
title: Builtin dataframe runtime feature declarations backed by Arrow.
"""

from __future__ import annotations

from irx.builder.runtime.arrow.declarations import (
    arrow_external_symbol_specs,
)
from irx.builder.runtime.arrow.feature import (
    build_arrow_native_artifact,
)
from irx.builder.runtime.arrowcpp import (
    arrowcpp_linker_flags,
    arrowcpp_runtime_metadata,
)
from irx.builder.runtime.features import RuntimeFeature
from irx.typecheck import typechecked


@typechecked
def build_dataframe_runtime_feature() -> RuntimeFeature:
    """
    title: Build the builtin dataframe runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    return RuntimeFeature(
        name="dataframe",
        symbols=arrow_external_symbol_specs("dataframe"),
        artifacts=(build_arrow_native_artifact("dataframe"),),
        metadata={
            "opaque_handles": {
                "table": "irx_arrow_table_handle",
                "chunked_array": "irx_arrow_chunked_array_handle",
            },
            "canonical_name": "dataframe",
            **arrowcpp_runtime_metadata(),
        },
        linker_flags=arrowcpp_linker_flags(),
        dependencies=("core",),
    )


__all__ = ["build_dataframe_runtime_feature"]
