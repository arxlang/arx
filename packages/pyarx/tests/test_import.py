"""
title: Smoke tests for pyarx package import.
"""

import pyarx


def test_import() -> None:
    """title: Verify pyarx can be imported and exposes a version."""
    assert pyarx.__version__
