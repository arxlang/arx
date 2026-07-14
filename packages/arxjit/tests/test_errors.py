"""
title: Tests for the arxjit exception hierarchy.
"""

import arxjit
import pytest

from arxjit.diagnostics import Diagnostic, DiagnosticSeverity
from arxjit.errors import (
    ArxJitError,
    SourceExtractionError,
    UnsupportedSyntaxError,
)

_DIAGNOSTIC = Diagnostic(
    severity=DiagnosticSeverity.ERROR,
    message="lambda is not supported",
    filename="example.py",
    line=3,
    column=5,
)


def test_base_error_message() -> None:
    """
    title: The error message is exposed through str().
    """
    assert str(ArxJitError("extraction failed")) == "extraction failed"


def test_diagnostics_default_to_empty_list() -> None:
    """
    title: An error built without diagnostics carries an empty list.
    """
    assert ArxJitError("failed").diagnostics == []


def test_diagnostics_are_copied() -> None:
    """
    title: The diagnostics sequence is copied defensively.
    """
    source: list[Diagnostic] = [_DIAGNOSTIC]
    error = ArxJitError("failed", diagnostics=source)
    source.clear()
    assert error.diagnostics == [_DIAGNOSTIC]


def test_subclasses_are_arxjit_errors() -> None:
    """
    title: Every public error subclasses ArxJitError and Exception.
    """
    for error_type in (SourceExtractionError, UnsupportedSyntaxError):
        error = error_type("failed", diagnostics=[_DIAGNOSTIC])
        assert isinstance(error, ArxJitError)
        assert isinstance(error, Exception)
        assert error.diagnostics == [_DIAGNOSTIC]


def test_errors_are_catchable_as_base() -> None:
    """
    title: A raised subclass is catchable as ArxJitError.
    """
    with pytest.raises(ArxJitError) as caught:
        raise UnsupportedSyntaxError(
            "unsupported syntax", diagnostics=[_DIAGNOSTIC]
        )
    assert caught.value.diagnostics == [_DIAGNOSTIC]


def test_errors_are_exported_from_package() -> None:
    """
    title: The exception hierarchy is exported from arxjit.
    """
    assert arxjit.ArxJitError is ArxJitError
    assert arxjit.SourceExtractionError is SourceExtractionError
    assert arxjit.UnsupportedSyntaxError is UnsupportedSyntaxError
    for name in (
        "ArxJitError",
        "SourceExtractionError",
        "UnsupportedSyntaxError",
    ):
        assert name in arxjit.__all__
