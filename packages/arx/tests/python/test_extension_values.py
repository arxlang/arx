"""
title: Extension storage execution without erasing type identity or metadata.
"""

from pathlib import Path

from .test_nullable_operations import execute
from .test_tabular_values import example_body


def test_extension_values_example(tmp_path: Path) -> None:
    """
    title: Build and inspect canonical and opaque extensions in pure Arx.
    parameters:
      tmp_path:
        type: Path
    """
    result = execute(example_body("extension_values"), tmp_path / "extension")
    assert result.returncode == 0, result.stderr
