"""
title: Smoke tests for arxpy package import.
"""

import arxpy


def test_import() -> None:
    """
    title: Verify arxpy can be imported and exposes a version.
    """
    assert arxpy.__version__
