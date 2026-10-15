#!/usr/bin/env python3
"""
title: Exercise Arrow ownership paths under native sanitizers.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from arrow_ownership_programs import ownership_programs
from llvmlite import binding as llvm

import astx

from irx.builder import Builder
from irx.builder.runtime.arrow.feature import (
    ARROW_RUNTIME_CAPABILITIES,
    arrow_native_source_dir,
    build_arrow_native_artifact,
)
from irx.builder.runtime.arrowcpp import arrowcpp_linker_flags
from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import compile_native_artifacts

FAILURE_MARKERS = {
    "scalar_failure": "ARX-RUNTIME-NULL-001",
    "tabular_failure": "ARX-RUNTIME-ARROW-001",
    "container_failure": "ARX-RUNTIME-NULL-001",
    "array_failure": "ARX_RUNTIME_FAIL|ARX-RUNTIME-NULL-001|",
    "descriptor_failure": "ARX_RUNTIME_FAIL|ARX-RUNTIME-ARROW-001|",
    "nullable_failure": "ARX_RUNTIME_FAIL|ARX-RUNTIME-NULL-001|",
}

SANITIZER_FLAGS = (
    "-fsanitize=address,undefined,leak",
    "-fno-omit-frame-pointer",
    "-O1",
)
SANITIZER_CAPABILITIES = (
    "core",
    "array",
    "tensor",
    "dataframe",
    "record_batch",
)
HARNESS_SOURCE = r"""
#include "irx_arrow_abi_generated.h"

#include <arrow/memory_pool.h>

#include <cstdint>
#include <cstdio>

#define IRX_REQUIRE_OK(expression)                                      \
  do {                                                                  \
    const irx_arrow_status status = (expression);                        \
    if (status != IRX_ARROW_STATUS_OK) {                                 \
      std::fprintf(stderr, "%s failed with status %d: %s\n",           \
                   #expression, status, irx_arrow_last_error());         \
      return false;                                                      \
    }                                                                   \
  } while (false)

static bool exercise_array_and_table(int64_t iteration) {
  irx_arrow_error_handle* error = nullptr;
  irx_arrow_array_builder_handle* builder = nullptr;
  IRX_REQUIRE_OK(irx_arrow_array_builder_new(
      IRX_ARROW_TYPE_INT64, &builder, &error));
  IRX_REQUIRE_OK(irx_arrow_array_builder_append_int(
      builder, iteration, &error));
  IRX_REQUIRE_OK(irx_arrow_array_builder_append_null(
      builder, 1, &error));

  irx_arrow_array_handle* array = nullptr;
  IRX_REQUIRE_OK(irx_arrow_array_builder_finish(
      &builder, &array, &error));
  if (builder != nullptr) {
    std::fprintf(stderr, "array builder was not consumed\n");
    return false;
  }

  const char* names[] = {"value"};
  irx_arrow_array_handle* arrays[] = {array};
  irx_arrow_table_handle* table = nullptr;
  IRX_REQUIRE_OK(irx_arrow_table_new_from_arrays(
      1, names, arrays, &table, &error));

  irx_arrow_chunked_array_handle* column = nullptr;
  IRX_REQUIRE_OK(irx_arrow_table_column_by_index(
      table, 0, &column, &error));
  if ((iteration % 2) == 0) {
    IRX_REQUIRE_OK(irx_arrow_table_release(&table, &error));
    IRX_REQUIRE_OK(irx_arrow_chunked_array_release(&column, &error));
  } else {
    IRX_REQUIRE_OK(irx_arrow_chunked_array_release(&column, &error));
    IRX_REQUIRE_OK(irx_arrow_table_release(&table, &error));
  }
  IRX_REQUIRE_OK(irx_arrow_array_release(&array, &error));
  if (table != nullptr || column != nullptr || array != nullptr) {
    std::fprintf(stderr, "released Arrow output remained non-null\n");
    return false;
  }
  return true;
}

static bool exercise_tensor(int64_t iteration) {
  irx_arrow_error_handle* error = nullptr;
  const int64_t shape[] = {2};
  irx_arrow_tensor_builder_handle* builder = nullptr;
  IRX_REQUIRE_OK(irx_arrow_tensor_builder_new(
      IRX_ARROW_TYPE_INT64, 1, shape, nullptr, &builder, &error));
  IRX_REQUIRE_OK(irx_arrow_tensor_builder_append_int(
      builder, iteration, &error));
  IRX_REQUIRE_OK(irx_arrow_tensor_builder_append_int(
      builder, iteration + 1, &error));

  irx_arrow_tensor_handle* tensor = nullptr;
  IRX_REQUIRE_OK(irx_arrow_tensor_builder_finish(
      &builder, &tensor, &error));
  IRX_REQUIRE_OK(irx_arrow_tensor_release(&tensor, &error));
  if (builder != nullptr || tensor != nullptr) {
    std::fprintf(stderr, "released tensor output remained non-null\n");
    return false;
  }
  return true;
}

static void release_schema_source(ArrowSchema* schema) {
  schema->release = nullptr;
}

static bool exercise_schema() {
  ArrowSchema item{};
  item.format = "u";
  item.name = "item";
  item.flags = 2;
  item.release = release_schema_source;
  ArrowSchema* children[] = {&item};
  ArrowSchema source{};
  source.format = "+l";
  source.name = "values";
  source.n_children = 1;
  source.children = children;
  source.release = release_schema_source;
  irx_arrow_error_handle* error = nullptr;
  irx_arrow_schema_handle* owner = nullptr;
  IRX_REQUIRE_OK(irx_arrow_schema_import_copy(&source, &owner, &error));
  if (source.release != release_schema_source ||
      item.release != release_schema_source) {
    std::fprintf(stderr, "schema copy consumed producer callbacks\n");
    return false;
  }
  source.release(&source);
  item.release(&item);
  ArrowSchema exported{};
  IRX_REQUIRE_OK(irx_arrow_schema_export(owner, &exported, &error));
  IRX_REQUIRE_OK(irx_arrow_schema_release(&owner, &error));
  if (exported.release == nullptr || exported.n_children != 1) {
    return false;
  }
  exported.release(&exported);
  return owner == nullptr && exported.release == nullptr;
}

int main() {
  constexpr int64_t kIterations = 256;
  arrow::MemoryPool* pool = arrow::default_memory_pool();
  const int64_t baseline = pool->bytes_allocated();
  for (int64_t iteration = 0; iteration < kIterations; ++iteration) {
    if (!exercise_array_and_table(iteration) ||
        !exercise_tensor(iteration) || !exercise_schema()) {
      return 1;
    }
    if (pool->bytes_allocated() != baseline) {
      std::fprintf(stderr, "live Arrow pool bytes grew after iteration %lld\n",
                   static_cast<long long>(iteration));
      return 2;
    }
  }
  return 0;
}
""".lstrip()


def sanitizer_artifact(capability: str) -> NativeArtifact:
    """
    title: Build one sanitizer-instrumented Arrow runtime artifact.
    parameters:
      capability:
        type: str
    returns:
      type: NativeArtifact
    """
    if capability not in ARROW_RUNTIME_CAPABILITIES:
        raise ValueError(f"Unknown Arrow runtime capability '{capability}'")
    artifact = build_arrow_native_artifact(capability)
    return replace(
        artifact,
        compile_flags=(*artifact.compile_flags, *SANITIZER_FLAGS),
    )


def write_harness(build_dir: Path) -> NativeArtifact:
    """
    title: Write and describe the sanitizer ownership harness.
    parameters:
      build_dir:
        type: Path
    returns:
      type: NativeArtifact
    """
    source = build_dir / "arrow_ownership_sanitizer_harness.cc"
    source.write_text(HARNESS_SOURCE, encoding="utf8")
    native_root = arrow_native_source_dir()
    buffer_native_root = native_root.parent.parent / "buffer" / "native"
    return NativeArtifact(
        kind="cxx_source",
        path=source,
        include_dirs=(
            native_root,
            buffer_native_root.resolve(),
            *build_arrow_native_artifact("core").include_dirs,
        ),
        compile_flags=("-std=c++20", *SANITIZER_FLAGS),
    )


def build_harness(build_dir: Path, cxx_binary: str) -> Path:
    """
    title: Compile and link the Arrow ownership sanitizer harness.
    parameters:
      build_dir:
        type: Path
      cxx_binary:
        type: str
    returns:
      type: Path
    """
    artifacts = (
        *(
            sanitizer_artifact(capability)
            for capability in SANITIZER_CAPABILITIES
        ),
        write_harness(build_dir),
    )
    link_inputs = compile_native_artifacts(
        artifacts,
        build_dir,
        cxx_binary=cxx_binary,
    )
    executable = build_dir / "arrow_ownership_sanitizer_harness"
    command = [cxx_binary, *SANITIZER_FLAGS]
    command.extend(str(path) for path in link_inputs.objects)
    command.extend(link_inputs.linker_flags)
    command.extend(arrowcpp_linker_flags())
    command.extend(("-o", str(executable)))
    subprocess.run(command, check=True)
    return executable


def run_harness(
    executable: Path,
    *,
    detect_leaks: bool = True,
    expected_status: int = 0,
    failure_marker: str = "ARX_ASSERT_FAIL|",
) -> None:
    """
    title: Run the ownership harness with fail-fast sanitizer settings.
    parameters:
      executable:
        type: Path
      detect_leaks:
        type: bool
      expected_status:
        type: int
      failure_marker:
        type: str
    """
    environment = os.environ.copy()
    environment["ASAN_OPTIONS"] = (
        f"detect_leaks={int(detect_leaks)}:halt_on_error=1:exitcode=86"
    )
    environment["UBSAN_OPTIONS"] = (
        "halt_on_error=1:print_stacktrace=1:exitcode=87"
    )
    if detect_leaks:
        environment["LSAN_OPTIONS"] = "exitcode=23"
    result = subprocess.run(
        [str(executable)],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    if result.returncode != expected_status:
        raise RuntimeError(
            f"{executable.name}: expected exit {expected_status}, "
            f"got {result.returncode}\n{result.stdout}{result.stderr}"
        )
    if expected_status != 0 and failure_marker not in result.stderr:
        raise RuntimeError(
            f"missing expected {failure_marker} record: {result.stderr}"
        )


def build_generated_program(
    module: astx.Module, build_dir: Path, cxx_binary: str, clang_binary: str
) -> Path:
    """
    title: Instrument generated LLVM and all its registered native artifacts.
    parameters:
      module:
        type: astx.Module
      build_dir:
        type: Path
      cxx_binary:
        type: str
      clang_binary:
        type: str
    returns:
      type: Path
    """
    builder = Builder()
    builder.translate(module)
    ir_module = builder.translator._llvm.module
    for function in ir_module.functions:
        if not function.is_declaration:
            function.attributes.add("sanitize_address")
            function._clear_string_cache()
    ir_text = str(ir_module)
    llvm.parse_assembly(ir_text).verify()
    source = build_dir / "program.ll"
    source.write_text(ir_text, encoding="utf8")
    primary = build_dir / "program.o"
    subprocess.run(
        [
            clang_binary,
            "-O1",
            "-fPIC",
            "-fsanitize=address",
            "-c",
            str(source),
            "-o",
            str(primary),
        ],
        check=True,
    )
    # Compiling .ll with a sanitizer flag alone can leave functions untouched.
    # Require emitted instrumentation, not just a linked sanitizer library.
    if b"__asan_report" not in primary.read_bytes():
        raise RuntimeError("generated LLVM lacks ASan instrumentation")
    artifacts = tuple(
        replace(item, compile_flags=(*item.compile_flags, *SANITIZER_FLAGS))
        for item in builder.translator.runtime_features.native_artifacts()
    )
    inputs = compile_native_artifacts(
        artifacts, build_dir, clang_binary=clang_binary, cxx_binary=cxx_binary
    )
    executable = build_dir / "program"
    subprocess.run(
        [
            cxx_binary,
            *SANITIZER_FLAGS,
            str(primary),
            *(str(path) for path in inputs.objects),
            *inputs.linker_flags,
            *builder.translator.runtime_features.linker_flags(),
            "-o",
            str(executable),
        ],
        check=True,
    )
    return executable


def main(argv: Sequence[str] | None = None) -> int:
    """
    title: Build and execute the Arrow ownership sanitizer harness.
    parameters:
      argv:
        type: Sequence[str] | None
    returns:
      type: int
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clang",
        default=os.environ.get("CC", "clang"),
        help="Clang compiler used to instrument generated LLVM IR",
    )
    parser.add_argument(
        "--cxx",
        default=os.environ.get("CXX", "c++"),
        help="C++ compiler with ASan, UBSan, and LSan support",
    )
    parser.add_argument(
        "--skip-leak-detection",
        action="store_true",
        help="disable LSan only when the execution environment uses ptrace",
    )
    arguments = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(
        prefix="irx-arrow-ownership-sanitizers-"
    ) as temporary_directory:
        build_dir = Path(temporary_directory)
        executable = build_harness(build_dir, arguments.cxx)
        run_harness(
            executable,
            detect_leaks=not arguments.skip_leak_detection,
        )
        for name, module, expected in ownership_programs():
            program_dir = build_dir / name
            program_dir.mkdir()
            program = build_generated_program(
                module, program_dir, arguments.cxx, arguments.clang
            )
            run_harness(
                program,
                detect_leaks=not arguments.skip_leak_detection,
                expected_status=expected,
                failure_marker=FAILURE_MARKERS.get(name, "ARX_ASSERT_FAIL|"),
            )
            print(f"Generated ownership sanitizer program passed: {name}")

    print("Arrow ownership sanitizer harness passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
