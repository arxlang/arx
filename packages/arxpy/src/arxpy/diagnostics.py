"""
title: Structured diagnostic records for the ArxPy public API.
summary: >-
  Define the stable, frozen Diagnostic record and the DiagnosticSeverity enum
  that ArxPy exposes to callers, plus the duck-typed helpers that translate
  upstream irx structured diagnostics and arx parser exceptions into it. The
  Diagnostic type strips the astx.AST node reference that irx records carry, so
  external callers never see raw compiler internals. These modules never import
  arx or irx at module load time, so importing arxpy.diagnostics stays free of
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
      severity:
        type: DiagnosticSeverity
        description: The severity level of the diagnostic.
      message:
        type: str
        description: The human-readable diagnostic message.
      filename:
        type: str
        description: Source attribution, or "<string>" / "<unknown>".
      line:
        type: int | None
        description: One-based source line, when known.
      column:
        type: int | None
        description: One-based source column, when known.
      code:
        type: str | None
        description: Stable diagnostic code, e.g. "S001", when known.
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
          severity:
            type: DiagnosticSeverity
          message:
            type: str
          filename:
            type: str
          line:
            type: int | None
          column:
            type: int | None
          code:
            type: str | None
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
    summary: >-
      Current irx diagnostics expose severity as a plain string such as
      "error"; enum-like values exposing `.value` are also handled.
      Unrecognised values fall back to ERROR.
    parameters:
      value:
        type: object
    returns:
      type: DiagnosticSeverity
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
      record:
        type: object
    returns:
      type: object | None
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
      record:
        type: object
    returns:
      type: str | None
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
    title: Translate one irx structured diagnostic into an ArxPy Diagnostic.
    summary: >-
      Reads the upstream record by attribute so it accepts any irx.diagnostics
      Diagnostic without importing irx, and discards the astx.AST node
      reference. The current irx SourceLocation carries no filename, so the
      attribution falls back to an explicit filename, then the diagnostic's
      module key, then "<unknown>".
    parameters:
      record:
        type: object
      filename:
        type: str | None
    returns:
      type: Diagnostic
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
    summary: >-
      Reads the stable code and optional source location exposed by ArxError
      without importing the frontend at module import time.
    parameters:
      exc:
        type: object
      filename:
        type: str
    returns:
      type: Diagnostic
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
      exc:
        type: object
      filename:
        type: str
    returns:
      type: Diagnostic
    """
    return from_arx_error(exc, filename=filename)


__all__ = [
    "Diagnostic",
    "DiagnosticSeverity",
]
