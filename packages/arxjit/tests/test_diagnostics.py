"""
title: Tests for the arxjit diagnostic records.
"""

import dataclasses

import arxjit
import pytest

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity

_BASE = Diagnostic(
    severity=DiagnosticSeverity.ERROR,
    message="lambda is not supported",
    filename="example.py",
    line=3,
    column=5,
)


def _diagnostic(**overrides: object) -> Diagnostic:
    """
    title: Build a valid Diagnostic, overriding selected fields.
    parameters:
      overrides:
        type: object
        description: Field values replacing the base diagnostic's.
        variadic: keyword
    returns:
      type: Diagnostic
    """
    return dataclasses.replace(_BASE, **overrides)


def test_severity_values() -> None:
    """
    title: The severity enum exposes the four expected levels.
    """
    assert DiagnosticSeverity.ERROR.value == "error"
    assert DiagnosticSeverity.WARNING.value == "warning"
    assert DiagnosticSeverity.INFO.value == "info"
    assert DiagnosticSeverity.HINT.value == "hint"


def test_code_defaults_to_none() -> None:
    """
    title: The diagnostic code is optional and defaults to None.
    """
    assert _diagnostic().code is None


def test_diagnostic_is_immutable() -> None:
    """
    title: Diagnostic instances cannot be mutated.
    """
    diagnostic = _diagnostic()
    with pytest.raises(dataclasses.FrozenInstanceError):
        diagnostic.message = "changed"  # type: ignore[misc]


def test_diagnostic_equality_by_value() -> None:
    """
    title: Diagnostics with identical fields compare equal.
    """
    assert _diagnostic() == _diagnostic()
    assert _diagnostic() != _diagnostic(line=4)


def test_str_with_full_location() -> None:
    """
    title: A fully-located diagnostic renders file, line, and column.
    """
    assert str(_diagnostic()) == (
        "example.py:3:5: error: lambda is not supported"
    )


def test_str_without_column() -> None:
    """
    title: A diagnostic without a column renders file and line only.
    """
    assert str(_diagnostic(column=None)) == (
        "example.py:3: error: lambda is not supported"
    )


def test_str_without_location() -> None:
    """
    title: A diagnostic without line or column renders the file only.
    """
    assert str(_diagnostic(line=None, column=None)) == (
        "example.py: error: lambda is not supported"
    )


def test_str_drops_column_when_line_is_unknown() -> None:
    """
    title: A column without a line is omitted from the rendering.
    """
    assert str(_diagnostic(line=None)) == (
        "example.py: error: lambda is not supported"
    )


def test_str_with_code() -> None:
    """
    title: An assigned diagnostic code renders in brackets.
    """
    assert str(_diagnostic(code="AJ001")) == (
        "example.py:3:5: error: [AJ001] lambda is not supported"
    )
    assert str(_diagnostic(code="")) == str(_diagnostic())


def test_diagnostics_are_exported_from_package() -> None:
    """
    title: Diagnostic and DiagnosticSeverity are exported from arxjit.
    """
    assert arxjit.Diagnostic is Diagnostic
    assert arxjit.DiagnosticSeverity is DiagnosticSeverity
    for name in ("Diagnostic", "DiagnosticSeverity"):
        assert name in arxjit.__all__
