"""
title: Structured diagnostic records for the PyArx public API.
summary: >-
  Define the stable, frozen Diagnostic record and the DiagnosticSeverity enum
  that PyArx exposes to callers, plus the duck-typed helpers that translate
  upstream irx structured diagnostics and arx parser exceptions into it. The
  Diagnostic type strips the astx.AST node reference that irx records carry, so
  external callers never see raw compiler internals. These modules never import
  arx or irx at module load time, so importing pyarx.diagnostics stays free of
  the LLVM toolchain.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DiagnosticSeverity(Enum):
    """
    title: Severity level of a diagnostic.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


@dataclass(frozen=True)
class Diagnostic:
    """
    title: One structured diagnostic exposed by the PyArx API.
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


def _coerce_severity(value: object) -> DiagnosticSeverity:
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


def _resolve_source(record: object) -> object | None:
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


def _resolve_module_key(record: object) -> str | None:
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


def _from_irx(
    record: object,
    *,
    filename: str | None = None,
) -> Diagnostic:
    """
    title: Translate one irx structured diagnostic into a PyArx Diagnostic.
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
    source = _resolve_source(record)
    code = getattr(record, "code", None)
    attribution = filename or _resolve_module_key(record) or "<unknown>"
    return Diagnostic(
        severity=_coerce_severity(getattr(record, "severity", "error")),
        message=str(getattr(record, "message", record)),
        filename=attribution,
        line=getattr(source, "line", None),
        column=getattr(source, "col", None),
        code=None if code is None else str(code),
    )


def _from_parser_exception(
    exc: object,
    *,
    filename: str = "<string>",
) -> Diagnostic:
    """
    title: Translate an arx ParserException into a PyArx Diagnostic.
    summary: >-
      ParserException.__init__ discards the offending token's location, so line
      and column are None by design rather than fabricated.
    parameters:
      exc:
        type: object
      filename:
        type: str
    returns:
      type: Diagnostic
    """
    return Diagnostic(
        severity=DiagnosticSeverity.ERROR,
        message=str(exc),
        filename=filename,
        line=None,
        column=None,
    )


__all__ = [
    "Diagnostic",
    "DiagnosticSeverity",
]
