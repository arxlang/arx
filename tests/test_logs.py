"""Test logs."""

from arx.logs import LogError


def test_log_error() -> None:
    """Test LogError."""
    LogError("Test")
