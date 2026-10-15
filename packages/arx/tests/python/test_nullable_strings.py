"""
title: Nullable strings and class field lifecycle across compiled boundaries.
"""

import os
import shutil
import subprocess
import sys

from pathlib import Path

import pytest

from irx.builder import Builder
from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import link_executable
from llvmlite import binding as llvm

from .test_nullable_operations import execute, parse
from .test_tabular_values import example_body


def test_nullable_strings_example(tmp_path: Path) -> None:
    """
    title: Copy, return, replace and destroy present or absent owned strings.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(example_body("nullable_strings"), tmp_path / "strings")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("failures", [False, True])
def test_nullable_string_allocations_balance(
    tmp_path: Path, failures: bool
) -> None:
    """
    title: Balance normal cross-call and failed same-frame string lifetimes.
    parameters:
      tmp_path:
        type: Path
      failures:
        type: bool
    """
    if sys.platform != "linux" or shutil.which("clang") is None:
        pytest.skip("allocation accounting requires GNU wrapping and Clang")
    source = example_body("nullable_strings")
    if failures:
        # Fatal native diagnostics currently unwind only the active function.
        # Isolate the allocation-failure guarantee from that tracked M2 gap.
        source = """class TextBox:
  @[public, mutable]
  text: str = "initial"
  @[public, mutable]
  empty: str
fn main() -> i32:
  var box: TextBox = TextBox()
  var value: str | none = "owned"
  var other: str | none = value
  box.text = expect_valid(other)
  box.text = box.text
  value = none
  other = none
  return 0
"""
    module = parse(source)
    builder = Builder()
    parsed = llvm.parse_assembly(builder.translate(module))
    parsed.verify()
    machine = llvm.Target.from_default_triple().create_target_machine()
    primary = tmp_path / "program.o"
    primary.write_bytes(machine.emit_object(parsed))
    shim = tmp_path / "accounting.c"
    shim.write_text(
        "#include <stdlib.h>\n#include <stdio.h>\n"
        "static long live, calls;\n"
        "void* __real_malloc(size_t); void __real_free(void*);\n"
        "void* __wrap_malloc(size_t n) {\n"
        '  const char* fail = getenv("FAIL_ALLOCATION");\n'
        "  if (fail && ++calls == atol(fail)) return NULL;\n"
        "  void* p = __real_malloc(n); if(p) ++live; return p; }\n"
        "void __wrap_free(void* p) { if(p) --live; __real_free(p); }\n"
        "__attribute__((destructor)) static void check(void) {\n"
        '  if(live) { fprintf(stderr, "leaked owners: %ld\\n", live); '
        "_Exit(99); }}\n"
    )
    executable = tmp_path / "accounted"
    link_executable(
        primary,
        executable,
        (
            *builder.translator.runtime_features.native_artifacts(),
            NativeArtifact(kind="c_source", path=shim),
        ),
        linker_flags=("-Wl,--wrap=malloc", "-Wl,--wrap=free"),
    )
    saw_failure = False
    saw_success = False
    for index in range(1, 33) if failures else (0,):
        result = subprocess.run(
            [str(executable)],
            env={**os.environ, "FAIL_ALLOCATION": str(index)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode in (0, 1), result.stderr
        if result.returncode:
            saw_failure = True
            assert "allocation failed" in result.stderr
        else:
            saw_success = True
    assert saw_success
    assert saw_failure is failures


def test_default_strings_in_distinct_functions(tmp_path: Path) -> None:
    """
    title: Default string storage is independent despite repeated local names.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(
        "fn first() -> str:\n  var value: str\n  return value\n"
        "fn second() -> str:\n  var value: str\n  return value\n"
        "fn main() -> i32:\n  assert first() == second()\n  return 0\n",
        tmp_path / "defaults",
    )
    assert result.returncode == 0, result.stderr
