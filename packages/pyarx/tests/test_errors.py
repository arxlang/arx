"""
title: Unit tests for the PyArx exception hierarchy.
"""

from __future__ import annotations

import pyarx

from pyarx.diagnostics import Diagnostic, DiagnosticSeverity
from pyarx.errors import ArxError, CompileError, ExecutionError, ParseError


def _diagnostic(message: str) -> Diagnostic:
    """
    title: Build a minimal Diagnostic for tests.
    parameters:
      message:
        type: str
    returns:
      type: Diagnostic
    """
    return Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message=message,
        filename="<string>",
        line=None,
        column=None,
    )


def test_hierarchy_and_public_exports() -> None:
    """
    title: Subclasses share ArxError and are re-exported from pyarx.
    """
    for error_type in (ParseError, CompileError, ExecutionError):
        assert issubclass(error_type, ArxError)
    assert pyarx.ArxError is ArxError
    assert pyarx.ParseError is ParseError
    assert pyarx.CompileError is CompileError
    assert pyarx.ExecutionError is ExecutionError
    assert pyarx.Diagnostic is Diagnostic
    assert pyarx.DiagnosticSeverity is DiagnosticSeverity


def test_error_carries_diagnostics() -> None:
    """
    title: An ArxError exposes its message and the diagnostics it carries.
    """
    diagnostics = [_diagnostic("first"), _diagnostic("second")]
    error = CompileError("headline", diagnostics=diagnostics)
    assert str(error) == "headline"
    assert error.diagnostics == diagnostics


def test_error_defaults_to_empty_diagnostics() -> None:
    """
    title: Without diagnostics, the list is empty rather than None.
    """
    assert ArxError("just a message").diagnostics == []


def test_catch_semantics_via_base_class() -> None:
    """
    title: A subclass raise is catchable through ArxError with diagnostics.
    """
    diagnostic = _diagnostic("unexpected token")
    try:
        raise ParseError("parse failed", diagnostics=[diagnostic])
    except ArxError as error:
        assert isinstance(error, ParseError)
        assert error.diagnostics == [diagnostic]
    else:  # pragma: no cover
        raise AssertionError("ParseError should be catchable as ArxError")
