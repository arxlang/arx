"""
title: Define custom Exceptions to improve error message.
"""


class ParserException(Exception):
    """
    title: Handle exceptions for the Parser phase.
    """

    def __init__(self, message: str) -> None:
        """
        title: Initialize ParserException.
        parameters:
          message:
            type: str
        """
        super().__init__(f"ParserError: {message}")


class CodeGenException(Exception):
    """
    title: Handle exceptions for the CodeGen phase.
    """

    def __init__(self, message: str) -> None:
        """
        title: Initialize ParserException.
        parameters:
          message:
            type: str
        """
        super().__init__(f"CodeGenError: {message}")
