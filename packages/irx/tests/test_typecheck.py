"""
title: Tests for runtime type-checking helpers.
"""

from astx.tools.typing import typechecked
from irx import typecheck


def test_runtime_checking_policy_is_shared_with_astx() -> None:
    """
    title: IRx keeps the same instrumentation policy as its input AST nodes.
    """
    assert typecheck.typechecked is typechecked


def test_skip_unused_accepts_args_and_kwargs() -> None:
    """
    title: skip_unused should accept positional and keyword values.
    """
    typecheck.skip_unused(1, "two", alpha=3, beta="four")


def test_copy_type_returns_identity_callable() -> None:
    """
    title: copy_type should return a callable that preserves the argument.
    """
    sentinel = object()
    identity = typecheck.copy_type(int)
    assert identity(sentinel) is sentinel
