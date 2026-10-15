"""
title: Cleanup of partial list comprehensions under real allocation failure.
"""

import os
import shutil
import subprocess
import sys

from pathlib import Path

import astx
import pytest

from irx.builder import Builder
from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import link_executable
from llvmlite import binding as llvm


def test_partial_comprehension_releases_all_owners(tmp_path: Path) -> None:
    """
    title: Release partially built and previously completed list owners on OOM.
    parameters:
      tmp_path:
        type: Path
    """
    if sys.platform != "linux" or shutil.which("clang") is None:
        pytest.skip("allocation accounting requires GNU wrapping and Clang")
    body = astx.Block()
    for name in ("first", "second"):
        expression = astx.ListComprehension(
            element=astx.Identifier("item"),
            generators=[
                astx.ComprehensionClause(
                    astx.Identifier("item"),
                    astx.LiteralList(
                        [astx.LiteralInt32(index) for index in range(12)]
                    ),
                )
            ],
        )
        body.append(
            astx.VariableDeclaration(
                name,
                astx.ListType([astx.Int32()]),
                value=expression,
            )
        )
    body.append(astx.FunctionReturn(astx.LiteralInt32(0)))
    module = astx.Module()
    module.block.append(
        astx.FunctionDef(
            astx.FunctionPrototype("main", astx.Arguments(), astx.Int32()),
            body,
        )
    )
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
        "void* __real_realloc(void*, size_t); void __real_free(void*);\n"
        "void* __wrap_realloc(void* p, size_t n) {\n"
        '  const char* fail = getenv("FAIL_ALLOCATION");\n'
        "  if (fail && ++calls == atol(fail)) return NULL;\n"
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
        linker_flags=("-Wl,--wrap=realloc", "-Wl,--wrap=free"),
    )
    allocation_count = 6
    for index in range(1, allocation_count + 2):
        result = subprocess.run(
            [str(executable)],
            env={**os.environ, "FAIL_ALLOCATION": str(index)},
            capture_output=True,
            text=True,
            check=False,
        )
        # Each list grows at capacities 4, 8 and 16; the seventh run succeeds.
        assert result.returncode == (1 if index <= allocation_count else 0), (
            result.stderr
        )
        if result.returncode:
            assert "ARX-RUNTIME-LIST-003" in result.stderr
