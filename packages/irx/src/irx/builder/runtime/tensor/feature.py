"""
title: Builtin tensor runtime feature declarations backed by Arrow.
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
from irx.builtins.collections.array_primitives import (
    ARRAY_PRIMITIVE_TYPE_SPECS,
)
from irx.typecheck import typechecked


@typechecked
def build_tensor_runtime_feature() -> RuntimeFeature:
    """
    title: Build the builtin tensor runtime feature specification.
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
        name="tensor",
        symbols=arrow_external_symbol_specs("tensor"),
        artifacts=artifacts,
        metadata={
            "type_ids": {
                name: spec.type_id
                for name, spec in ARRAY_PRIMITIVE_TYPE_SPECS.items()
            },
            "buffer_dtype_tokens": {
                name: spec.dtype_token
                for name, spec in ARRAY_PRIMITIVE_TYPE_SPECS.items()
            },
            "supported_primitive_types": {
                name: {
                    "type_id": spec.type_id,
                    "dtype_token": spec.dtype_token,
                    "element_size_bytes": spec.element_size_bytes,
                    "buffer_view_compatible": spec.buffer_view_compatible,
                }
                for name, spec in ARRAY_PRIMITIVE_TYPE_SPECS.items()
                if spec.buffer_view_compatible
            },
            "opaque_handles": {
                "tensor_builder": "irx_arrow_tensor_builder_handle",
                "tensor": "irx_arrow_tensor_handle",
            },
            "canonical_name": "tensor",
            **arrowcpp_runtime_metadata(),
        },
        linker_flags=arrowcpp_linker_flags(),
    )


__all__ = ["build_tensor_runtime_feature"]
