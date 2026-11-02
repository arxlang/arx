"""
title: ASTx Data Types module.
"""

from __future__ import annotations

from public import public

from astx.tools.typing import typechecked
from astx.types.base import AnyType


@public
@typechecked
class String(AnyType):
    """
    title: Base class for strings.
    """


@public
@typechecked
class UTF8String(String):
    """
    title: Class for UTF-8 encoded strings.
    """


@public
@typechecked
class UTF8Char(String):
    """
    title: Class for UTF-8 encoded characters.
    """


@public
@typechecked
class Bytes(AnyType):
    """
    title: Immutable octets, distinct from Unicode and Arrow binary.
    summary: >-
      Elements are UInt8 and lengths count bytes, including embedded NUL.
      Storage, checked construction, and ownership are semantic-host contracts.
    """
