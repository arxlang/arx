"""
title: The @jit decorator, the public entry point of arxjit.
summary: Wraps a pure Python function so it can be compiled through the Arx
  stack. In this first version the wrapper records the requested signature
  and falls back to running the original Python function; real compilation
  lands in later sprints.
"""

from __future__ import annotations

import functools

from typing import Any, Callable

from arxjit.types import Signature

PyFunc = Callable[..., Any]


class JitFunction:
    """
    title: A callable wrapper around a @jit-decorated function.
    attributes:
      py_func: The original, undecorated Python function.
      signature: The explicit signature, or None when not given.
      cache: Whether compiled artifacts should be cached.
    """

    py_func: PyFunc
    signature: Signature | None
    cache: bool

    def __init__(
        self,
        py_func: PyFunc,
        signature: Signature | None = None,
        cache: bool = False,
    ) -> None:
        """
        title: Wrap a Python function for just-in-time compilation.
        parameters:
          py_func: The function being decorated.
          signature: The explicit call signature, if provided.
          cache: Whether to cache compiled artifacts.
        """
        self.py_func = py_func
        self.signature = signature
        self.cache = cache
        functools.update_wrapper(self, py_func)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        title: Run the function (Python fallback until compilation lands).
        parameters:
          args:
            description: Positional arguments forwarded to the function.
            variadic: positional
          kwargs:
            description: Keyword arguments forwarded to the function.
            variadic: keyword
        returns: 'Result of this operation: run the function (Python fallback
          until compilation lands).'
        """
        return self.py_func(*args, **kwargs)


def jit(
    fn: PyFunc | None = None,
    *,
    signature: Signature | None = None,
    cache: bool = False,
) -> JitFunction | functools.partial[JitFunction]:
    """
    title: Compile a pure Python function through the Arx stack.
    summary: Use ``@jit`` directly or supply ``signature`` and ``cache``
      options. Records the requested signature and returns a callable wrapper.
      When called with options it returns a partial that wraps the function
      next.
    parameters:
      fn: The function to wrap, when used as a bare decorator.
      signature: The explicit call signature.
      cache: Whether to cache compiled artifacts.
    returns: Wrapped function, or a decorator awaiting a function when options
      are supplied.
    """
    if signature is not None and not isinstance(signature, Signature):
        raise TypeError(
            "jit(signature=...) must be a Signature, e.g. i64(i64, i64)"
        )

    if fn is not None:
        return JitFunction(fn, signature=signature, cache=cache)
    return functools.partial(JitFunction, signature=signature, cache=cache)
