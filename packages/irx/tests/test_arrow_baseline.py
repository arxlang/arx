"""
title: Correctness and measurement boundaries of the M0 benchmark driver.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys

from pathlib import Path

import pyarrow as pa
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "benchmark_arrow_first.py"
SPEC = importlib.util.spec_from_file_location("arrow_baseline", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("benchmark driver could not be loaded")
baseline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = baseline
SPEC.loader.exec_module(baseline)


def test_versioned_inputs_and_llvm_oracle() -> None:
    """
    title: Empty/dense inputs execute with explicit offset/null dimensions.
    """
    cases = {case.name: case for case in baseline.cases()}
    assert cases["nullable_chunked"].chunks > 1
    assert cases["nullable_chunked"].offset > 0
    assert None in cases["nullable_chunked"].values()
    for values in ([], [0.0, -0.5, -0.0, 0.125, 1024.0]):
        run, read = baseline.llvm_runner(values)
        run()
        assert read() == [value + 0.5 for value in values]
    with pytest.raises(ValueError, match="does not support null"):
        baseline.llvm_runner([None])


@pytest.mark.parametrize("attribute", ["__version__", "cpp_version"])
def test_unqualified_arrow_is_rejected(
    monkeypatch: pytest.MonkeyPatch, attribute: str
) -> None:
    """
    title: Newer PyArrow or mismatched linked C++ is not silently benchmarked.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
      attribute:
        type: str
    """
    major = int(pa.__version__.split(".")[0])
    monkeypatch.setattr(pa, attribute, "25.0.0")
    with pytest.raises(RuntimeError, match="matching Arrow"):
        baseline.require_arrow_baseline(major)


def test_invalid_measurement_counts_fail_before_building() -> None:
    """
    title: Reject an empty sample set without compiling native dependencies.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--samples", "0"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "must be positive" in result.stderr


def test_old_arrow_cannot_qualify_the_default_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    title: A historical Arrow 24 run cannot silently satisfy the Arrow 26 gate.
    parameters:
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    monkeypatch.setattr(pa, "__version__", "24.0.0")
    monkeypatch.setattr(pa, "cpp_version", "24.0.0")
    with pytest.raises(RuntimeError, match=r"matching Arrow 26\.0\.1 exactly"):
        baseline.require_arrow_baseline()


def test_target_is_one_exact_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    title: Matching headers and libraries from another patch are not the pin.
    parameters:
      tmp_path:
        type: Path
      monkeypatch:
        type: pytest.MonkeyPatch
    """
    header = tmp_path / "arrow/util/config.h"
    header.parent.mkdir(parents=True)
    header.write_text('#define ARROW_VERSION_STRING "26.0.0"\n')
    monkeypatch.setattr(pa, "get_include", lambda: str(tmp_path))
    monkeypatch.setattr(pa, "__version__", "26.0.0")
    monkeypatch.setattr(pa, "cpp_version", "26.0.0")
    with pytest.raises(RuntimeError, match=r"Arrow 26\.0\.1 exactly"):
        baseline.require_arrow_baseline()
    with pytest.raises(ValueError, match="unsupported benchmark Arrow"):
        baseline.require_arrow_baseline(25)


@pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("clang++") is None,
    reason="Linux benchmark qualification needs a C++20 Clang toolchain",
)
def test_isolated_baseline_reports_correctness_and_allocations(
    tmp_path: Path,
) -> None:
    """
    title: Exercise real workers, native ownership, counters and both reports.
    parameters:
      tmp_path:
        type: Path
    """
    samples, iterations = 2, 2
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(tmp_path),
            "--samples",
            str(samples),
            "--iterations",
            str(iterations),
            "--arrow-major",
            pa.__version__.split(".")[0],
            "--case",
            "scalar",
            "--case",
            "nullable_chunked",
            "--case",
            "empty",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((tmp_path / "baseline.json").read_text())
    assert report["schema_version"] == 1
    assert report["source_sha256"]["scripts/benchmarks/arrow-first-v1.ll"]
    assert report["source_sha256"]["poetry.lock"]
    assert report["source_sha256"][
        "packages/irx/src/irx/builder/runtime/arrowcpp.py"
    ]
    assert report["build"]["compile_ns"] > 0
    assert report["build"]["runtime_library_bytes"] > 0
    assert report["build"]["native_object_bytes"] > 0
    assert report["qualification_arrow_version"] == "26.0.1"
    assert report["versions"]["pyarrow"] == pa.__version__
    assert report["versions"]["arx-arrowcpp-sources"] == pa.cpp_version
    assert report["manifests"]["irx"] == report["versions"]["pyirx"]
    rows = {(row["backend"], row["case"]): row for row in report["results"]}
    selected = {"scalar", "nullable_chunked", "empty"}
    assert len(rows) == len(baseline.BACKENDS) * len(selected)
    assert rows["llvm", "nullable_chunked"]["status"] == "unsupported"
    for row in rows.values():
        if row["status"] == "unsupported":
            assert "cold_first_call_ns" not in row
            continue
        assert len(row["warm_ns"]) == samples
        assert row["cold_first_call_ns"] > 0
        assert row["worker_wall_ns"] > row["setup_ns"]
        assert row["arrow_pool_live_delta_bytes"] == 0
        assert row["measured_calls"] == samples * iterations
        assert not row["compiler_loaded"]
    # This guards against a Python-only proxy missing native ExecContext's
    # original memory pool and incorrectly reporting allocation-free Series.
    assert rows["irx-series", "nullable_chunked"]["arrow_pool_allocations"] > 0
    assert rows["pyarrow", "nullable_chunked"]["arrow_pool_allocations"] > 0
    assert rows["llvm", "scalar"]["output_policy"] == "preallocated"
    assert "unsupported" in (tmp_path / "baseline.md").read_text()
    assert not list(tmp_path.glob("build-*"))
