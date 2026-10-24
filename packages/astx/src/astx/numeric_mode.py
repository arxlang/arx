"""
title: Explicit numeric execution intent.
"""

from enum import Enum

from public import public

from astx.tools.typing import typechecked


@public
@typechecked
class NumericMode(str, Enum):
    """
    title: Explicit checked or modular numeric intent.
    """

    CHECKED = "checked"
    WRAPPING = "wrapping"
