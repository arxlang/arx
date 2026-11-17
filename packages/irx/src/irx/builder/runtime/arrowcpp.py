"""
title: Arrow C++ runtime build helpers.
"""

from __future__ import annotations

import re
import sys

from pathlib import Path

import pyarrow

from arx_arrowcpp_sources import (
    bundled_arrowcpp_version,
)
from arx_arrowcpp_sources import (
    get_include_dir as get_arrowcpp_source_include_dir,
)
from public import private

from irx.diagnostics import Diagnostic, DiagnosticCodes, RuntimeFeatureError
from irx.typecheck import typechecked


@private
@typechecked
def validate_arrowcpp_versions() -> None:
    """
    title: Reject mixed Arrow sources, packaged headers and linked versions.
    summary: >-
      This validates a single installed build, not cross-version compatibility.
      It does not establish the ABI revision of an arbitrary loaded IRx handle.
      The source bundle remains required. Check its actual CMake version and
      public header, not only its Python version constant. Missing sources or
      disagreement fail before compilation without choosing another provider.
    """
    try:
        source_include = get_arrowcpp_source_include_dir()
        source_config = source_include.parent / "CMakeLists.txt"
        source_match = re.search(
            r'^set\(ARROW_VERSION "([^"]+)"\)$',
            source_config.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        source_header = source_include / "arrow/api.h"
        if not source_header.is_file():
            raise FileNotFoundError(
                f"Arrow C++ source header is unavailable: {source_header}"
            )
    except (OSError, UnicodeError) as error:
        raise RuntimeFeatureError(
            Diagnostic(
                message="Arrow C++ bundled sources are unavailable",
                code=DiagnosticCodes.RUNTIME_FEATURE_UNAVAILABLE,
                phase="runtime",
                hint="reinstall the pinned arx-arrowcpp-sources distribution",
                cause=error,
            )
        ) from error
    config = Path(pyarrow.get_include()) / "arrow/util/config.h"
    try:
        match = re.search(
            r'^#define ARROW_VERSION_STRING "([^"]+)"$',
            config.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    except (OSError, UnicodeError) as error:
        raise RuntimeFeatureError(
            Diagnostic(
                message="Arrow C++ packaged version header is unavailable",
                code=DiagnosticCodes.RUNTIME_FEATURE_UNAVAILABLE,
                phase="runtime",
                notes=(str(config),),
                hint="reinstall the pinned PyArrow distribution",
                cause=error,
            )
        ) from error
    versions = (
        bundled_arrowcpp_version(),
        source_match.group(1) if source_match else None,
        pyarrow.__version__,
        pyarrow.cpp_version,
        match.group(1) if match else None,
    )
    if all(version == versions[0] for version in versions):
        return
    raise RuntimeFeatureError(
        Diagnostic(
            message="Arrow source/header/library versions do not match",
            code=DiagnosticCodes.RUNTIME_FEATURE_UNAVAILABLE,
            phase="runtime",
            notes=(
                f"source bundle: {versions[0]}; source tree: {versions[1]}; "
                f"PyArrow: {versions[2]}; linked C++: {versions[3]}; "
                f"packaged headers: {versions[4]}",
            ),
            hint=(
                "install matching exact PyArrow and arx-arrowcpp-sources "
                "pins, then rebuild native artifacts"
            ),
        )
    )


@typechecked
def arrowcpp_include_dirs() -> tuple[Path, ...]:
    """
    title: Return Arrow C++ include directories for native runtime builds.
    returns:
      type: tuple[Path, Ellipsis]
    """
    validate_arrowcpp_versions()
    return (
        get_arrowcpp_source_include_dir(),
        Path(pyarrow.get_include()),
    )


@typechecked
def arrowcpp_compile_flags() -> tuple[str, ...]:
    """
    title: Return compiler flags required by Arrow C++ headers.
    returns:
      type: tuple[str, Ellipsis]
    """
    return ("-std=c++20",)


@typechecked
def arrowcpp_linker_flags() -> tuple[str, ...]:
    """
    title: Return linker flags for the bundled Arrow C++ runtime.
    returns:
      type: tuple[str, Ellipsis]
    """
    validate_arrowcpp_versions()
    library = _find_pyarrow_library("arrow")
    library_dir = library.parent
    flags = [str(_find_pyarrow_library("arrow_compute")), str(library)]

    if sys.platform != "win32":
        flags.append(f"-Wl,-rpath,{library_dir}")

    return tuple(flags)


@typechecked
def parquet_linker_flags() -> tuple[str, ...]:
    """
    title: Link RecordBatch artifacts to PyArrow's matching Parquet library.
    returns:
      type: tuple[str, Ellipsis]
    """
    library = _find_pyarrow_library("parquet")
    flags = (
        str(_find_pyarrow_library("arrow_dataset")),
        str(_find_pyarrow_library("arrow_acero")),
        str(_find_pyarrow_library("arrow_compute")),
        str(library),
        *arrowcpp_linker_flags(),
    )
    if sys.platform != "win32":
        flags += (f"-Wl,-rpath,{library.parent}",)
    return tuple(dict.fromkeys(flags))


@typechecked
def arrowcpp_runtime_metadata() -> dict[str, object]:
    """
    title: Return Arrow C++ runtime implementation metadata.
    returns:
      type: dict[str, object]
    """
    return {
        "implementation": "arrow-cpp",
        "arrowcpp_version": bundled_arrowcpp_version(),
        "arrowcpp_include_dirs": tuple(
            str(path) for path in arrowcpp_include_dirs()
        ),
        "arrowcpp_libraries": tuple(arrowcpp_linker_flags()),
    }


@typechecked
def _find_pyarrow_library(name: str) -> Path:
    """
    title: Find one PyArrow-shipped Arrow C++ shared library.
    parameters:
      name:
        type: str
    returns:
      type: Path
    """
    prefixes = _library_prefixes(name)
    suffixes = _library_suffixes()

    for directory_name in pyarrow.get_library_dirs():
        directory = Path(directory_name)
        for prefix in prefixes:
            for suffix in suffixes:
                candidate = directory / f"{prefix}{suffix}"
                if candidate.exists():
                    return candidate

            versioned = sorted(
                directory.glob(f"{prefix}{_versioned_library_glob()}")
            )
            if versioned:
                return versioned[0]

    raise RuntimeError(
        f"PyArrow did not provide a linkable lib{name!s} shared library"
    )


@typechecked
def _library_prefixes(name: str) -> tuple[str, ...]:
    """
    title: Return platform-specific library name prefixes.
    parameters:
      name:
        type: str
    returns:
      type: tuple[str, Ellipsis]
    """
    if sys.platform == "win32":
        return (name, f"lib{name}")
    return (f"lib{name}",)


@typechecked
def _library_suffixes() -> tuple[str, ...]:
    """
    title: Return platform-specific exact shared library suffixes.
    returns:
      type: tuple[str, Ellipsis]
    """
    if sys.platform == "darwin":
        return (".dylib",)
    if sys.platform == "win32":
        return (".lib", ".dll")
    return (".so",)


@typechecked
def _versioned_library_glob() -> str:
    """
    title: Return platform-specific versioned shared library glob.
    returns:
      type: str
    """
    if sys.platform == "darwin":
        return "*.dylib"
    if sys.platform == "win32":
        return "*.dll"
    return ".so*"


__all__ = [
    "arrowcpp_compile_flags",
    "arrowcpp_include_dirs",
    "arrowcpp_linker_flags",
    "arrowcpp_runtime_metadata",
    "parquet_linker_flags",
]
