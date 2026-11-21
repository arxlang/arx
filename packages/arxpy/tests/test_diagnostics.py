"""
title: Unit tests for the ArxPy Diagnostic record and translation helpers.
"""

from __future__ import annotations

from arxpy.diagnostics import (
    Diagnostic,
    DiagnosticSeverity,
    from_irx,
    from_parser_exception,
)


class _FakeSource:
    """
    title: Stand-in for an irx SourceLocation (line/col only, no filename).
    attributes:
      line: One-based source line, or None.
      col: One-based source column, or None.
    """

    line: int | None
    col: int | None

    def __init__(self, line: int | None, col: int | None) -> None:
        """
        title: Initialize the fake source location.
        parameters:
          line: Source line coordinate.
          col: Source column or column selector.
        """
        self.line = line
        self.col = col


class _FakeRecord:
    """
    title: Stand-in for an irx structured Diagnostic.
    attributes:
      message: The diagnostic message.
      source: The source location, when present.
      severity: The raw severity string, e.g. "error".
      code: Stable diagnostic code, when present.
      module_key: Module attribution, when present.
    """

    message: str
    source: _FakeSource | None
    severity: str
    code: str | None
    module_key: str | None

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
          message: Diagnostic or output message.
          source: Source input to process.
          severity: Severity.
          code: Source code or diagnostic identifier.
          module_key: Canonical module identity.
        """
        self.message = message
        self.source = source
        self.severity = severity
        self.code = code
        self.module_key = module_key

    def resolved_source(self) -> _FakeSource | None:
        """
        title: Return the resolved source location.
        returns: The resolved source location.
        """
        return self.source

    def resolved_module_key(self) -> str | None:
        """
        title: Return the resolved module attribution.
        returns: The resolved module attribution.
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
    title: from_irx maps severity, message, location, code, and module key.
    """
    record = _FakeRecord(
        "unresolved name x",
        source=_FakeSource(5, 12),
        code="S001",
        module_key="main",
    )
    assert from_irx(record) == Diagnostic(
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
    assert from_irx(record, filename="prog.x").filename == "prog.x"


def test_from_irx_without_source_or_module_key() -> None:
    """
    title: Missing source and module key yield None location and "<unknown>".
    """
    diagnostic = from_irx(_FakeRecord("oops"))
    assert diagnostic.line is None
    assert diagnostic.column is None
    assert diagnostic.filename == "<unknown>"


def test_from_irx_coerces_severity() -> None:
    """
    title: A string severity is coerced; unknown values fall back to ERROR.
    """
    warning = from_irx(_FakeRecord("w", severity="warning"))
    assert warning.severity is DiagnosticSeverity.WARNING
    unknown = from_irx(_FakeRecord("j", severity="weird"))
    assert unknown.severity is DiagnosticSeverity.ERROR


def test_from_parser_exception_has_no_location() -> None:
    """
    title: from_parser_exception yields an error with no line or column.
    """
    diagnostic = from_parser_exception(
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
    title: from_parser_exception accepts a filename override.
    """
    diagnostic = from_parser_exception(Exception("bad"), filename="prog.x")
    assert diagnostic.filename == "prog.x"


def test_from_parser_exception_maps_stable_frontend_fields() -> None:
    """
    title: Frontend code and trustworthy location are preserved.
    """
    error = Exception("rendered")
    error.message = "raw parser failure"  # type: ignore[attr-defined]
    error.code = "ARX-PARSE-001"  # type: ignore[attr-defined]
    error.location = _FakeSource(4, 9)  # type: ignore[attr-defined]
    assert from_parser_exception(error, filename="prog.x") == Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message="raw parser failure",
        filename="prog.x",
        line=4,
        column=9,
        code="ARX-PARSE-001",
    )
