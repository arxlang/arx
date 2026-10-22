#!/usr/bin/env python3
"""
title: Fail CI rather than silently skip required native integration tests.
"""

import shutil
import subprocess

import pyarrow as pa

from irx.builder.runtime.arrowcpp import parquet_linker_flags


def main() -> None:
    """
    title: Verify compiler availability and the expected Arrow runtime build.
    """
    for name in ("clang", "c++"):
        compiler = shutil.which(name)
        if compiler is None:
            raise RuntimeError(
                f"Required native test compiler missing: {name}"
            )
        subprocess.run([compiler, "--version"], check=True)
    parquet_linker_flags()
    for codec in ("snappy", "gzip", "brotli", "zstd", "lz4"):
        if not pa.Codec.is_available(codec):
            raise RuntimeError(
                f"Required CI Parquet codec unavailable: {codec}"
            )
    print("Native integration prerequisites available")


if __name__ == "__main__":
    main()
