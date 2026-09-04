"""
title: Builtin array runtime feature declarations backed by Arrow.
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
    IRX_ARROW_TYPE_BOOL,
    IRX_ARROW_TYPE_FLOAT32,
    IRX_ARROW_TYPE_FLOAT64,
    IRX_ARROW_TYPE_INT8,
    IRX_ARROW_TYPE_INT16,
    IRX_ARROW_TYPE_INT32,
    IRX_ARROW_TYPE_INT64,
    IRX_ARROW_TYPE_UINT8,
    IRX_ARROW_TYPE_UINT16,
    IRX_ARROW_TYPE_UINT32,
    IRX_ARROW_TYPE_UINT64,
    IRX_ARROW_TYPE_UNKNOWN,
    ArrayPrimitiveTypeSpec,
)
from irx.typecheck import typechecked


@typechecked
def build_named_array_runtime_feature(feature_name: str) -> RuntimeFeature:
    """
    title: Build one Arrow-backed array runtime feature specification.
    parameters:
      feature_name:
        type: str
    returns:
      type: RuntimeFeature
    """
    return RuntimeFeature(
        name=feature_name,
        symbols=arrow_external_symbol_specs("array"),
        artifacts=(build_arrow_native_artifact("array"),),
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
            },
            "opaque_handles": {
                "schema": "irx_arrow_schema_handle",
                "array_builder": "irx_arrow_array_builder_handle",
                "array": "irx_arrow_array_handle",
            },
            "canonical_name": "array",
            **arrowcpp_runtime_metadata(),
        },
        linker_flags=arrowcpp_linker_flags(),
        dependencies=("core",),
    )


@typechecked
def build_array_runtime_feature() -> RuntimeFeature:
    """
    title: Build the builtin array runtime feature specification.
    returns:
      type: RuntimeFeature
    """
    return build_named_array_runtime_feature("array")


__all__ = [
    "ARRAY_PRIMITIVE_TYPE_SPECS",
    "IRX_ARROW_TYPE_BOOL",
    "IRX_ARROW_TYPE_FLOAT32",
    "IRX_ARROW_TYPE_FLOAT64",
    "IRX_ARROW_TYPE_INT8",
    "IRX_ARROW_TYPE_INT16",
    "IRX_ARROW_TYPE_INT32",
    "IRX_ARROW_TYPE_INT64",
    "IRX_ARROW_TYPE_UINT8",
    "IRX_ARROW_TYPE_UINT16",
    "IRX_ARROW_TYPE_UINT32",
    "IRX_ARROW_TYPE_UINT64",
    "IRX_ARROW_TYPE_UNKNOWN",
    "ArrayPrimitiveTypeSpec",
    "build_array_runtime_feature",
]
