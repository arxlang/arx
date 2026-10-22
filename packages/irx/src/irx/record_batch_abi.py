"""
title: RecordBatch native ABI and cache path contract.
"""

from __future__ import annotations

import ctypes
import os
import sys

from pathlib import Path

from public import private

from irx.typecheck import typechecked

RECORD_BATCH_ABI_VERSION = 1
IRX_NATIVE_CACHE_DIR_ENV = "IRX_NATIVE_CACHE_DIR"
IRX_RECORD_BATCH_LIBRARY_ENV = "IRX_RECORD_BATCH_LIBRARY"


@private
@typechecked
class ArrowArrayStream(ctypes.Structure):
    """
    title: Caller-owned Arrow C Stream ABI storage with opaque callbacks.
    """

    _fields_ = [
        ("get_schema", ctypes.c_void_p),
        ("get_next", ctypes.c_void_p),
        ("get_last_error", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("private_data", ctypes.c_void_p),
    ]


@private
@typechecked
class ArrowSchema(ctypes.Structure):
    """
    title: Caller-owned Arrow C Data schema storage, not an Arrow C++ layout.
    summary: >-
      Matches irx_arrow_c_abi.h. Native release helpers own callback
      invocation; pointer fields remain opaque. This uses only the Python
      standard library.
    """

    _fields_ = [
        ("format", ctypes.c_void_p),
        ("name", ctypes.c_void_p),
        ("metadata", ctypes.c_void_p),
        ("flags", ctypes.c_int64),
        ("n_children", ctypes.c_int64),
        ("children", ctypes.c_void_p),
        ("dictionary", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("private_data", ctypes.c_void_p),
    ]


@private
@typechecked
class ArrowArray(ctypes.Structure):
    """
    title: Caller-owned Arrow C Data array storage with opaque native buffers.
    summary: >-
      Matches irx_arrow_c_abi.h. Release callbacks are invoked by the native
      helpers; this structure does not describe any Arrow C++ object layout.
    """

    _fields_ = [
        ("length", ctypes.c_int64),
        ("null_count", ctypes.c_int64),
        ("offset", ctypes.c_int64),
        ("n_buffers", ctypes.c_int64),
        ("n_children", ctypes.c_int64),
        ("buffers", ctypes.c_void_p),
        ("children", ctypes.c_void_p),
        ("dictionary", ctypes.c_void_p),
        ("release", ctypes.c_void_p),
        ("private_data", ctypes.c_void_p),
    ]


@typechecked
def record_batch_library_name() -> str:
    """
    title: Return the platform-native RecordBatch shared-library name.
    returns:
      type: str
    """
    if sys.platform == "darwin":
        return "libirx_record_batch.dylib"
    if sys.platform == "win32":
        return "irx_record_batch.dll"
    return "libirx_record_batch.so"


@typechecked
def irx_native_cache_dir() -> Path:
    """
    title: Return the explicit writable cache root for generated native code.
    returns:
      type: Path
    """
    configured = os.environ.get(IRX_NATIVE_CACHE_DIR_ENV)
    if configured:
        return Path(configured).expanduser().resolve()

    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    root = (
        Path(xdg_cache).expanduser() if xdg_cache else Path.home() / ".cache"
    )
    return (root / "arxlang" / "irx").resolve()


@typechecked
def record_batch_library_path() -> Path:
    """
    title: Return the configured or ABI-scoped cached native library path.
    returns:
      type: Path
    """
    configured = os.environ.get(IRX_RECORD_BATCH_LIBRARY_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return (
        irx_native_cache_dir()
        / "record_batch"
        / f"abi-{RECORD_BATCH_ABI_VERSION}"
        / record_batch_library_name()
    )


__all__ = [
    "IRX_NATIVE_CACHE_DIR_ENV",
    "IRX_RECORD_BATCH_LIBRARY_ENV",
    "RECORD_BATCH_ABI_VERSION",
    "irx_native_cache_dir",
    "record_batch_library_name",
    "record_batch_library_path",
]
