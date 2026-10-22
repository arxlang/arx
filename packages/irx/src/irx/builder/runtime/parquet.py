"""
title: On-demand Parquet plugin linked to the owning RecordBatch library.
summary: >-
  Opaque handles and thread-local errors belong to one base shared library. The
  optional plugin links that library rather than duplicating its objects.
"""

from __future__ import annotations

import hashlib
import subprocess

from dataclasses import replace
from pathlib import Path

from public import private

from irx.builder.runtime.linking import compile_native_artifacts
from irx.builder.runtime.record_batch import (
    build_parquet_runtime_feature,
    ensure_record_batch_shared_library,
    record_batch_build_lock,
    shared_library_fingerprint_path,
)
from irx.typecheck import typechecked


@private
@typechecked
def ensure_parquet_shared_library(cxx_binary: str = "c++") -> Path:
    """
    title: Build a fingerprinted plugin only when Parquet is requested.
    summary: >-
      Keep the base path in DT_NEEDED so both loaded modules share handles and
      error state. The base fingerprint includes compiler, sources and headers;
      the plugin adds its optional library flags and sources to that identity.
    parameters:
      cxx_binary:
        type: str
    returns:
      type: Path
    """
    feature = build_parquet_runtime_feature()
    if feature.unavailable_reason is not None:
        raise RuntimeError(feature.unavailable_reason)
    base = ensure_record_batch_shared_library(cxx_binary=cxx_binary)
    output = base.with_name(base.name.replace("record_batch", "parquet"))
    digest = hashlib.sha256(shared_library_fingerprint_path(base).read_bytes())
    digest.update(str(base).encode())
    digest.update(repr((feature.artifacts, feature.linker_flags)).encode())
    for artifact in feature.artifacts:
        digest.update(artifact.path.read_bytes())
    fingerprint = digest.hexdigest()
    stamp = shared_library_fingerprint_path(output)
    with record_batch_build_lock(output):
        if (
            output.is_file()
            and stamp.is_file()
            and stamp.read_text().strip() == fingerprint
        ):
            return output
        artifacts = tuple(
            replace(item, compile_flags=(*item.compile_flags, "-fPIC"))
            for item in feature.artifacts
        )
        work = output.parent / "parquet-build"
        work.mkdir(parents=True, exist_ok=True)
        inputs = compile_native_artifacts(
            artifacts, work, cxx_binary=cxx_binary
        )
        temporary = output.with_name(f".{output.name}.{fingerprint[:12]}.tmp")
        try:
            subprocess.run(
                [
                    cxx_binary,
                    "-shared",
                    "-o",
                    str(temporary),
                    *(str(path) for path in inputs.objects),
                    str(base),
                    *inputs.linker_flags,
                    *feature.linker_flags,
                ],
                check=True,
            )
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
        temporary_stamp = stamp.with_name(f".{stamp.name}.tmp")
        temporary_stamp.write_text(fingerprint + "\n")
        temporary_stamp.replace(stamp)
    return output
