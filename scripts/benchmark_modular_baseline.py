#!/usr/bin/env python3
"""
title: Measure the existing table I/O pilot without changing compiler behavior.
summary: >-
  Run from the repository root with python -m
  scripts.benchmark_modular_baseline --repeats 5. Requires the development
  environment and native prerequisites checked by
  scripts/check_native_test_environment.py. Reuse the host CSV fixture rather
  than maintaining another program. Each phase sample uses fresh AST and
  compiler state; import samples use fresh interpreters, not cold OS caches.
  Composition means analyzer/visitor construction, including fresh scoped
  dispatch setup and first-use metadata loading. Lowering includes runtime-
  state setup and IR serialization, but excludes analysis, construction, and
  LLVM verification. A public analysis call includes its own analyzer
  construction. The separate construction probe is not an additional cost to
  add to that measurement. A scoped analysis stub supplies the already analyzed
  session to the public translate entry point; revisit this adapter when phase
  APIs change. Emit and link once, then execute that artifact repeatedly in an
  isolated directory. Native build/cache cost is reported separately, not
  amortized into execution. Report samples and variance; do not enforce a
  timing threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile

from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from irx.builder import Visitor

MIN_REPEATS = 2


def report(phase: str, samples: list[float]) -> None:
    """
    title: Print reproducible samples in seconds, including first-use cost.
    parameters:
      phase:
        type: str
      samples:
        type: list[float]
    """
    print(
        json.dumps(
            {
                "phase": phase,
                "seconds": samples,
                "mean": statistics.mean(samples),
                "stdev": (
                    statistics.stdev(samples) if len(samples) > 1 else None
                ),
                "first": samples[0],
                "min": min(samples),
                "max": max(samples),
            }
        ),
        flush=True,
    )


def main() -> None:
    """
    title: Measure imports, phase construction, CSV compilation, and execution.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if args.repeats < MIN_REPEATS:
        parser.error("--repeats must be at least 2 to report variance")
    root = Path(__file__).resolve().parents[1]
    work = root / ".tmp"
    work.mkdir(exist_ok=True)
    os.environ.setdefault(
        "IRX_NATIVE_CACHE_DIR", str(work / "irx-native-cache")
    )
    print(
        json.dumps(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "versions": {
                    name: version(name)
                    for name in ("plum-dispatch", "llvmlite", "pyarrow")
                },
                "native_cache": os.environ["IRX_NATIVE_CACHE_DIR"],
                "native_cache_policy": "reuse content-addressed cache",
            }
        ),
        flush=True,
    )
    measure_imports(args.repeats, root)
    measure_pipeline(args.repeats, work)


def measure_imports(repeats: int, root: Path) -> None:
    """
    title: Time analysis and backend imports in separate fresh interpreters.
    parameters:
      repeats:
        type: int
      root:
        type: Path
    """
    for module in ("irx.analysis", "irx.builder"):
        samples: list[float] = []
        for _ in range(repeats):
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from time import perf_counter; "
                    f"start = perf_counter(); import {module}; "
                    "print(perf_counter() - start)",
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd=root,
            )
            samples.append(float(result.stdout))
        report(f"fresh-process import {module}", samples)


def measure_pipeline(repeats: int, work: Path) -> None:
    """
    title: Separate construction, analysis, and lowering on fresh CSV trees.
    parameters:
      repeats:
        type: int
      work:
        type: Path
    """
    from llvmlite import binding as llvm
    from packages.irx.tests.analysis.test_table_io import io_module
    from packages.irx.tests.conftest import StaticImportResolver

    from irx.analysis import SemanticAnalyzer, analyze_modules
    from irx.builder import Visitor

    timings: dict[str, list[float]] = {
        name: []
        for name in (
            "analyzer construction",
            "visitor construction",
            "analysis",
            "lowering",
        )
    }
    resolver = StaticImportResolver({})
    for _ in range(repeats):
        module = io_module("csv")[0]
        start = perf_counter()
        analyzer = SemanticAnalyzer()
        timings["analyzer construction"].append(perf_counter() - start)
        del analyzer
        start = perf_counter()
        visitor = Visitor()
        timings["visitor construction"].append(perf_counter() - start)
        start = perf_counter()
        session = analyze_modules(module, resolver)
        timings["analysis"].append(perf_counter() - start)
        with patch(
            "irx.builder.core.analyze_modules", return_value=session
        ) as analysis:
            start = perf_counter()
            ir_text = visitor.translate_modules(module, resolver)
            timings["lowering"].append(perf_counter() - start)
        analysis.assert_called_once_with(module, resolver, configuration=None)
        llvm.parse_assembly(ir_text).verify()
    for phase, samples in timings.items():
        report(phase, samples)
    measure_native(repeats, work, visitor, ir_text)


def measure_native(
    repeats: int, work: Path, visitor: Visitor, ir_text: str
) -> None:
    """
    title: Build once and validate each isolated execution of that artifact.
    parameters:
      repeats:
        type: int
      work:
        type: Path
      visitor:
        type: Visitor
      ir_text:
        type: str
    """
    from llvmlite import binding as llvm

    from irx.builder.runtime.linking import link_executable

    with tempfile.TemporaryDirectory(dir=work, prefix="modular-") as directory:
        path = Path(directory)
        object_file = path / "module.o"
        executable = path / "table-io"
        llvm_module = llvm.parse_assembly(ir_text)
        llvm_module.verify()
        start = perf_counter()
        object_file.write_bytes(
            visitor.target_machine.emit_object(llvm_module)
        )
        report("object emission (once)", [perf_counter() - start])
        start = perf_counter()
        link_executable(
            primary_object=object_file,
            output_file=executable,
            artifacts=visitor.runtime_features.native_artifacts(),
            linker_flags=visitor.runtime_features.linker_flags(),
        )
        executable.chmod(0o755)
        report(
            "native build/link (once; existing cache)",
            [perf_counter() - start],
        )
        (path / "input").write_text("id\n1\n2\n", encoding="utf-8")
        samples = []
        for _ in range(repeats):
            (path / "output").unlink(missing_ok=True)
            start = perf_counter()
            subprocess.run([str(executable)], cwd=path, check=True)
            samples.append(perf_counter() - start)
            # Validation is outside the timer; each process starts fresh.
            if (path / "output").read_text(encoding="utf-8") != '"id"\n1\n2\n':
                raise RuntimeError("CSV baseline output differs from input")
        report("native execution (includes process launch)", samples)


if __name__ == "__main__":
    main()
