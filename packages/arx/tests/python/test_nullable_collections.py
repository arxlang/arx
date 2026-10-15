"""
title: Optional by-value list and tensor owners across compiled boundaries.
"""

import os
import shutil
import subprocess
import sys

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from irx.analysis import analyze
from irx.builder import Builder
from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import link_executable
from irx.diagnostics import SemanticError
from llvmlite import binding as llvm

from .test_nullable_operations import execute, parse
from .test_tabular_values import example_body


def test_nullable_collections_example(tmp_path: Path) -> None:
    """
    title: Execute independent aggregate validity, payload retention and drop.
    parameters:
      tmp_path:
        type: Path
    """
    source = example_body("nullable_collections")
    text = ArxBuilder().translate(parse(source))
    llvm.parse_assembly(text).verify()
    assert "irx_list_destroy" in text
    assert "irx_buffer_view_release" in text
    result = execute(source, tmp_path / "collections")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "statement",
    [
        "var alias: list[i32] | none = value",
        "value = value",
    ],
)
def test_optional_list_cannot_copy_unique_storage(statement: str) -> None:
    """
    title: Nullable wrapping does not turn unique list storage into an alias.
    parameters:
      statement:
        type: str
    """
    with pytest.raises(SemanticError, match="unique"):
        analyze(
            parse(
                "fn main() -> i32:\n"
                "  var value: list[i32] | none = none\n"
                f"  {statement}\n  return 0\n"
            )
        )


def test_optional_list_append_requires_validity() -> None:
    """
    title: Reject appending to an optional owner without a validity proof.
    """
    with pytest.raises(SemanticError, match="list target"):
        analyze(
            parse(
                "fn main() -> i32:\n  var values: list[i32] | none = none\n"
                "  values.append(1)\n  return 0\n"
            )
        )


@pytest.mark.parametrize("type_name", ["list[i32]", "tensor[i32, 2]"])
def test_absent_collection_unwrap(tmp_path: Path, type_name: str) -> None:
    """
    title: Guard validity before accessing an absent aggregate payload.
    parameters:
      tmp_path:
        type: Path
      type_name:
        type: str
    """
    result = execute(
        f"fn main() -> i32:\n  var value: {type_name} | none = none\n"
        "  expect_valid(value)\n  return 0\n",
        tmp_path / "missing-collection",
    )
    assert result.returncode != 0
    assert "ARX-RUNTIME-NULL-001" in result.stderr


@pytest.mark.parametrize("mode", ["normal", "allocation", "bounds"])
def test_nullable_collection_allocations_balance(
    tmp_path: Path, mode: str
) -> None:
    """
    title: Balance optional aggregate owners across copies, growth and failure.
    parameters:
      tmp_path:
        type: Path
      mode:
        type: str
    """
    if sys.platform != "linux" or shutil.which("clang") is None:
        pytest.skip("allocation accounting requires GNU wrapping and Clang")
    source = example_body("nullable_collections")
    if mode != "normal":
        # The error path guarantees cleanup in the active generated frame;
        # cross-frame fatal unwinding remains a separately tracked M2 item.
        source = """class Lists:
  @[public, mutable]
  values: list[i32] | none
fn empty() -> list[i32]:
  var values: list[i32]
  return values
fn main() -> i32:
  var box: Lists = Lists()
  box.values = empty()
  var values: list[i32] | none = empty()
  if is_valid(values):
    var index: i32 = 0
    while index < 12:
      if is_valid(values):
        values.append(index)
      index = index + 1
  values = none
  return 0
"""
    if mode == "bounds":
        source = source.replace(
            "  values = none\n",
            "  if is_valid(values):\n    assert values[99] == 0\n"
            "  values = none\n",
        )
    builder = Builder()
    parsed = llvm.parse_assembly(builder.translate(parse(source)))
    parsed.verify()
    machine = llvm.Target.from_default_triple().create_target_machine()
    primary = tmp_path / "program.o"
    primary.write_bytes(machine.emit_object(parsed))
    shim = tmp_path / "accounting.c"
    shim.write_text(
        "#include <stdlib.h>\n#include <stdio.h>\n"
        "static long live, calls;\n"
        "void* __real_malloc(size_t); void __real_free(void*);\n"
        "void* __real_realloc(void*, size_t);\n"
        "static int fail(void) { ++calls;\n"
        '  const char* at = getenv("FAIL_ALLOCATION");\n'
        "  return at && calls == atol(at); }\n"
        "void* __wrap_malloc(size_t n) {\n"
        "  if (fail()) return NULL;\n"
        "  void* p = __real_malloc(n); if(p) ++live; return p; }\n"
        "void* __wrap_realloc(void* p, size_t n) {\n"
        "  if (fail()) return NULL;\n"
        "  int fresh = p == NULL; void* q = __real_realloc(p, n);\n"
        "  if(q && fresh) ++live; return q; }\n"
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
        linker_flags=(
            *builder.translator.runtime_features.linker_flags(),
            "-Wl,--wrap=malloc",
            "-Wl,--wrap=realloc",
            "-Wl,--wrap=free",
        ),
    )
    failed = 0
    succeeded = 0
    for index in range(1, 13) if mode == "allocation" else (0,):
        result = subprocess.run(
            [str(executable)],
            env={**os.environ, "FAIL_ALLOCATION": str(index)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode in (0, 1), result.stderr
        if result.returncode:
            failed += 1
            message = (
                "index out of range"
                if mode == "bounds"
                else "allocation failed"
            )
            assert message in result.stderr
        else:
            succeeded += 1
    assert bool(succeeded) is (mode != "bounds")
    # One class allocation and three list capacity allocations.
    expected_failures = {"normal": 0, "allocation": 4, "bounds": 1}
    assert failed == expected_failures[mode]


@pytest.mark.parametrize("type_name", ["list[i32]", "tensor[i32, 2]"])
def test_nullable_collection_index_requires_validity(type_name: str) -> None:
    """
    title: Reject optional collection indexing before unsafe lowering.
    parameters:
      type_name:
        type: str
    """
    with pytest.raises(SemanticError, match="requires proven validity"):
        analyze(
            parse(
                f"fn main() -> i32:\n  var value: {type_name} | none = none\n"
                "  return value[0]\n"
            )
        )
