"""
title: Define custom Exceptions to improve error message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astx import SourceLocation


class ArxError(Exception):
    """
    title: Base class for expected user-facing Arx failures.
    attributes:
      code:
        type: str
      location:
        type: SourceLocation | None
    """

    code: str
    location: SourceLocation | None

    def __init__(
        self,
        message: str,
        *,
        code: str,
        location: SourceLocation | None = None,
    ) -> None:
        """
        title: Initialize an expected Arx failure.
        parameters:
          message:
            type: str
          code:
            type: str
          location:
            type: SourceLocation | None
        """
        super().__init__(message)
        self.code = code
        self.location = location


class ParserException(ArxError):
    """
    title: Handle exceptions for the Parser phase.
    attributes:
      code:
        type: str
      location:
        type: SourceLocation | None
      message:
        type: str
    """

    message: str

    def __init__(
        self,
        message: str,
        location: SourceLocation | None = None,
        code: str = "ARX-PARSE-001",
    ) -> None:
        """
        title: Initialize ParserException.
        parameters:
          message:
            type: str
          location:
            type: SourceLocation | None
          code:
            type: str
        """
        self.message = message
        super().__init__(
            self.format_message(location),
            code=code,
            location=location,
        )

    def format_message(self, location: SourceLocation | None) -> str:
        """
        title: Format the parser failure with an optional source location.
        parameters:
          location:
            type: SourceLocation | None
        returns:
          type: str
        """
        formatted = f"ParserError: {self.message}"
        if location is None:
            return formatted
        return f"{formatted} at line {location.line}, col {location.col}"

    def attach_location(self, location: SourceLocation) -> ParserException:
        """
        title: Attach a source-backed location when one is not already set.
        parameters:
          location:
            type: SourceLocation
        returns:
          type: ParserException
        """
        if self.location is not None:
            return self
        self.location = location
        self.args = (self.format_message(location),)
        return self


class CodeGenException(ArxError):
    """
    title: Handle exceptions for the CodeGen phase.
    attributes:
      code:
        type: str
      location:
        type: SourceLocation | None
    """

    def __init__(
        self,
        message: str,
        location: SourceLocation | None = None,
        code: str = "ARX-CODEGEN-001",
    ) -> None:
        """
        title: Initialize ParserException.
        parameters:
          message:
            type: str
          location:
            type: SourceLocation | None
          code:
            type: str
        """
        formatted = f"CodeGenError: {message}"
        if location is not None:
            formatted += f" at line {location.line}, col {location.col}"
        super().__init__(formatted, code=code, location=location)


class SourceError(ArxError):
    """
    title: Handle expected source loading and size failures.
    attributes:
      code:
        type: str
      location:
        type: SourceLocation | None
    """

    def __init__(
        self,
        message: str,
        code: str = "ARX-SOURCE-001",
    ) -> None:
        """
        title: Initialize SourceError.
        parameters:
          message:
            type: str
          code:
            type: str
        """
        super().__init__(message, code=code)


__all__ = [
    "ArxError",
    "CodeGenException",
    "ParserException",
    "SourceError",
]
