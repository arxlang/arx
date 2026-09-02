"""
title: Runtime type-checking helpers for ArxPy.
summary: >-
  Configure Typeguard to validate every item in public collection arguments and
  return values throughout the programmatic compiler API.
"""

from typeguard import (
    CollectionCheckStrategy,
    ForwardRefPolicy,
)
from typeguard import (
    typechecked as typeguard_typechecked,
)
from typeguard._config import global_config

typechecked = typeguard_typechecked(
    forward_ref_policy=ForwardRefPolicy.IGNORE,
    collection_check_strategy=CollectionCheckStrategy.ALL_ITEMS,
)

global_config.forward_ref_policy = ForwardRefPolicy.IGNORE
global_config.collection_check_strategy = CollectionCheckStrategy.ALL_ITEMS

__all__ = ["typechecked"]
