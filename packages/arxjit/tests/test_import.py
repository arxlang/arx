"""
title: Smoke tests for arxjit package import.
"""

import arxjit


def test_import() -> None:
    """
    title: Verify arxjit can be imported and exposes a version.
    """
    assert arxjit.__version__
