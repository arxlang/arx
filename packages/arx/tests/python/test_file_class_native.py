"""
title: >-
  Counted native File allocation, publication, close, and failure rollback.
"""

import shutil
import subprocess
import sys

from pathlib import Path

import pytest

from arx.codegen import ArxBuilder
from arx.io import ArxIO
from arx.lexer import Lexer
from arx.parser import Parser
from irx.builder.runtime.features import NativeArtifact
from irx.builder.runtime.linking import link_executable
from llvmlite import binding as llvm

AUDITOR = r"""#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static int calls, live, opened, released;
void* __real_malloc(size_t size);
void* __real_calloc(size_t count, size_t size);
void __real_free(void* value);
void* __wrap_malloc(size_t size) {
  void* out = ++calls == FAULT ? NULL : __real_malloc(size);
  if (out) live++;
  return out;
}
void* __wrap_calloc(size_t count, size_t size) {
  void* out = ++calls == FAULT ? NULL : __real_calloc(count, size);
  if (out) live++;
  return out;
}
void __wrap_free(void* value) {
  if (value) live--;
  __real_free(value);
}
typedef struct irx_file irx_file;
int32_t __real_irx_file_open(const char*, const char*, irx_file**, char*);
int32_t __real_irx_file_release(irx_file*, char*);
int32_t __wrap_irx_file_open(const char* path, const char* mode,
                           irx_file** out, char* error) {
  int32_t status = __real_irx_file_open(path, mode, out, error);
  if (!status) opened++;
  return status;
}
int32_t __wrap_irx_file_release(irx_file* value, char* error) {
  if (value) released++;
  return __real_irx_file_release(value, error);
}
__attribute__((destructor)) static void audit(void) {
  fprintf(stderr, "AUDIT live=%d opened=%d released=%d\n",
          live, opened, released);
}
"""


@pytest.mark.parametrize("factory", ["open", "File"])
@pytest.mark.parametrize(
    "case, fault",
    [
        ("success", 0),
        ("class_token", 1),
        ("class_payload", 2),
        ("native_wrapper", 3),
        ("open_failure", 0),
    ],
)
def test_counted_file_lifetime(
    tmp_path: Path, factory: str, case: str, fault: int
) -> None:
    """
    title: >-
      Class and native handle ownership release exactly once, even on error.
    parameters:
      tmp_path:
        type: Path
      factory:
        type: str
      case:
        type: str
      fault:
        type: int
    """
    if shutil.which("clang") is None or sys.platform != "linux":
        pytest.skip(
            "counted allocation requires clang and GNU linker wrapping"
        )
    path = "missing/stream" if case == "open_failure" else "stream"
    ArxIO.string_to_buffer(f'''```
title: Counted File lifetime
```
fn share(stream: file) -> File:
  return stream
fn main() -> i32:
  var stream: File = {factory}("{path}", "w")
  var alias: File = share(stream)
  alias.write("saved")
  stream.close()
  alias.close()
  return 0
''')
    builder = ArxBuilder()
    module = llvm.parse_assembly(
        builder.translate(Parser().parse(Lexer().lex()))
    )
    module.verify()
    primary = tmp_path / "module.o"
    primary.write_bytes(builder.translator.target_machine.emit_object(module))
    wrapper = tmp_path / "audit.c"
    wrapper.write_text(AUDITOR, encoding="utf-8")
    program = tmp_path / "program"
    link_executable(
        primary_object=primary,
        output_file=program,
        artifacts=(
            *builder.translator.runtime_features.native_artifacts(),
            NativeArtifact(
                "c_source", wrapper, compile_flags=(f"-DFAULT={fault}",)
            ),
        ),
        linker_flags=tuple(
            f"-Wl,--wrap={name}"
            for name in (
                "malloc",
                "calloc",
                "free",
                "irx_file_open",
                "irx_file_release",
            )
        ),
    )
    result = subprocess.run(
        [str(program)],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    if case == "success":
        assert result.returncode == 0, result.stderr
        assert "AUDIT live=0 opened=1 released=1" in result.stderr
        assert (tmp_path / "stream").read_text() == "saved"
    else:
        assert result.returncode != 0
        assert "AUDIT live=0 opened=0 released=0" in result.stderr
        assert not (tmp_path / "stream").exists()
