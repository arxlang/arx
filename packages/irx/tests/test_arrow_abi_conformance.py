"""
title: Installed-header, layout, symbol, and version ABI conformance tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from dataclasses import replace
from pathlib import Path

import pytest

from irx.builder.runtime.array.feature import build_array_runtime_feature
from irx.builder.runtime.arrow.abi_generated import FEATURE_SYMBOLS
from irx.builder.runtime.arrow.feature import (
    arrow_native_source_dir,
    build_arrow_core_runtime_feature,
)
from irx.builder.runtime.dataframe.feature import (
    build_dataframe_runtime_feature,
)
from irx.builder.runtime.features import RuntimeFeature
from irx.builder.runtime.linking import compile_native_artifacts
from irx.builder.runtime.record_batch import (
    build_record_batch_runtime_feature,
)
from irx.builder.runtime.tensor.feature import build_tensor_runtime_feature

ROOT = Path(__file__).parents[3]
ABI_MANIFEST = (
    ROOT
    / "packages"
    / "irx"
    / "src"
    / "irx"
    / "builder"
    / "runtime"
    / "arrow"
    / "abi.json"
)
ABI_BASELINE = ABI_MANIFEST.parent / "abi_baselines" / "1.0.0.json"
COMPATIBILITY_CHECKER = ROOT / "scripts" / "check_arrow_abi_compatibility.py"
HEADER_PROBE = """
#include "irx_arrow_runtime.h"

#if IRX_ARROW_ABI_VERSION != UINT32_C(0x00010000)
#error "unexpected Arrow ABI version"
#endif

#if defined(__cplusplus)
static_assert(IRX_ARROW_ABI_VERSION_IS_COMPATIBLE(
    UINT32_C(0x00010100), UINT32_C(0x00010000)));
static_assert(!IRX_ARROW_ABI_VERSION_IS_COMPATIBLE(
    UINT32_C(0x00010000), UINT32_C(0x00010100)));
#else
_Static_assert(IRX_ARROW_ABI_VERSION_IS_COMPATIBLE(
    UINT32_C(0x00010100), UINT32_C(0x00010000)),
    "older-minor consumers must accept newer runtimes");
_Static_assert(!IRX_ARROW_ABI_VERSION_IS_COMPATIBLE(
    UINT32_C(0x00010000), UINT32_C(0x00010100)),
    "newer-minor consumers must reject older runtimes");
#endif

int irx_arrow_header_probe(void) {
  return (int)sizeof(irx_buffer_view);
}
"""


def find_compiler(environment_name: str, fallback: str) -> str | None:
    """
    title: Resolve one configured native compiler.
    parameters:
      environment_name:
        type: str
      fallback:
        type: str
    returns:
      type: str | None
    """
    configured = os.environ.get(environment_name, fallback)
    compiler = shutil.which(configured)
    if compiler is None and environment_name in os.environ:
        raise RuntimeError(f"configured compiler not found: {configured}")
    return compiler


@pytest.mark.parametrize(
    ("suffix", "environment_name", "fallback", "standard"),
    (
        ("c", "CC", "cc", "c11"),
        ("cc", "CXX", "c++", "c++20"),
    ),
)
def test_public_arrow_header_compiles_with_required_language_standards(
    tmp_path: Path,
    suffix: str,
    environment_name: str,
    fallback: str,
    standard: str,
) -> None:
    """
    title: The public header family should compile as C11 and C++20.
    parameters:
      tmp_path:
        type: Path
      suffix:
        type: str
      environment_name:
        type: str
      fallback:
        type: str
      standard:
        type: str
    """
    compiler = find_compiler(environment_name, fallback)
    if compiler is None:
        pytest.skip(f"{configured_compiler_label(environment_name)} missing")

    arrow_include = arrow_native_source_dir()
    buffer_include = arrow_include.parent.parent / "buffer" / "native"
    source = tmp_path / f"arrow_abi_probe.{suffix}"
    output = tmp_path / f"arrow_abi_probe_{suffix}.o"
    source.write_text(HEADER_PROBE, encoding="utf-8")

    subprocess.run(
        [
            compiler,
            f"-std={standard}",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic-errors",
            "-I",
            str(arrow_include),
            "-I",
            str(buffer_include),
            "-c",
            str(source),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def configured_compiler_label(environment_name: str) -> str:
    """
    title: Describe the compiler selected by one environment variable.
    parameters:
      environment_name:
        type: str
    returns:
      type: str
    """
    return os.environ.get(environment_name, environment_name)


def run_compatibility_check(
    manifest: Path,
    baseline: Path,
) -> subprocess.CompletedProcess[str]:
    """
    title: Run the Arrow ABI compatibility checker for two manifests.
    parameters:
      manifest:
        type: Path
      baseline:
        type: Path
    returns:
      type: subprocess.CompletedProcess[str]
    """
    return subprocess.run(
        [
            sys.executable,
            str(COMPATIBILITY_CHECKER),
            "--manifest",
            str(manifest),
            "--baseline",
            str(baseline),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    """
    title: Write one temporary ABI manifest fixture.
    parameters:
      path:
        type: Path
      manifest:
        type: dict[str, object]
    """
    path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def test_checked_in_abi_satisfies_version_one_baseline() -> None:
    """
    title: The current manifest should preserve every ABI 1.0 contract.
    """
    result = run_compatibility_check(ABI_MANIFEST, ABI_BASELINE)

    assert result.returncode == 0, result.stderr


def test_compatibility_checker_accepts_newer_minor_runtime(
    tmp_path: Path,
) -> None:
    """
    title: An older-minor consumer should accept an append-only newer runtime.
    parameters:
      tmp_path:
        type: Path
    """
    current = json.loads(ABI_MANIFEST.read_text(encoding="utf-8"))
    current["abi_version"] = "1.1.0"
    manifest = tmp_path / "runtime-1.1.json"
    write_manifest(manifest, current)

    result = run_compatibility_check(manifest, ABI_BASELINE)

    assert result.returncode == 0, result.stderr


def test_compatibility_checker_rejects_older_minor_runtime(
    tmp_path: Path,
) -> None:
    """
    title: A newer-minor consumer should reject an older runtime.
    parameters:
      tmp_path:
        type: Path
    """
    baseline = json.loads(ABI_BASELINE.read_text(encoding="utf-8"))
    baseline["abi_version"] = "1.1.0"
    consumer = tmp_path / "consumer-1.1.json"
    write_manifest(consumer, baseline)

    result = run_compatibility_check(ABI_MANIFEST, consumer)

    assert result.returncode == 1
    assert "older than its consumer baseline" in result.stderr


def test_compatibility_checker_ignores_patch_version_order(
    tmp_path: Path,
) -> None:
    """
    title: ABI patch releases should not change consumer compatibility.
    parameters:
      tmp_path:
        type: Path
    """
    baseline = json.loads(ABI_BASELINE.read_text(encoding="utf-8"))
    baseline["abi_version"] = "1.0.1"
    consumer = tmp_path / "consumer-1.0.1.json"
    write_manifest(consumer, baseline)

    result = run_compatibility_check(ABI_MANIFEST, consumer)

    assert result.returncode == 0, result.stderr


def test_compatibility_checker_rejects_changed_stable_signature(
    tmp_path: Path,
) -> None:
    """
    title: A stable function signature cannot change within ABI major one.
    parameters:
      tmp_path:
        type: Path
    """
    current = json.loads(ABI_MANIFEST.read_text(encoding="utf-8"))
    current["abi_version"] = "1.1.0"
    functions = current["functions"]
    assert isinstance(functions, list)
    functions[0]["return"] = "int32"
    manifest = tmp_path / "broken-runtime.json"
    write_manifest(manifest, current)

    result = run_compatibility_check(manifest, ABI_BASELINE)

    assert result.returncode == 1
    assert "function declarations changed" in result.stderr


def arrow_features() -> dict[str, RuntimeFeature]:
    """
    title: Build every stable Arrow runtime capability feature.
    returns:
      type: dict[str, RuntimeFeature]
    """
    return {
        "core": build_arrow_core_runtime_feature(),
        "array": build_array_runtime_feature(),
        "tensor": build_tensor_runtime_feature(),
        "dataframe": build_dataframe_runtime_feature(),
        "record_batch": build_record_batch_runtime_feature(),
    }


@pytest.fixture(scope="module")
def arrow_capability_libraries(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Path]:
    """
    title: Compile one shared library for each stable Arrow capability.
    parameters:
      tmp_path_factory:
        type: pytest.TempPathFactory
    returns:
      type: dict[str, Path]
    """
    if not sys.platform.startswith("linux"):
        pytest.skip("ELF dynamic symbol enumeration requires Linux")
    cxx = find_compiler("CXX", "c++")
    nm = shutil.which("nm")
    if cxx is None or nm is None:
        pytest.skip("a C++ compiler and nm are required")

    features = arrow_features()
    work_dir = tmp_path_factory.mktemp("arrow-abi-symbols")
    capability_order = tuple(features)
    artifacts = tuple(
        replace(
            features[name].artifacts[0],
            compile_flags=(
                *features[name].artifacts[0].compile_flags,
                "-fPIC",
            ),
        )
        for name in capability_order
    )
    link_inputs = compile_native_artifacts(
        artifacts,
        work_dir,
        cxx_binary=cxx,
    )
    objects = dict(zip(capability_order, link_inputs.objects, strict=True))
    libraries: dict[str, Path] = {}

    for capability in capability_order:
        library = work_dir / f"libirx_arrow_{capability}.so"
        command = [cxx, "-shared"]
        command.extend(["-o", str(library), str(objects["core"])])
        if capability != "core":
            command.append(str(objects[capability]))
        command.extend(features[capability].linker_flags)
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        libraries[capability] = library

    return libraries


def exported_symbols(library: Path) -> set[str]:
    """
    title: Enumerate defined dynamic symbols from one native library.
    parameters:
      library:
        type: Path
    returns:
      type: set[str]
    """
    nm = shutil.which("nm")
    if nm is None:
        raise RuntimeError("nm is required for symbol conformance")
    result = subprocess.run(
        [nm, "-D", "--defined-only", str(library)],
        check=True,
        capture_output=True,
        text=True,
    )
    symbols = {
        line.split()[-1].split("@", maxsplit=1)[0]
        for line in result.stdout.splitlines()
        if line.split()
    }
    symbols.discard("IRX_ARROW_1.0")
    return symbols


@pytest.mark.parametrize(
    "capability",
    ("core", "array", "tensor", "dataframe", "record_batch"),
)
def test_capability_libraries_export_only_owned_stable_symbols(
    capability: str,
    arrow_capability_libraries: dict[str, Path],
) -> None:
    """
    title: Capability libs should hide every non-ABI implementation symbol.
    parameters:
      capability:
        type: str
      arrow_capability_libraries:
        type: dict[str, Path]
    """
    expected = set(FEATURE_SYMBOLS["core"])
    if capability != "core":
        expected.update(FEATURE_SYMBOLS[capability])

    assert exported_symbols(arrow_capability_libraries[capability]) == expected
