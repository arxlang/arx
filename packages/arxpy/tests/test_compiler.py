"""
title: End-to-end tests for the public ArxPy compiler facade.
"""

from __future__ import annotations

import subprocess
import sys

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from arxpy import (
    ArtifactKind,
    CompilationArtifact,
    CompileError,
    Compiler,
    ExecutionError,
    ParseError,
)

MODULE_DOCSTRING = """```
title: ArxPy test module
```
"""
FUNCTION_SOURCE = (
    MODULE_DOCSTRING
    + """fn identity(value: i32) -> i32:
  ```
  title: identity
  ```
  return value
"""
)
MAIN_SOURCE = (
    MODULE_DOCSTRING
    + """fn main() -> i32:
  ```
  title: main
  ```
  return 7
"""
)


def test_import_does_not_initialize_llvm() -> None:
    """
    title: Importing the public facade remains independent of LLVM startup.
    """
    command = (
        "import sys; import arxpy; "
        "assert 'llvmlite.binding' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", command], check=True)


def test_parse_string_returns_attributed_program() -> None:
    """
    title: parse_string returns a reusable parsed program.
    """
    program = Compiler().parse_string(
        FUNCTION_SOURCE,
        filename="memory.x",
        module_name="demo",
    )
    assert program.filename == "memory.x"
    assert program.module_name == "demo"
    assert program.module.name == "demo"
    assert program.origin is None


def test_parse_error_has_frontend_code_and_location() -> None:
    """
    title: Parser failures cross the facade as located structured diagnostics.
    """
    with pytest.raises(ParseError) as captured:
        Compiler().parse_string(MODULE_DOCSTRING + "fn broken(")

    [diagnostic] = captured.value.diagnostics
    assert diagnostic.code == "ARX-PARSE-001"
    assert diagnostic.line is not None
    assert diagnostic.column is not None
    assert diagnostic.filename == "<string>"


def test_parse_file_reports_missing_source(tmp_path: Path) -> None:
    """
    title: Source I/O errors become ParseError rather than leaking OSError.
    parameters:
      tmp_path:
        type: Path
    """
    missing = tmp_path / "missing.x"
    with pytest.raises(ParseError) as captured:
        Compiler().parse_file(missing)
    assert captured.value.diagnostics[0].code == "ARXPY-SOURCE-001"


def test_check_returns_checked_program() -> None:
    """
    title: check performs semantic analysis without materializing an artifact.
    """
    compiler = Compiler()
    parsed = compiler.parse_string(FUNCTION_SOURCE)
    checked = compiler.check(parsed)
    assert checked.parsed is parsed


def test_check_translates_semantic_diagnostics() -> None:
    """
    title: Semantic failures become CompileError diagnostics.
    """
    source = (
        MODULE_DOCSTRING
        + """fn broken() -> i32:
  ```
  title: broken
  ```
  return missing
"""
    )
    compiler = Compiler()
    parsed = compiler.parse_string(source, filename="broken.x")
    with pytest.raises(CompileError) as captured:
        compiler.check(parsed)
    assert captured.value.diagnostics
    assert captured.value.diagnostics[0].filename == "broken.x"


def test_in_memory_import_requires_an_origin() -> None:
    """
    title: Imports from unattributed in-memory input fail at the API boundary.
    """
    source = MODULE_DOCSTRING + "import support.arithmetic\n"
    compiler = Compiler()
    parsed = compiler.parse_string(source)
    with pytest.raises(CompileError) as captured:
        compiler.check(parsed)
    assert captured.value.diagnostics[0].code == "ARXPY-IMPORT-001"


def test_missing_file_import_is_a_located_semantic_diagnostic(
    tmp_path: Path,
) -> None:
    """
    title: Host module lookup failures cross ArxPy with a stable IRx code.
    parameters:
      tmp_path:
        type: Path
    """
    source = tmp_path / "main.x"
    source.write_text(
        MODULE_DOCSTRING + "import missing.module\n",
        encoding="utf-8",
    )
    compiler = Compiler()
    with pytest.raises(CompileError) as captured:
        compiler.check(compiler.parse_file(source))
    [diagnostic] = captured.value.diagnostics
    assert diagnostic.code == "S011"
    assert diagnostic.filename == str(source.resolve())
    assert diagnostic.line == 4
    assert diagnostic.column == 1


def test_compile_llvm_ir_without_temporary_artifact() -> None:
    """
    title: LLVM IR can be returned entirely in memory.
    """
    compiler = Compiler()
    parsed = compiler.parse_string(FUNCTION_SOURCE)
    artifact = compiler.compile(parsed, kind=ArtifactKind.LLVM_IR)
    assert artifact.kind is ArtifactKind.LLVM_IR
    assert artifact.path is None
    assert artifact.llvm_ir is not None
    assert "define" in artifact.llvm_ir


def test_compile_llvm_ir_can_write_caller_path(tmp_path: Path) -> None:
    """
    title: An explicit LLVM IR output is materialized at the requested path.
    parameters:
      tmp_path:
        type: Path
    """
    output = tmp_path / "module.ll"
    artifact = Compiler().compile(
        Compiler().parse_string(FUNCTION_SOURCE),
        kind=ArtifactKind.LLVM_IR,
        output=output,
    )
    assert artifact.path == output.resolve()
    assert output.read_text(encoding="utf-8") == artifact.llvm_ir


def test_in_memory_object_requires_output_path() -> None:
    """
    title: The facade never creates an implicit temporary native artifact.
    """
    compiler = Compiler()
    parsed = compiler.parse_string(FUNCTION_SOURCE)
    with pytest.raises(CompileError) as captured:
        compiler.compile(parsed, kind=ArtifactKind.OBJECT)
    assert captured.value.diagnostics[0].code == "ARXPY-OUTPUT-001"


def test_compile_object_materializes_requested_path(tmp_path: Path) -> None:
    """
    title: Object compilation returns a typed persistent artifact.
    parameters:
      tmp_path:
        type: Path
    """
    output = tmp_path / "module.o"
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(FUNCTION_SOURCE),
        kind=ArtifactKind.OBJECT,
        output=output,
    )
    assert artifact == CompilationArtifact(
        kind=ArtifactKind.OBJECT,
        path=output.resolve(),
    )
    assert output.stat().st_size > 0


def test_executable_requires_main(tmp_path: Path) -> None:
    """
    title: Explicit executable requests reject programs without an entrypoint.
    parameters:
      tmp_path:
        type: Path
    """
    compiler = Compiler()
    parsed = compiler.parse_string(FUNCTION_SOURCE)
    with pytest.raises(CompileError) as captured:
        compiler.compile(
            parsed,
            kind=ArtifactKind.EXECUTABLE,
            output=tmp_path / "program",
        )
    assert captured.value.diagnostics[0].code == "ARXPY-ENTRY-001"


def test_compile_and_run_executable(tmp_path: Path) -> None:
    """
    title: Executable results capture a program's non-zero exit as data.
    parameters:
      tmp_path:
        type: Path
    """
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_string(MAIN_SOURCE),
        output=tmp_path / "program",
    )
    assert artifact.kind is ArtifactKind.EXECUTABLE
    result = compiler.run(artifact)
    assert result.exit_code == 7
    assert result.stdout == ""
    assert result.stderr == ""


def test_run_rejects_non_executable_artifact(tmp_path: Path) -> None:
    """
    title: run rejects object and IR artifacts before starting a subprocess.
    parameters:
      tmp_path:
        type: Path
    """
    artifact = CompilationArtifact(
        kind=ArtifactKind.OBJECT,
        path=tmp_path / "module.o",
    )
    with pytest.raises(ExecutionError) as captured:
        Compiler().run(artifact)
    assert captured.value.diagnostics[0].code == "ARXPY-EXECUTABLE-001"


def test_repeated_and_concurrent_parse_calls_are_isolated() -> None:
    """
    title: The global frontend buffer is serialized across Compiler instances.
    """
    module_names = [f"module_{index}" for index in range(16)]

    def parse(module_name: str) -> str:
        """
        title: Parse one module through an independent compiler instance.
        parameters:
          module_name:
            type: str
        returns:
          type: str
        """
        program = Compiler().parse_string(
            FUNCTION_SOURCE,
            module_name=module_name,
        )
        return program.module.name

    with ThreadPoolExecutor(max_workers=4) as executor:
        actual = list(executor.map(parse, module_names))
    assert actual == module_names
