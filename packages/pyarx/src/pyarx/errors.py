"""
title: Public exception hierarchy for the PyArx API.
summary: >-
  Define the single error hierarchy PyArx raises to callers: ArxError as the
  base, with ParseError, CompileError, and ExecutionError for the lex/parse,
  analysis/lowering, and execution stages of the pipeline. Each error carries a
  list of structured Diagnostic records so callers can inspect failures
  programmatically instead of scraping message text. The pipeline modules catch
  upstream arx and irx exceptions and re-raise them as these types, building
  diagnostics via the helpers in pyarx.diagnostics.
"""

from __future__ import annotations

from collections.abc import Sequence

from pyarx.diagnostics import Diagnostic


class ArxError(Exception):
    """
    title: Base class for every error raised by the PyArx API.
    attributes:
      diagnostics:
        type: list[Diagnostic]
        description: Structured diagnostics describing the failure.
    """

    diagnostics: list[Diagnostic]

    def __init__(
        self,
        message: str,
        *,
        diagnostics: Sequence[Diagnostic] | None = None,
    ) -> None:
        """
        title: Initialize an ArxError.
        parameters:
          message:
            type: str
          diagnostics:
            type: Sequence[Diagnostic] | None
        """
        self.diagnostics = list(diagnostics or ())
        super().__init__(message)


class ParseError(ArxError):
    """
    title: Raised when lexing or parsing Arx source fails.
    summary: >-
      Parser-origin diagnostics have no line or column in v1 because
      ParserException discards token location.
    attributes:
      diagnostics:
        type: list[Diagnostic]
    """


class CompileError(ArxError):
    """
    title: >-
      Raised when semantic analysis, lowering, native compile, or linking
      fails.
    summary: >-
      Carries the structured diagnostics from the irx error family, which
      include source locations for most phases.
    attributes:
      diagnostics:
        type: list[Diagnostic]
    """


class ExecutionError(ArxError):
    """
    title: Raised when running a compiled Arx program fails to execute.
    summary: >-
      Reserved for failures that prevent execution from completing, such as a
      missing binary or a timeout. A program that runs to completion with a
      non-zero exit code is reported as data, not raised.
    attributes:
      diagnostics:
        type: list[Diagnostic]
    """


__all__ = [
    "ArxError",
    "CompileError",
    "ExecutionError",
    "ParseError",
]
