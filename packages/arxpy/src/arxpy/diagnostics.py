"""
title: Structured diagnostic records for the ArxPy public API.
summary: Define the stable, frozen Diagnostic record and the DiagnosticSeverity
  enum that ArxPy exposes to callers, plus the duck-typed helpers
  that translate upstream irx structured diagnostics and arx parser
  exceptions into it. The Diagnostic type strips the astx.AST node
  reference that irx records carry, so external callers never see
  raw compiler internals. These modules never import arx or irx at
  module load time, so importing arxpy.diagnostics stays free of
  the LLVM toolchain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from public import private, public

from arxpy.typecheck import typechecked


@public
@typechecked
class DiagnosticSeverity(Enum):
    """
    title: Severity level of a diagnostic.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


@public
@typechecked
@dataclass(frozen=True, init=False)
class Diagnostic:
    """
    title: One structured diagnostic exposed by the ArxPy API.
    attributes:
      severity: The severity level of the diagnostic.
      message: The human-readable diagnostic message.
      filename: Source attribution, or "<string>" / "<unknown>".
      line: One-based source line, when known.
      column: One-based source column, when known.
      code: Stable diagnostic code, e.g. "S001", when known.
    """

    severity: DiagnosticSeverity
    message: str
    filename: str
    line: int | None
    column: int | None
    code: str | None = None

    def __init__(
        self,
        severity: DiagnosticSeverity,
        message: str,
        filename: str,
        line: int | None,
        column: int | None,
        code: str | None = None,
    ) -> None:
        """
        title: Initialize one structured diagnostic.
        parameters:
          severity: Severity.
          message: Diagnostic or output message.
          filename: Source or resource filename.
          line: Source line coordinate.
          column: Column to process.
          code: Source code or diagnostic identifier.
        """
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "line", line)
        object.__setattr__(self, "column", column)
        object.__setattr__(self, "code", code)


@private
@typechecked
def coerce_severity(value: object) -> DiagnosticSeverity:
    """
    title: Coerce an upstream severity value into a DiagnosticSeverity.
    summary: Current irx diagnostics expose severity as a plain string
      such as "error"; enum-like values exposing `.value` are also
      handled. Unrecognised values fall back to ERROR.
    parameters:
      value: Value to process.
    returns: 'Result of this operation: coerce an upstream severity
      value into a DiagnosticSeverity.'
    """
    if isinstance(value, DiagnosticSeverity):
        return value
    raw = getattr(value, "value", value)
    try:
        return DiagnosticSeverity(str(raw))
    except ValueError:
        return DiagnosticSeverity.ERROR


@private
@typechecked
def resolve_source(record: object) -> object | None:
    """
    title: Return the best-effort source location of an irx diagnostic.
    parameters:
      record: Record.
    returns: The best-effort source location of an irx diagnostic.
    """
    resolver = getattr(record, "resolved_source", None)
    if callable(resolver):
        resolved: object = resolver()
        return resolved
    source: object = getattr(record, "source", None)
    return source


@private
@typechecked
def resolve_module_key(record: object) -> str | None:
    """
    title: Return the best-effort module attribution of an irx diagnostic.
    parameters:
      record: Record.
    returns: The best-effort module attribution of an irx diagnostic.
    """
    resolver = getattr(record, "resolved_module_key", None)
    if callable(resolver):
        module_key = resolver()
    else:
        module_key = getattr(record, "module_key", None)
    return None if module_key is None else str(module_key)


@private
@typechecked
def from_irx(
    record: object,
    *,
    filename: str | None = None,
) -> Diagnostic:
    """
    title: Translate one irx structured diagnostic into an ArxPy
      Diagnostic.
    summary: Reads the upstream record by attribute so it accepts
      any irx.diagnostics Diagnostic without importing irx, and discards
      the astx.AST node reference. The current irx SourceLocation
      carries no filename, so the attribution falls back to an explicit
      filename, then the diagnostic's module key, then "<unknown>".
    parameters:
      record: Record.
      filename: Source or resource filename.
    returns: 'Result of this operation: translate one irx structured
      diagnostic into an ArxPy Diagnostic.'
    """
    source = resolve_source(record)
    code = getattr(record, "code", None)
    attribution = filename or resolve_module_key(record) or "<unknown>"
    return Diagnostic(
        severity=coerce_severity(getattr(record, "severity", "error")),
        message=str(getattr(record, "message", record)),
        filename=attribution,
        line=getattr(source, "line", None),
        column=getattr(source, "col", None),
        code=None if code is None else str(code),
    )


@private
@typechecked
def from_arx_error(
    exc: object,
    *,
    filename: str = "<string>",
) -> Diagnostic:
    """
    title: Translate an expected Arx frontend error into a Diagnostic.
    summary: Reads the stable code and optional source location exposed by
      ArxError without importing the frontend at module import time.
    parameters:
      exc: Exc.
      filename: Source or resource filename.
    returns: 'Result of this operation: translate an expected Arx frontend
      error into a Diagnostic.'
    """
    location = getattr(exc, "location", None)
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", str(exc))
    return Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message=str(message),
        filename=filename,
        line=getattr(location, "line", None),
        column=getattr(location, "col", None),
        code=None if code is None else str(code),
    )


@private
@typechecked
def from_parser_exception(
    exc: object,
    *,
    filename: str = "<string>",
) -> Diagnostic:
    """
    title: Translate an Arx parser failure into an ArxPy Diagnostic.
    summary: Compatibility alias for the general expected-frontend adapter.
    parameters:
      exc: Exc.
      filename: Source or resource filename.
    returns: 'Result of this operation: translate an Arx parser failure into
      an ArxPy Diagnostic.'
    """
    return from_arx_error(exc, filename=filename)


__all__ = [
    "Diagnostic",
    "DiagnosticSeverity",
]
