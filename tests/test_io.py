"""
title: Test IO module.
"""

import pytest

from arx.io import ArxIO


@pytest.mark.parametrize("value", ["1", "2", "3"])
def test_write_and_read_single_value(value: str) -> None:
    """
    title: Test write and read of a single value.
    parameters:
      value:
        type: str
    """
    ArxIO.string_to_buffer(value)
    assert ArxIO.buffer.read() == value


def test_write_and_read_multiple_value() -> None:
    """
    title: Test write and read multiple values.
    """
    ArxIO.string_to_buffer("123")
    assert ArxIO.buffer.read() == "1"
    assert ArxIO.buffer.read() == "2"
    assert ArxIO.buffer.read() == "3"
