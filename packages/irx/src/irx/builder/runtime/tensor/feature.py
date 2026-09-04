"""
title: Builtin tensor runtime feature declarations backed by Arrow.
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
    return RuntimeFeature(
        name="tensor",
        symbols=arrow_external_symbol_specs("tensor"),
        artifacts=(build_arrow_native_artifact("tensor"),),
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
        dependencies=("core",),
    )


__all__ = ["build_tensor_runtime_feature"]
