"""
title: Tools for typing support helper.
summary: >-
  Runtime checking is disabled by default. Set ARX_RUNTIME_TYPECHECK=1 before
  importing the compiler stack to instrument functions and classes for tests.
  Changing the setting after import does not reinstrument existing definitions.
"""

import os

from typing import Any, Callable, TypeVar

from public import public
from typeguard import (
    CollectionCheckStrategy,
    ForwardRefPolicy,
)
from typeguard import (
    typechecked as typeguard_typechecked,
)
from typeguard._config import global_config

_T = TypeVar("_T")
TypecheckedTarget = TypeVar("TypecheckedTarget", bound=Callable[..., object])

RUNTIME_TYPECHECK_SETTING = os.environ.get("ARX_RUNTIME_TYPECHECK", "0")
if RUNTIME_TYPECHECK_SETTING not in {"0", "1"}:
    raise ValueError("ARX_RUNTIME_TYPECHECK must be '0' or '1'")


__all__ = ["typechecked"]


@public
def skip_unused(*args: Any, **kwargs: Any) -> None:
    """
    title: Referencing variables to pacify static analyzers.
    parameters:
      args:
        type: Any
        variadic: positional
      kwargs:
        type: Any
        variadic: keyword
    """
    for arg in args:
        pass
    for key in kwargs:
        pass


@public
def copy_type(f: _T) -> Callable[[Any], _T]:
    """
    title: Copy types for args, kwargs from parent class.
    parameters:
      f:
        type: _T
    returns:
      type: Callable[[Any], _T]
    """
    skip_unused(f)
    return lambda x: x


@public
def typechecked(target: TypecheckedTarget) -> TypecheckedTarget:
    """
    title: Instrument a function or class when runtime checking is enabled.
    summary: >-
      ARX_RUNTIME_TYPECHECK=1 at import enables argument, return, and all-item
      collection checks. Otherwise return the original target without runtime
      instrumentation or a call wrapper. Compiler semantic validation is
      independent of this developer-only setting.
    parameters:
      target:
        type: TypecheckedTarget
    returns:
      type: TypecheckedTarget
    """
    if RUNTIME_TYPECHECK_SETTING == "0":
        return target
    return typeguard_typechecked(
        forward_ref_policy=ForwardRefPolicy.IGNORE,
        collection_check_strategy=CollectionCheckStrategy.ALL_ITEMS,
    )(target)


# Override the default configuration
global_config.forward_ref_policy = ForwardRefPolicy.IGNORE
global_config.collection_check_strategy = CollectionCheckStrategy.ALL_ITEMS
