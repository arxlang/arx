"""
title: Generated declarations for the native Arrow runtime ABI.
"""

from irx.builder.runtime.arrow.bindings import (
    configure_arrow_ctypes_library,
)
from irx.builder.runtime.arrow.declarations import (
    arrow_external_symbol_specs,
)

__all__ = [
    "arrow_external_symbol_specs",
    "configure_arrow_ctypes_library",
]
