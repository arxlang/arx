"""
title: Unit tests for the PyArx Diagnostic record and translation helpers.
"""

from __future__ import annotations

from pyarx.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    _from_irx,
    _from_parser_exception,
)


class _FakeSource:
    """
    title: Stand-in for an irx SourceLocation (line/col only, no filename).
    attributes:
      line:
        description: One-based source line, or None.
      col:
        description: One-based source column, or None.
    """

    def __init__(self, line: int | None, col: int | None) -> None:
        """
        title: Initialize the fake source location.
        parameters:
          line:
            type: int | None
          col:
            type: int | None
        """
        self.line = line
        self.col = col


class _FakeRecord:
    """
    title: Stand-in for an irx structured Diagnostic.
    attributes:
      message:
        description: The diagnostic message.
      source:
        description: The source location, when present.
      severity:
        description: The raw severity string, e.g. "error".
      code:
        description: Stable diagnostic code, when present.
      module_key:
        description: Module attribution, when present.
    """

    def __init__(
        self,
        message: str,
        *,
        source: _FakeSource | None = None,
        severity: str = "error",
        code: str | None = None,
        module_key: str | None = None,
    ) -> None:
        """
        title: Initialize the fake record.
        parameters:
          message:
            type: str
          source:
            type: _FakeSource | None
          severity:
            type: str
          code:
            type: str | None
          module_key:
            type: str | None
        """
        self.message = message
        self.source = source
        self.severity = severity
        self.code = code
        self.module_key = module_key

    def resolved_source(self) -> _FakeSource | None:
        """
        title: Return the resolved source location.
        returns:
          type: _FakeSource | None
        """
        return self.source

    def resolved_module_key(self) -> str | None:
        """
        title: Return the resolved module attribution.
        returns:
          type: str | None
        """
        return self.module_key


def test_severity_enum_values() -> None:
    """
    title: DiagnosticSeverity exposes the four documented levels.
    """
    assert {s.value for s in DiagnosticSeverity} == {
        "error",
        "warning",
        "info",
        "hint",
    }
    assert DiagnosticSeverity("error") is DiagnosticSeverity.ERROR


def test_diagnostic_is_frozen() -> None:
    """
    title: Diagnostic is an immutable value record.
    """
    diagnostic = Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message="m",
        filename="<string>",
        line=1,
        column=2,
    )
    try:
        diagnostic.message = "other"  # type: ignore[misc]
    except AttributeError:
        return
    raise AssertionError("Diagnostic should be frozen")


def test_from_irx_maps_every_field() -> None:
    """
    title: _from_irx maps severity, message, location, code, and module key.
    """
    record = _FakeRecord(
        "unresolved name x",
        source=_FakeSource(5, 12),
        code="S001",
        module_key="main",
    )
    assert _from_irx(record) == Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message="unresolved name x",
        filename="main",
        line=5,
        column=12,
        code="S001",
    )


def test_from_irx_explicit_filename_overrides_module_key() -> None:
    """
    title: An explicit filename takes precedence over the module key.
    """
    record = _FakeRecord("oops", module_key="main")
    assert _from_irx(record, filename="prog.x").filename == "prog.x"


def test_from_irx_without_source_or_module_key() -> None:
    """
    title: Missing source and module key yield None location and "<unknown>".
    """
    diagnostic = _from_irx(_FakeRecord("oops"))
    assert diagnostic.line is None
    assert diagnostic.column is None
    assert diagnostic.filename == "<unknown>"


def test_from_irx_coerces_severity() -> None:
    """
    title: A string severity is coerced; unknown values fall back to ERROR.
    """
    warning = _from_irx(_FakeRecord("w", severity="warning"))
    assert warning.severity is DiagnosticSeverity.WARNING
    unknown = _from_irx(_FakeRecord("j", severity="weird"))
    assert unknown.severity is DiagnosticSeverity.ERROR


def test_from_parser_exception_has_no_location() -> None:
    """
    title: _from_parser_exception yields an error with no line or column.
    """
    diagnostic = _from_parser_exception(
        Exception("ParserError: unexpected token")
    )
    assert diagnostic == Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message="ParserError: unexpected token",
        filename="<string>",
        line=None,
        column=None,
    )


def test_from_parser_exception_custom_filename() -> None:
    """
    title: _from_parser_exception accepts a filename override.
    """
    diagnostic = _from_parser_exception(Exception("bad"), filename="prog.x")
    assert diagnostic.filename == "prog.x"
