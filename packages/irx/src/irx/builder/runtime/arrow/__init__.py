"""
title: Generated declarations for the native Arrow runtime ABI.
"""

from irx.builder.runtime.arrow.bindings import (
    configure_arrow_ctypes_library,
)
from irx.builder.runtime.arrow.declarations import (
    arrow_external_symbol_specs,
)
from irx.builder.runtime.arrow.feature import (
    build_arrow_core_runtime_feature,
)

__all__ = [
    "arrow_external_symbol_specs",
    "build_arrow_core_runtime_feature",
    "configure_arrow_ctypes_library",
]
