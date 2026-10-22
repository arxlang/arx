#!/usr/bin/env python3
"""
title: Exercise registered Arrow and Parquet native code under ASan and UBSan.
summary: >-
  Compile the runtime feature artifacts, not a separately maintained source
  list. Third-party Arrow libraries are not rebuilt or instrumented.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile

from pathlib import Path

from irx.builder.runtime.registry import get_default_runtime_feature_registry


def main() -> None:
    """
    title: Build a standalone instrumented executable and fail on diagnostics.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-leaks",
        action="store_true",
        help="disable LeakSanitizer only for restricted local sandboxes",
    )
    args = parser.parse_args()
    cxx = shutil.which(os.environ.get("SANITIZER_CXX", "clang++"))
    cc = shutil.which(os.environ.get("SANITIZER_CC", "clang"))
    if not cxx or not cc:
        raise RuntimeError(
            "ASan/UBSan tests require Clang C and C++ compilers"
        )
    root = Path(__file__).resolve().parents[1]
    temp = root / ".tmp"
    temp.mkdir(exist_ok=True)
    registry = get_default_runtime_feature_registry()
    features = [
        registry.get(name)
        for name in ("buffer", "array", "record_batch", "parquet")
    ]
    artifacts = {
        artifact.path: artifact
        for feature in features
        for artifact in feature.artifacts
    }
    link_flags = list(
        dict.fromkeys(
            flag for feature in features for flag in feature.linker_flags
        )
    )
    includes = sorted(
        {
            str(path)
            for artifact in artifacts.values()
            for path in artifact.include_dirs
        }
    )
    flags = [
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-g1",
        "-O0",
    ]
    with tempfile.TemporaryDirectory(
        dir=temp, prefix="sanitizers-"
    ) as directory:
        work = Path(directory)
        objects: list[str] = []
        for index, artifact in enumerate(artifacts.values()):
            output = work / f"runtime-{index}.o"
            compiler = cc if artifact.kind == "c_source" else cxx
            command = [compiler, *flags, *artifact.compile_flags]
            command.extend(f"-I{path}" for path in includes)
            command.extend(["-c", str(artifact.path), "-o", str(output)])
            subprocess.run(command, check=True)
            objects.append(str(output))
        executable = work / "native-sanitizers"
        source = root / "packages/irx/tests/native/nullable_sanitizers.cc"
        subprocess.run(
            [
                cxx,
                *flags,
                "-std=c++20",
                *(f"-I{p}" for p in includes),
                str(source),
                *objects,
                *link_flags,
                "-o",
                str(executable),
            ],
            check=True,
        )
        detect_leaks = int(not args.no_leaks)
        env = dict(
            os.environ,
            ASAN_OPTIONS=f"detect_leaks={detect_leaks}:halt_on_error=1",
            UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1",
        )
        subprocess.run([str(executable)], cwd=work, env=env, check=True)
    suffix = " (leak detection disabled)" if args.no_leaks else ""
    print(f"Native ASan/UBSan smoke passed{suffix}")


if __name__ == "__main__":
    main()
