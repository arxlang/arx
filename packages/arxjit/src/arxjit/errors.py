"""
title: Public exception hierarchy for arxjit.
summary: >-
  Define the single error hierarchy arxjit raises to callers: ArxJitError as
  the base, with SourceExtractionError for functions whose source cannot be
  retrieved and parsed, and UnsupportedSyntaxError for functions using Python
  constructs outside the supported subset. Each error carries a list of
  structured Diagnostic records so callers can inspect failures
  programmatically instead of scraping message text.
"""

from __future__ import annotations

from collections.abc import Sequence

from arxjit.diagnostics import Diagnostic


class ArxJitError(Exception):
    """
    title: Base class for every error raised by arxjit.
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
        title: Initialize an ArxJitError.
        parameters:
          message:
            type: str
          diagnostics:
            type: Sequence[Diagnostic] | None
        """
        self.diagnostics = list(diagnostics or ())
        super().__init__(message)


class SourceExtractionError(ArxJitError):
    """
    title: Raised when a decorated function's source cannot be extracted.
    summary: >-
      Covers the whole extraction stage, functions whose source cannot be
      retrieved or cannot be parsed as a standalone function definition, such
      as ones defined in the REPL, built with exec, implemented in C, or
      lambdas. Constructs rejected after successful extraction raise
      UnsupportedSyntaxError instead.
    attributes:
      diagnostics:
        type: list[Diagnostic]
    """


class UnsupportedSyntaxError(ArxJitError):
    """
    title: Raised when a function uses Python outside the supported subset.
    summary: >-
      Carries one diagnostic per rejected construct, each pointing at the
      offending source line, so a function with several unsupported constructs
      reports all of them at once.
    attributes:
      diagnostics:
        type: list[Diagnostic]
    """


class LoweringError(ArxJitError):
    """
    title: Raised when a validated function cannot be lowered to astx.
    summary: >-
      Lowering runs on a function validation has already accepted, so this
      reports a disagreement between the two stages rather than a mistake by
      the user: a construct the subset admits that the lowerer has no astx
      mapping for. It stays a distinct error because the fix is a change to
      arxjit, not to the decorated function.
    attributes:
      diagnostics:
        type: list[Diagnostic]
    """


__all__ = [
    "ArxJitError",
    "LoweringError",
    "SourceExtractionError",
    "UnsupportedSyntaxError",
]
