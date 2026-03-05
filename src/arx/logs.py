"""
title: The logs functions and classes handle all the system messages.
"""

import sys


def LogError(message: str) -> None:
    """
    title: LogError - A helper function for error handling.
    parameters:
      message:
        type: str
        description: The error message.
    """
    print(f"Error: {message}\n", file=sys.stderr)


LogErrorV = LogError
