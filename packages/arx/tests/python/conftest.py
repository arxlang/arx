"""
title: Share unchanged runtime objects, not mutable program state.
"""

import os

from collections.abc import Iterator
from pathlib import Path

import irx
import pytest

from irx.builder.runtime import linking

from .native_support import NativeObjectCache


@pytest.fixture(scope="session")
def native_cache(
    tmp_path_factory: pytest.TempPathFactory,
) -> NativeObjectCache:
    """
    title: Allocate one isolated native cache for this pytest worker.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: NativeObjectCache
    """
    return NativeObjectCache(
        tmp_path_factory.mktemp("arx-native"), Path(irx.__file__).parent
    )


@pytest.fixture(scope="module", autouse=True)
def native_objects(native_cache: NativeObjectCache) -> Iterator[None]:
    """
    title: Reuse objects in Arx tests without patching other packages' tests.
    parameters:
      native_cache:
        type: NativeObjectCache
    returns:
      type: Iterator[None]
    yields:
      type: None
    """
    with pytest.MonkeyPatch.context() as patch:
        if not os.environ.get("IRX_NATIVE_CACHE_DIR"):
            patch.setenv(
                "IRX_NATIVE_CACHE_DIR",
                str(native_cache.directory / "libraries"),
            )
        patch.setattr(linking, "_compile_native_source", native_cache.compile)
        yield
