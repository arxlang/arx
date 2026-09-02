"""
title: Runtime type-contract tests for the public ArxPy API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arxpy import (
    ArtifactKind,
    ArxError,
    CheckedProgram,
    CompilationArtifact,
    CompileError,
    Compiler,
    Diagnostic,
    DiagnosticSeverity,
    ExecutionError,
    ExecutionResult,
    ParsedProgram,
    ParseError,
)
from typeguard import TypeCheckError


def test_public_value_records_reject_invalid_constructor_arguments() -> None:
    """
    title: Public artifact and diagnostic records check constructor arguments.
    """
    with pytest.raises(TypeCheckError, match="module"):
        ParsedProgram(  # type: ignore[arg-type]
            object(),
            "source",
            "memory.x",
            "main",
        )
    with pytest.raises(TypeCheckError, match="parsed"):
        CheckedProgram("not parsed")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError, match="kind"):
        CompilationArtifact(  # type: ignore[arg-type]
            "executable",
            Path("program"),
        )
    with pytest.raises(TypeCheckError, match="stdout"):
        ExecutionResult(0, b"output", "")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError, match="severity"):
        Diagnostic(  # type: ignore[arg-type]
            "error",
            "message",
            "memory.x",
            None,
            None,
        )


def test_public_error_checks_every_diagnostic_item() -> None:
    """
    title: Exception construction checks every diagnostic collection item.
    """
    diagnostic = Diagnostic(
        DiagnosticSeverity.ERROR,
        "message",
        "memory.x",
        None,
        None,
    )
    with pytest.raises(TypeCheckError, match="item 1"):
        ParseError(
            "parse failed",
            diagnostics=[diagnostic, "not a diagnostic"],  # type: ignore[list-item]
        )


@pytest.mark.parametrize(
    "error_type",
    [ArxError, ParseError, CompileError, ExecutionError],
)
def test_public_errors_reject_invalid_messages(
    error_type: type[ArxError],
) -> None:
    """
    title: Every public exception class enforces its inherited constructor.
    parameters:
      error_type:
        type: type[ArxError]
    """
    with pytest.raises(TypeCheckError, match="message"):
        error_type(12)  # type: ignore[arg-type]


def test_public_enums_reject_invalid_runtime_values() -> None:
    """
    title: Public enum constructors reject values outside their contracts.
    """
    with pytest.raises(ValueError):
        ArtifactKind(12)
    with pytest.raises(ValueError):
        DiagnosticSeverity(12)


@pytest.mark.parametrize(
    ("method_name", "args", "kwargs"),
    [
        ("parse_string", (b"source",), {}),
        ("parse_file", (object(),), {}),
        ("check", (object(),), {}),
        ("compile", (object(),), {}),
        ("compile_file", (object(),), {}),
    ],
)
def test_compiler_operations_reject_invalid_primary_arguments(
    method_name: str,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    """
    title: Every compiler operation validates its primary public argument.
    parameters:
      method_name:
        type: str
      args:
        type: tuple[object, Ellipsis]
      kwargs:
        type: dict[str, object]
    """
    method = getattr(Compiler(), method_name)
    with pytest.raises(TypeCheckError):
        method(*args, **kwargs)


def test_compile_checks_keyword_argument_types() -> None:
    """
    title: Compilation validates enum and literal-valued keyword arguments.
    """
    program = Compiler().parse_string("""```
title: Runtime type test
```
""")
    with pytest.raises(TypeCheckError, match="kind"):
        Compiler().compile(program, kind="object")  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError, match="link_mode"):
        Compiler().compile(
            program,
            link_mode="dynamic",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("args", ["ab", b"ab"])
def test_run_rejects_scalar_command_arguments(args: object) -> None:
    """
    title: Scalar strings and bytes are never expanded as command arguments.
    parameters:
      args:
        type: object
    """
    artifact = CompilationArtifact(
        ArtifactKind.EXECUTABLE,
        Path("/bin/echo"),
    )
    with pytest.raises(TypeCheckError):
        Compiler().run(artifact, args=args)  # type: ignore[arg-type]


def test_run_checks_every_argument_and_environment_item() -> None:
    """
    title: Execution validates every item in argument and environment inputs.
    """
    artifact = CompilationArtifact(
        ArtifactKind.EXECUTABLE,
        Path("/bin/echo"),
    )
    with pytest.raises(TypeCheckError, match="item 1"):
        Compiler().run(
            artifact,
            args=["valid", 2],  # type: ignore[list-item]
        )
    with pytest.raises(TypeCheckError, match="INVALID"):
        Compiler().run(
            artifact,
            env={"VALID": "yes", "INVALID": 2},  # type: ignore[dict-item]
        )


def test_run_checks_artifact_and_scalar_options() -> None:
    """
    title: Execution validates its artifact, cwd, and timeout boundaries.
    """
    compiler = Compiler()
    artifact = CompilationArtifact(
        ArtifactKind.EXECUTABLE,
        Path("/bin/echo"),
    )
    with pytest.raises(TypeCheckError, match="artifact"):
        compiler.run(object())  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError, match="cwd"):
        compiler.run(artifact, cwd=12)  # type: ignore[arg-type]
    with pytest.raises(TypeCheckError, match="timeout"):
        compiler.run(artifact, timeout="one")  # type: ignore[arg-type]
