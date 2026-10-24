"""
title: Uncaught Arx exceptions remain structured subprocess result data.
"""

import shutil

from pathlib import Path

import pytest

from arxpy import ArtifactKind, Compiler, ExecutionResult


def test_execution_result_decodes_exception_lazily() -> None:
    """
    title: Report inspection does not turn a nonzero exit into a Python raise.
    """
    result = ExecutionResult(
        1,
        "before failure\n",
        "ARX_EXCEPTION|root|USER|app.Problem|demo\\pfile.x|7|3|bad\\nvalue\n"
        "ARX_EXCEPTION_FRAME|caller.x|4|2\n",
    )
    assert result.exit_code == 1
    assert result.stdout == "before failure\n"
    failure = result.exception
    assert failure is not None
    assert failure.type_name == "app.Problem"
    assert failure.source == "demo|file.x"
    assert failure.message == "bad\nvalue"
    assert len(failure.frames) == 1
    assert failure.frames[0].source == "caller.x"


@pytest.mark.parametrize(
    "stderr", ["", "ordinary stderr\n", "ARX_EXCEPTION|too|short\n"]
)
def test_execution_result_without_exception_report(stderr: str) -> None:
    """
    title: Ordinary and malformed stderr do not masquerade as exceptions.
    parameters:
      stderr:
        type: str
    """
    result = ExecutionResult(7, "", stderr)
    assert result.exit_code == 7
    assert result.exception is None


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
def test_uncaught_native_exception_is_execution_data(tmp_path: Path) -> None:
    """
    title: The compiler facade returns a failed execution and its typed report.
    parameters:
      tmp_path:
        type: Path
    """
    compiler = Compiler()
    program = compiler.parse_string(
        "```\ntitle: Uncaught exception facade acceptance\n```\n"
        "fn main() -> i32:\n"
        '  raise ValueError("bad input")\n',
    )
    artifact = compiler.compile(program, output=tmp_path / "failure")
    result = compiler.run(artifact, timeout=10)
    assert result.exit_code != 0
    assert result.exception is not None
    assert result.exception.message == "bad input"


def test_explicit_exception_import_requires_no_filesystem_origin() -> None:
    """
    title: Canonical builtin exceptions are available to in-memory hosts.
    """
    compiler = Compiler()
    program = compiler.parse_string(
        "```\ntitle: Imported exception acceptance\n```\n"
        "import ValueError as Problem from builtins.exceptions\n"
        'fn fail() -> none:\n  raise Problem("bad input")\n'
    )
    checked = compiler.check(program)
    artifact = compiler.compile(checked, kind=ArtifactKind.LLVM_IR)
    assert artifact.llvm_ir is not None
    assert "irx_exception_raise" in artifact.llvm_ir


@pytest.mark.skipif(shutil.which("clang") is None, reason="clang required")
def test_imported_exception_identity_is_nominal(tmp_path: Path) -> None:
    """
    title: Equal display names from different modules never match by spelling.
    parameters:
      tmp_path:
        type: Path
    """
    for name, base in (("left", "ValueError"), ("right", "TypeError")):
        (tmp_path / f"{name}.x").write_text(
            "```\ntitle: Imported exception class\n```\n"
            f"class Problem({base}):\n"
            "  ```\n  title: Module-owned failure\n  ```\n",
            encoding="utf-8",
        )
    entry = tmp_path / "main.x"
    entry.write_text(
        "```\ntitle: Nominal exception import acceptance\n```\n"
        "import Problem as LeftProblem from left\n"
        "import right as failures\n"
        "fn main() -> i32:\n"
        '  try:\n    raise LeftProblem("left")\n'
        '  except failures.Problem:\n    print("wrong")\n'
        "  except ValueError as caught:\n    print(caught.message)\n"
        "  return 0\n",
        encoding="utf-8",
    )
    compiler = Compiler()
    artifact = compiler.compile(
        compiler.parse_file(entry), output=tmp_path / "nominal"
    )
    result = compiler.run(artifact, timeout=10)
    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines() == ["left"]
