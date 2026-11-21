"""
title: Runtime type-checking helpers.
summary: Reuse ASTx's import-time runtime-checking policy.
"""

from typing import Any, Callable, TypeVar

from astx.tools.typing import typechecked
from public import public

_T = TypeVar("_T")

__all__ = ["copy_type", "skip_unused", "typechecked"]


@public
@typechecked
def skip_unused(*args: Any, **kwargs: Any) -> None:
    """
    title: Referencing variables to pacify static analyzers.
    parameters:
      args:
        variadic: positional
        description: Positional arguments.
      kwargs:
        variadic: keyword
        description: Keyword arguments.
    """
    for _arg in args:
        pass
    for _key in kwargs:
        pass


@public
@typechecked
def copy_type(f: _T) -> Callable[[Any], _T]:
    """
    title: Copy types for args, kwargs from parent class.
    parameters:
      f: F.
    returns: 'Result of this operation: copy types for args, kwargs from
      parent class.'
    """
    skip_unused(f)
    return lambda x: x
