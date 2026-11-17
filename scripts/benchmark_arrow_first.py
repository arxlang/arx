#!/usr/bin/env python3
"""
title: Reproduce the M0 unboxed LLVM and existing Arrow compute baseline.
summary: >-
  Run from the checkout on Linux. Each backend/case uses a fresh process;
  runtime compilation is uncached in a tool-owned temporary directory. Cold
  means first kernel invocation, not an OS page-cache flush. Warm samples
  include output allocation and release, but exclude input construction and
  correctness checks. LLVM uses preallocated output, reported separately. Arrow
  counters cover memory-pool buffers, not C++ Scalar/handle heap objects.
  Process peak RSS includes imports/setup and is not kernel-only memory.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tomllib

from collections.abc import Callable
from dataclasses import dataclass, replace
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "scripts" / "benchmarks" / "arrow-first-v1.json"
REFERENCE = INPUTS.with_suffix(".ll")
BACKENDS = ("llvm", "irx-scalar", "irx-series", "pyarrow")
RHS = 0.5
TARGET_ARROW_VERSION = "26.0.1"
TARGET_ARROW_MAJOR = 26
HISTORICAL_ARROW_MAJOR = 24


@dataclass(frozen=True)
class Case:
    """
    title: One versioned input with logical nulls and physical chunk offsets.
    attributes:
      name:
        type: str
      length:
        type: int
      chunks:
        type: int
      offset:
        type: int
      null_every:
        type: int
    """

    name: str
    length: int
    chunks: int
    offset: int
    null_every: int

    def values(self) -> list[float | None]:
        """
        title: Generate exact dyadic inputs independently of Arrow compute.
        returns:
          type: list[float | None]
        """
        return [
            None
            if self.null_every and i % self.null_every == 0
            else i % 1024 / 8
            for i in range(self.length)
        ]


def cases() -> list[Case]:
    """
    title: Load the checked-in baseline inputs.
    returns:
      type: list[Case]
    """
    data = json.loads(INPUTS.read_text())
    if data["schema_version"] != 1 or data["rhs"] != RHS:
        raise ValueError("unsupported benchmark input revision")
    return [Case(**item) for item in data["cases"]]


def require_arrow_baseline(arrow_major: int = TARGET_ARROW_MAJOR) -> None:
    """
    title: Reject mismatched headers, linked Arrow, or an unqualified major.
    parameters:
      arrow_major:
        type: int
    """
    import pyarrow as pa

    if arrow_major not in (HISTORICAL_ARROW_MAJOR, TARGET_ARROW_MAJOR):
        raise ValueError("unsupported benchmark Arrow version")
    # Do not import the compiler in every measurement subprocess. Runtime
    # typechecking makes that setup expensive; build_runtime checks the actual
    # registered feature's header version once before compiling it.
    config = Path(pa.get_include()) / "arrow/util/config.h"
    match = re.search(
        r'^#define ARROW_VERSION_STRING "([^"]+)"$',
        config.read_text(),
        re.MULTILINE,
    )
    headers = match.group(1) if match else None
    expected = (
        TARGET_ARROW_VERSION if arrow_major == TARGET_ARROW_MAJOR else "24.0.0"
    )
    if (
        pa.__version__ != expected
        or pa.cpp_version != headers
        or pa.__version__ != pa.cpp_version
    ):
        raise RuntimeError(
            f"baseline requires matching Arrow {expected} exactly: "
            f"pyarrow={pa.__version__}, "
            f"linked={pa.cpp_version}, sources={headers}"
        )


def build_runtime(
    directory: Path, compiler: str, flags: tuple[str, ...]
) -> tuple[Path, dict[str, object]]:
    """
    title: Build only registered array artifacts without a persistent cache.
    parameters:
      directory:
        type: Path
      compiler:
        type: str
      flags:
        type: tuple[str, Ellipsis]
    returns:
      type: tuple[Path, dict[str, object]]
    """
    start = time.perf_counter_ns()
    import pyarrow as pa

    from irx.builder.runtime.array.feature import build_array_runtime_feature
    from irx.builder.runtime.linking import compile_native_artifacts

    feature = build_array_runtime_feature()
    if feature.metadata["arrowcpp_version"] != pa.cpp_version:
        raise RuntimeError(
            "registered runtime headers and Arrow library differ"
        )
    feature_setup_ns = time.perf_counter_ns() - start
    artifacts = tuple(
        replace(item, compile_flags=(*item.compile_flags, "-fPIC", *flags))
        for item in feature.artifacts
    )
    start = time.perf_counter_ns()
    inputs = compile_native_artifacts(
        artifacts, directory, cxx_binary=compiler
    )
    compile_ns = time.perf_counter_ns() - start
    output = directory / "libbaseline.so"
    command = [
        compiler,
        "-shared",
        "-o",
        str(output),
        *(str(path) for path in inputs.objects),
        *inputs.linker_flags,
        *feature.linker_flags,
        *flags,
    ]
    start = time.perf_counter_ns()
    subprocess.run(command, check=True, capture_output=True, text=True)
    return output, {
        "feature_setup_ns": feature_setup_ns,
        "compile_ns": compile_ns,
        "link_ns": time.perf_counter_ns() - start,
        "runtime_library_bytes": output.stat().st_size,
        "native_object_bytes": sum(
            path.stat().st_size for path in inputs.objects
        ),
        "compiler": subprocess.check_output(
            [compiler, "--version"], text=True
        ).strip(),
        "compiler_executable": shutil.which(compiler),
        "runtime_metadata": feature.metadata,
        "artifacts": [
            {
                "source": str(a.path.relative_to(ROOT)),
                "flags": a.compile_flags,
                "include_dirs": [str(p) for p in a.include_dirs],
            }
            for a in artifacts
        ],
        "link_command": command,
    }


def llvm_runner(
    values: list[float | None],
) -> tuple[Callable[[], None], Callable[[], list[float | None]]]:
    """
    title: JIT the verified unboxed reference with no fast-math flags.
    parameters:
      values:
        type: list[float | None]
    returns:
      type: tuple[Callable[[], None], Callable[[], list[float | None]]]
    """
    from llvmlite import binding as llvm

    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    target = llvm.Target.from_default_triple().create_target_machine(opt=2)
    module = llvm.parse_assembly(REFERENCE.read_text())
    module.triple = llvm.get_default_triple()
    module.data_layout = str(target.target_data)
    module.verify()
    engine = llvm.create_mcjit_compiler(module, target)
    engine.finalize_object()
    function = ctypes.CFUNCTYPE(
        None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64, ctypes.c_double
    )(engine.get_function_address("add_f64"))
    numbers: list[ctypes.c_double] = []
    for value in values:
        if value is None:
            raise ValueError("LLVM reference does not support null inputs")
        numbers.append(ctypes.c_double(value))
    source = (ctypes.c_double * len(values))(*numbers)
    output = (ctypes.c_double * len(values))()

    def invoke() -> None:
        """
        title: Execute one loop while retaining the JIT engine.
        """
        # The engine must outlive its executable pointer.
        _ = engine
        function(source, output, len(values), 0.5)

    def read() -> list[float | None]:
        """
        title: Read the preallocated reference output.
        returns:
          type: list[float | None]
        """
        return list(output)

    return invoke, read


def load_native(library: Path) -> ctypes.CDLL:
    """
    title: Bind only the existing opaque ABI signatures used by the baseline.
    parameters:
      library:
        type: Path
    returns:
      type: ctypes.CDLL
    """
    native = ctypes.CDLL(str(library))
    pointer = ctypes.c_void_p
    uint64, int32 = ctypes.c_uint64, ctypes.c_int32
    signatures = {
        "irx_arrow_table_import_stream": (int32, [pointer, pointer]),
        "irx_arrow_table_column_by_index": (int32, [pointer, int32, pointer]),
        "irx_arrow_table_release": (None, [pointer]),
        "irx_arrow_chunked_array_release": (None, [pointer]),
        "irx_arrow_column_compute": (
            int32,
            [
                ctypes.c_char_p,
                int32,
                pointer,
                uint64,
                int32,
                pointer,
                uint64,
                int32,
                pointer,
                pointer,
                pointer,
            ],
        ),
        "irx_arrow_series_index": (
            int32,
            [pointer, ctypes.c_int64, int32, pointer, pointer],
        ),
        "irx_arrow_sequence_length": (ctypes.c_int64, [pointer]),
        "irx_arrow_last_error": (ctypes.c_char_p, []),
    }
    for name, (result, args) in signatures.items():
        function = getattr(native, name)
        function.restype, function.argtypes = result, args
    return native


def check_native(native: ctypes.CDLL, status: int) -> None:
    """
    title: Reject failed native calls before inspecting their output slots.
    parameters:
      native:
        type: ctypes.CDLL
      status:
        type: int
    """
    if status:
        raise RuntimeError(native.irx_arrow_last_error().decode())


def native_runner(
    library: Path,
    column: pa.ChunkedArray,
    scalar: bool,
) -> tuple[
    Callable[[], None], Callable[[], list[float | None]], Callable[[], None]
]:
    """
    title: Exercise the existing opaque ABI and success-only output slots.
    parameters:
      library:
        type: Path
      column:
        type: pa.ChunkedArray
      scalar:
        type: bool
    returns:
      type: >-
        tuple[Callable[[], None], Callable[[], list[float | None]],
        Callable[[], None]]
    """
    import pyarrow as pa

    from pyarrow.cffi import ffi

    native = load_native(library)
    pointer, uint64, int32 = (ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int32)
    rhs_bits = int.from_bytes(ctypes.c_double(RHS), sys.byteorder)
    lhs = column[0] if scalar else pa.scalar(0.0)
    lhs_bits = (
        int.from_bytes(ctypes.c_double(lhs.as_py()), sys.byteorder)
        if lhs.is_valid
        else 0
    )

    table, left, output, bits, valid = (
        pointer(),
        pointer(),
        pointer(),
        uint64(),
        int32(),
    )
    stream = ffi.new("struct ArrowArrayStream *")
    reader = pa.table({"value": column}).to_reader()
    reader._export_to_c(int(ffi.cast("uintptr_t", stream)))
    try:
        check_native(
            native,
            native.irx_arrow_table_import_stream(
                int(ffi.cast("uintptr_t", stream)), ctypes.byref(table)
            ),
        )
        check_native(
            native,
            native.irx_arrow_table_column_by_index(
                table, 0, ctypes.byref(left)
            ),
        )
    finally:
        native.irx_arrow_table_release(table)
        if stream.release != ffi.NULL:
            stream.release(stream)

    def invoke() -> None:
        """
        title: Execute only the fixed approved addition operation.
        """
        check_native(
            native,
            native.irx_arrow_column_compute(
                b"add_checked",
                10,
                None if scalar else left,
                lhs_bits,
                int(lhs.is_valid),
                None,
                rhs_bits,
                1,
                ctypes.byref(output),
                ctypes.byref(bits),
                ctypes.byref(valid),
            ),
        )

    def release() -> None:
        """
        title: Release the result owner before the next invocation.
        """
        native.irx_arrow_chunked_array_release(output)
        output.value = None

    def read() -> list[float | None]:
        """
        title: Check every value and validity outside timed execution.
        returns:
          type: list[float | None]
        """
        if scalar:
            return [
                ctypes.c_double.from_buffer_copy(bits).value
                if valid.value
                else None
            ]
        if native.irx_arrow_sequence_length(output) != len(column):
            raise AssertionError("native output length differs from input")
        results: list[float | None] = []
        for index in range(len(column)):
            check_native(
                native,
                native.irx_arrow_series_index(
                    output, index, 10, ctypes.byref(bits), ctypes.byref(valid)
                ),
            )
            results.append(
                ctypes.c_double.from_buffer_copy(bits).value
                if valid.value
                else None
            )
        return results

    def close() -> None:
        """
        title: Release both owned native handles.
        """
        release()
        native.irx_arrow_chunked_array_release(left)

    # Invoke and release together so warm timings include output cleanup.
    def run() -> None:
        """
        title: Include output allocation and release in measured execution.
        """
        invoke()
        release()

    def checked_read() -> list[float | None]:
        """
        title: Materialize a result for the independent correctness oracle.
        returns:
          type: list[float | None]
        """
        invoke()
        try:
            return read()
        finally:
            release()

    return run, checked_read, close


def worker(
    backend: str,
    case: Case,
    library: Path,
    samples: int,
    iterations: int,
    arrow_major: int,
) -> dict[str, object]:
    """
    title: Measure one isolated backend/input after checking exact results.
    parameters:
      backend:
        type: str
      case:
        type: Case
      library:
        type: Path
      samples:
        type: int
      iterations:
        type: int
      arrow_major:
        type: int
    returns:
      type: dict[str, object]
    """
    start = time.perf_counter_ns()
    import resource

    import pyarrow as pa
    import pyarrow.compute as pc

    require_arrow_baseline(arrow_major)
    if (backend == "llvm" and case.null_every) or (
        backend == "irx-scalar" and case.name != "scalar"
    ):
        return {
            "backend": backend,
            "case": case.name,
            "status": "unsupported",
            "reason": "shape not implemented",
        }
    values = case.values()
    expected = [None if value is None else value + 0.5 for value in values]
    width = max(1, (case.length + case.chunks - 1) // case.chunks)
    chunks = [
        pa.array(
            [0.0] * case.offset + values[i : i + width], type=pa.float64()
        ).slice(case.offset)
        for i in range(0, max(1, case.length), width)
    ]
    column = pa.chunked_array(chunks, type=pa.float64())

    def close() -> None:
        """
        title: Provide a no-op cleanup for backends without owned handles.
        """
        return None

    if backend == "llvm":
        run, read = llvm_runner(values)
    elif backend in ("irx-scalar", "irx-series"):
        run, read, close = native_runner(
            library, column, backend == "irx-scalar"
        )
    else:
        rhs = pa.scalar(RHS, type=pa.float64())

        def run() -> None:
            """
            title: Execute the same fixed Arrow function through PyArrow.
            """
            # PyArrow's stubs omit this public re-export.
            pc.call_function("add_checked", [column, rhs])  # type: ignore[attr-defined]

        def read() -> list[float | None]:
            """
            title: Materialize PyArrow output outside measurement.
            returns:
              type: list[float | None]
            """
            result = cast(
                "pa.ChunkedArray",
                pc.call_function("add_checked", [column, rhs]),  # type: ignore[attr-defined]
            )
            if result.type != pa.float64():
                raise AssertionError("PyArrow result changed dtype")
            return cast(list[float | None], result.to_pylist())

    setup_ns = time.perf_counter_ns() - start
    # Use the original pool: Arrow's cached default ExecContext can retain it
    # even if Python later selects a proxy. A proxy would miss native buffers.
    pool = pa.default_memory_pool()
    baseline_bytes = pool.bytes_allocated()
    try:
        start = time.perf_counter_ns()
        run()
        cold_ns = time.perf_counter_ns() - start
        if read() != expected:
            raise AssertionError(f"incorrect {backend}/{case.name} result")
        allocations, allocated = (
            pool.num_allocations(),
            pool.total_bytes_allocated(),
        )
        timings: list[float] = []
        for _ in range(samples):
            start = time.perf_counter_ns()
            for _ in range(iterations):
                run()
            timings.append((time.perf_counter_ns() - start) / iterations)
        result = {
            "backend": backend,
            "case": case.name,
            "status": "ok",
            "length": case.length,
            "setup_ns": setup_ns,
            "cold_first_call_ns": cold_ns,
            "warm_ns": timings,
            "warm_median_ns": statistics.median(timings),
            "arrow_pool_allocations": pool.num_allocations() - allocations,
            "arrow_pool_bytes": pool.total_bytes_allocated() - allocated,
            "arrow_pool_peak_bytes": pool.max_memory(),
            "arrow_pool_live_bytes": pool.bytes_allocated(),
            "arrow_pool_input_bytes": baseline_bytes,
            "arrow_pool_live_delta_bytes": (
                pool.bytes_allocated() - baseline_bytes
            ),
            "shape": "scalar" if backend == "irx-scalar" else "array/series",
            "measured_calls": samples * iterations,
            "compiler_loaded": "irx.builder" in sys.modules,
            "process_peak_rss_bytes": resource.getrusage(
                resource.RUSAGE_SELF
            ).ru_maxrss
            * 1024,
            "output_policy": "preallocated"
            if backend == "llvm"
            else "allocate/release",
        }
        if read() != expected:
            raise AssertionError("warm result differs from oracle")
        return result
    finally:
        close()


def markdown(
    report: dict[str, object], results: list[dict[str, object]]
) -> str:
    """
    title: Render measured results without inventing unsupported comparisons.
    parameters:
      report:
        type: dict[str, object]
      results:
        type: list[dict[str, object]]
    returns:
      type: str
    """
    lines = [
        "# Arrow-first M0 baseline",
        "",
        f"Revision: `{report['revision']}`",
        "",
        f"Arrow major: `{report['requested_arrow_major']}`. "
        "Arrow 24 results are historical, not Arrow 26 qualification.",
        "",
        "| Case | Backend | Cold ns | Warm median ns | Pool allocations |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for row in results:
        lines.append(
            f"| {row['case']} | {row['backend']} | "
            f"{row.get('cold_first_call_ns', 'unsupported')} | "
            f"{row.get('warm_median_ns', '-')} | "
            f"{row.get('arrow_pool_allocations', '-')} |"
        )
    lines.extend(
        [
            "",
            "Allocation counts cover Arrow pool buffers only, not C++ "
            "object boxing. Allocation deltas cover warm calls only. "
            "Pool peak and RSS include setup. LLVM preallocates output; "
            "Arrow allocates/releases it. See JSON for raw samples, input and "
            "source hashes, toolchain, versions and build time.",
            "",
        ]
    )
    return "\n".join(lines)


def wheel_sizes() -> list[dict[str, str | int]]:
    """
    title: Snapshot wheel footprints without claiming a fresh build.
    summary: >-
      Build first with makim all.build. An empty list means wheel size was not
      measured; it is not a zero-byte installation. Hashes identify the exact
      measured artifacts independently of the working tree dirty flag.
    returns:
      type: list[dict[str, str | int]]
    """
    return [
        {
            "path": str(path.relative_to(ROOT)),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted((ROOT / "packages").glob("*/dist/*.whl"))
    ]


def main() -> None:
    """
    title: Build once, isolate measurements and publish raw and summary output.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".tmp/arrow-first"
    )
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--cxx", default="clang++")
    parser.add_argument("--cxx-flag", action="append", default=[])
    parser.add_argument(
        "--arrow-major",
        type=int,
        choices=(HISTORICAL_ARROW_MAJOR, TARGET_ARROW_MAJOR),
        default=TARGET_ARROW_MAJOR,
        help="exact 26.0.1 target; 24 captures the historical 24.0.0 baseline",
    )
    parser.add_argument(
        "--case", choices=[c.name for c in cases()], action="append"
    )
    parser.add_argument("--worker", choices=BACKENDS, help=argparse.SUPPRESS)
    parser.add_argument("--library", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.samples < 1 or args.iterations < 1:
        parser.error("samples and iterations must be positive")
    if sys.platform != "linux":
        parser.error(
            "this baseline qualifies Linux only (RSS uses Linux units)"
        )
    selected = [c for c in cases() if not args.case or c.name in args.case]
    if args.worker:
        if len(selected) != 1 or args.library is None:
            parser.error("worker requires exactly one case and a library")
        print(
            json.dumps(
                worker(
                    args.worker,
                    selected[0],
                    args.library,
                    args.samples,
                    args.iterations,
                    args.arrow_major,
                )
            )
        )
        return
    require_arrow_baseline(args.arrow_major)
    args.output.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="build-", dir=args.output) as work:
        library, build = build_runtime(
            Path(work), args.cxx, tuple(args.cxx_flag)
        )
        for case in selected:
            for backend in BACKENDS:
                start = time.perf_counter_ns()
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        backend,
                        "--case",
                        case.name,
                        "--library",
                        str(library),
                        "--samples",
                        str(args.samples),
                        "--iterations",
                        str(args.iterations),
                        "--arrow-major",
                        str(args.arrow_major),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode:
                    raise RuntimeError(
                        f"{backend}/{case.name} worker failed:\n"
                        f"{completed.stderr}"
                    )
                row = json.loads(completed.stdout)
                row["worker_wall_ns"] = time.perf_counter_ns() - start
                results.append(row)
    sources = [
        INPUTS,
        REFERENCE,
        Path(__file__).resolve(),
        ROOT / "poetry.lock",
        ROOT / "pyproject.toml",
        ROOT / "packages/irx/pyproject.toml",
        ROOT / "packages/irx/src/irx/builder/runtime/arrowcpp.py",
        ROOT / "packages/irx/src/irx/builder/runtime/linking.py",
        ROOT / "packages/irx/src/irx/builder/runtime/array/feature.py",
        *sorted(
            (ROOT / "packages/irx/src/irx/builder/runtime/arrow/native").glob(
                "*.*"
            )
        ),
    ]
    import pyarrow as pa

    from llvmlite import binding as llvm

    report: dict[str, object] = {
        "schema_version": 1,
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()
        ),
        "versions": {
            name: version(name)
            for name in (
                "arxlang",
                "astx",
                "pyirx",
                "arxpy",
                "arxjit",
                "airx",
                "pyarrow",
                "arx-arrowcpp-sources",
                "llvmlite",
            )
        },
        "manifests": {
            path.parent.name: tomllib.loads(path.read_text())["project"][
                "version"
            ]
            for path in sorted((ROOT / "packages").glob("*/pyproject.toml"))
        },
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cpuinfo": Path("/proc/cpuinfo").read_text(),
        "environment": {
            key: os.environ.get(key)
            for key in (
                "ARX_RUNTIME_TYPECHECK",
                "ARROW_USER_SIMD_LEVEL",
                "OMP_NUM_THREADS",
                "ARROW_DEFAULT_MEMORY_POOL",
            )
        },
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sources
            if path.is_file()
        },
        "samples": args.samples,
        "iterations": args.iterations,
        "requested_arrow_major": args.arrow_major,
        "qualification_arrow_version": TARGET_ARROW_VERSION,
        "wheel_artifacts": wheel_sizes(),
        "inputs": json.loads(INPUTS.read_text()),
        "llvm": llvm.llvm_version_info,
        "arrow_cpp": pa.cpp_version,
        "arrow_memory_pool": pa.default_memory_pool().backend_name,
        "arrow_simd": str(pa.runtime_info()),
        "build": build,
        "results": results,
        "scope": "add_checked f64 baseline, not stdlib.math.sqrt; "
        "LLVM reference is not frontend throughput; Arrow counters "
        "exclude C++ object/Python heap allocations; no page-cache flush",
    }
    (args.output / "baseline.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    (args.output / "baseline.md").write_text(markdown(report, results))
    print(args.output / "baseline.json")


if __name__ == "__main__":
    main()
