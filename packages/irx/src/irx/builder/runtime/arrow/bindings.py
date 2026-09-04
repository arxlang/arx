"""
title: Python bindings for the generated Arrow runtime ABI.
"""

from __future__ import annotations

import ctypes

from collections.abc import Sequence

from irx.builder.runtime.arrow.abi_generated import (
    CTYPES_SIGNATURES,
    FEATURE_SYMBOLS,
    HANDLE_TYPES,
)
from irx.typecheck import typechecked


@typechecked
def arrow_ctypes_type(type_token: str) -> object | None:
    """
    title: Resolve one generated Arrow ABI token to a ctypes type.
    parameters:
      type_token:
        type: str
    returns:
      type: object | None
    """
    scalar_types: dict[str, object | None] = {
        "void": None,
        "status": ctypes.c_int32,
        "status_category": ctypes.c_int32,
        "runtime_feature_id": ctypes.c_int32,
        "uint32": ctypes.c_uint32,
        "int32": ctypes.c_int32,
        "int64": ctypes.c_int64,
        "uint64": ctypes.c_uint64,
        "double": ctypes.c_double,
        "c_string": ctypes.c_char_p,
    }
    if type_token in scalar_types:
        return scalar_types[type_token]

    if type_token == "uint32_pointer":
        return ctypes.POINTER(ctypes.c_uint32)
    if type_token in {
        "const_void",
        "void_pointer",
        "const_arrow_schema",
        "arrow_schema",
        "const_arrow_array",
        "arrow_array",
        "buffer_view",
    }:
        return ctypes.c_void_p
    if type_token == "c_string_pointer":
        return ctypes.POINTER(ctypes.c_char_p)
    if type_token in {"int64_pointer", "const_int64_pointer"}:
        return ctypes.POINTER(ctypes.c_int64)
    if type_token == "const_int64_output":
        return ctypes.POINTER(ctypes.POINTER(ctypes.c_int64))
    if type_token in {
        "handle_kind_pointer",
        "int32_pointer",
        "ownership_pointer",
        "status_pointer",
    }:
        return ctypes.POINTER(ctypes.c_int32)
    if type_token == "const_void_pointer":
        return ctypes.POINTER(ctypes.c_void_p)

    for handle_name in HANDLE_TYPES:
        if type_token in {handle_name, f"const_{handle_name}"}:
            return ctypes.c_void_p
        if type_token == f"{handle_name}_pointer":
            return ctypes.POINTER(ctypes.c_void_p)
    raise ValueError(f"Unknown generated Arrow ABI type '{type_token}'")


@typechecked
def configure_arrow_ctypes_library(
    library: ctypes.CDLL,
    features: Sequence[str] | None = None,
) -> None:
    """
    title: Apply selected generated Arrow ABI declarations to a ctypes library.
    summary: >-
      Configure the complete ABI by default. Capability-specific libraries can
      provide their exact linked feature names so absent symbols are not
      resolved eagerly.
    parameters:
      library:
        type: ctypes.CDLL
      features:
        type: Sequence[str] | None
    """
    selected_symbols: frozenset[str] | None = None
    if features is not None:
        unknown_features = set(features).difference(FEATURE_SYMBOLS)
        if unknown_features:
            names = ", ".join(sorted(unknown_features))
            raise ValueError(f"Unknown Arrow runtime features: {names}")
        selected_symbols = frozenset(
            name for feature in features for name in FEATURE_SYMBOLS[feature]
        )

    for name, (return_type, parameter_types) in CTYPES_SIGNATURES.items():
        if selected_symbols is not None and name not in selected_symbols:
            continue
        function = getattr(library, name)
        function.argtypes = [
            arrow_ctypes_type(type_token) for type_token in parameter_types
        ]
        function.restype = arrow_ctypes_type(return_type)


__all__ = ["arrow_ctypes_type", "configure_arrow_ctypes_library"]
