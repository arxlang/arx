"""
title: AIX frontend exceptions.
"""


class ParserException(Exception):
    """
    title: Handle parser-specific errors.
    """

    def __init__(self, message: str) -> None:
        """
        title: Initialize parser exception.
        parameters:
          message:
            type: str
        """
        super().__init__(message)


class CodeGenException(Exception):
    """
    title: Handle code generation errors.
    """

    def __init__(self, message: str) -> None:
        """
        title: Initialize code generation exception.
        parameters:
          message:
            type: str
        """
        super().__init__(message)
