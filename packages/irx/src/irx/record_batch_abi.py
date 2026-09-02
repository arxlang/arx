"""
title: RecordBatch native ABI and cache path contract.
"""

from __future__ import annotations

import os
import sys

from pathlib import Path

from irx.typecheck import typechecked

RECORD_BATCH_ABI_VERSION = 1
IRX_NATIVE_CACHE_DIR_ENV = "IRX_NATIVE_CACHE_DIR"
IRX_RECORD_BATCH_LIBRARY_ENV = "IRX_RECORD_BATCH_LIBRARY"


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
