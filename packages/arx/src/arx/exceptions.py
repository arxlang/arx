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
      code: Stable diagnostic identifier.
      location: Source location attached to this record.
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
          message: Diagnostic or output message.
          code: Source code or diagnostic identifier.
          location: Source coordinates associated with the operation.
        """
        super().__init__(message)
        self.code = code
        self.location = location


class ParserException(ArxError):
    """
    title: Handle exceptions for the Parser phase.
    attributes:
      code: Stable diagnostic identifier.
      location: Source location attached to this record.
      message: Diagnostic message.
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
          message: Diagnostic or output message.
          location: Source coordinates associated with the operation.
          code: Source code or diagnostic identifier.
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
          location: Source coordinates associated with the operation.
        returns: Formatted the parser failure with an optional source location.
        """
        formatted = f"ParserError: {self.message}"
        if location is None:
            return formatted
        return f"{formatted} at line {location.line}, col {location.col}"

    def attach_location(self, location: SourceLocation) -> ParserException:
        """
        title: Attach a source-backed location when one is not already set.
        parameters:
          location: Source coordinates associated with the operation.
        returns: 'Result of this operation: attach a source-backed location
          when one is not already set.'
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
      code: Stable diagnostic identifier.
      location: Source location attached to this record.
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
          message: Diagnostic or output message.
          location: Source coordinates associated with the operation.
          code: Source code or diagnostic identifier.
        """
        formatted = f"CodeGenError: {message}"
        if location is not None:
            formatted += f" at line {location.line}, col {location.col}"
        super().__init__(formatted, code=code, location=location)


class SourceError(ArxError):
    """
    title: Handle expected source loading and size failures.
    attributes:
      code: Stable diagnostic identifier.
      location: Source location attached to this record.
    """

    def __init__(
        self,
        message: str,
        code: str = "ARX-SOURCE-001",
    ) -> None:
        """
        title: Initialize SourceError.
        parameters:
          message: Diagnostic or output message.
          code: Source code or diagnostic identifier.
        """
        super().__init__(message, code=code)


__all__ = [
    "ArxError",
    "CodeGenException",
    "ParserException",
    "SourceError",
]
