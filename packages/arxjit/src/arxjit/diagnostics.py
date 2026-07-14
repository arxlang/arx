"""
title: Structured diagnostic records for arxjit.
summary: >-
  Define the frozen Diagnostic record and the DiagnosticSeverity enum that
  arxjit uses to report problems found while extracting, validating, or
  compiling a decorated Python function. Diagnostics point at the user's Python
  source (the file and line of the decorated function), so messages stay
  actionable without exposing compiler internals.
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
    title: One structured diagnostic reported by arxjit.
    attributes:
      severity:
        type: DiagnosticSeverity
        description: The severity level of the diagnostic.
      message:
        type: str
        description: The human-readable diagnostic message.
      filename:
        type: str
        description: >-
          The file defining the decorated function, or "<unknown>" when the
          source cannot be attributed.
      line:
        type: int | None
        description: One-based source line in ``filename``, when known.
      column:
        type: int | None
        description: >-
          One-based Unicode character column in ``line``, when known. Python
          AST ``col_offset`` values (zero-based UTF-8 byte offsets) must be
          converted to this representation at the boundary that produces the
          diagnostic, never stored raw.
      code:
        type: str | None
        description: Stable diagnostic code, e.g. "AJ001", when assigned.
    """

    severity: DiagnosticSeverity
    message: str
    filename: str
    line: int | None
    column: int | None
    code: str | None = None

    def __str__(self) -> str:
        """
        title: Render the diagnostic as one human-readable line.
        summary: >-
          Format is ``file:line:column: severity: [code] message``. Unknown
          location parts are omitted (a column is only rendered when the line
          is also known), and an unset or empty code renders no bracket prefix.
        returns:
          type: str
        """
        location = self.filename
        if self.line is not None:
            location = f"{location}:{self.line}"
            if self.column is not None:
                location = f"{location}:{self.column}"
        prefix = f"[{self.code}] " if self.code else ""
        return f"{location}: {self.severity.value}: {prefix}{self.message}"


__all__ = [
    "Diagnostic",
    "DiagnosticSeverity",
]
