"""
title: Unit tests for the ArxPy exception hierarchy.
"""

from __future__ import annotations

import arxpy

from arxpy.diagnostics import Diagnostic, DiagnosticSeverity
from arxpy.errors import ArxError, CompileError, ExecutionError, ParseError


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
    title: Subclasses share ArxError and are re-exported from arxpy.
    """
    for error_type in (ParseError, CompileError, ExecutionError):
        assert issubclass(error_type, ArxError)
    assert arxpy.ArxError is ArxError
    assert arxpy.ParseError is ParseError
    assert arxpy.CompileError is CompileError
    assert arxpy.ExecutionError is ExecutionError
    assert arxpy.Diagnostic is Diagnostic
    assert arxpy.DiagnosticSeverity is DiagnosticSeverity
    assert arxpy.Compiler
    assert arxpy.ArtifactKind


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
