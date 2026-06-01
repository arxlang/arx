"""
title: Smoke tests for pyarx package import.
"""


def test_import() -> None:
    """title: Verify pyarx can be imported and exposes a version."""
    import pyarx

    assert pyarx.__version__
