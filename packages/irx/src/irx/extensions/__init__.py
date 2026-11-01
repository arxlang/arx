"""
title: Explicit, immutable compiler handler contributions.
summary: No provider discovery or backend imports occur in this package.
"""

from irx.extensions.handlers import (
    ConfigurationError,
    HandlerConfiguration,
    HandlerContribution,
    ScopedDispatch,
    contribute,
)

__all__ = [
    "ConfigurationError",
    "HandlerConfiguration",
    "HandlerContribution",
    "ScopedDispatch",
    "contribute",
]
