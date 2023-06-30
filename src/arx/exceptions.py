"""Define custom Exceptions to improve error message."""


class ParserException(Exception):
    """Handle exceptions for the Parser phase."""

    def __init__(self, message: str):
        """Initialize ParserException."""
        super().__init__(f"ParserError: {message}")