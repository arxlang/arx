"""
title: Tests for the arxjit @jit decorator.
"""

import arxjit
import pytest

from arxjit import JitFunction, i64, jit


def _add(a: int, b: int) -> int:
    """
    title: Add two integers (test helper).
    parameters:
      a:
        type: int
      b:
        type: int
    returns:
      type: int
    """
    return a + b


def test_wraps_and_runs() -> None:
    """
    title: jit wraps a function and runs it (Python fallback).
    """
    wrapped = jit(_add)
    assert isinstance(wrapped, JitFunction)
    assert wrapped.signature is None
    assert wrapped.cache is False
    assert wrapped(2, 3) == 5


def test_records_signature() -> None:
    """
    title: jit(signature=...) records the signature.
    """
    sig = i64(i64, i64)
    wrapped = jit(signature=sig)(_add)
    assert wrapped.signature is sig
    assert wrapped(4, 5) == 9


def test_records_cache_flag() -> None:
    """
    title: jit(cache=True) records the cache flag.
    """
    wrapped = jit(signature=i64(i64, i64), cache=True)(_add)
    assert wrapped.cache is True


def test_no_options_leaves_signature_none() -> None:
    """
    title: jit() with no options records no signature.
    """
    wrapped = jit()(_add)
    assert isinstance(wrapped, JitFunction)
    assert wrapped.signature is None
    assert wrapped(1, 1) == 2


def test_original_function_preserved() -> None:
    """
    title: The wrapper preserves the original function and its metadata.
    """
    wrapped = jit(_add)
    assert wrapped.py_func is _add
    assert wrapped.__wrapped__ is _add
    assert wrapped.__name__ == "_add"
    assert wrapped.__doc__ == _add.__doc__


def test_invalid_signature_raises() -> None:
    """
    title: A non-Signature signature argument raises TypeError.
    """
    with pytest.raises(TypeError, match="Signature"):
        jit(signature="i64(i64, i64)")  # type: ignore[arg-type]


def test_jit_is_exported() -> None:
    """
    title: jit and JitFunction are exported from arxjit.
    """
    assert arxjit.jit is jit
    assert arxjit.JitFunction is JitFunction
    for name in ("jit", "JitFunction"):
        assert name in arxjit.__all__
