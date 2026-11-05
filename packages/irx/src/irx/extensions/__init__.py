"""
title: Explicit, immutable compiler handler contributions.
summary: Discovery is explicit; importing this package loads no backend.
"""

from irx.extensions.handlers import (
    ConfigurationError,
    HandlerConfiguration,
    HandlerContribution,
    ScopedDispatch,
    contribute,
)
from irx.extensions.providers import (
    FeatureConfiguration,
    FeatureDescriptor,
    PhaseProvider,
    default_feature_configuration,
    discover_builtin_features,
)

__all__ = [
    "ConfigurationError",
    "FeatureConfiguration",
    "FeatureDescriptor",
    "HandlerConfiguration",
    "HandlerContribution",
    "PhaseProvider",
    "ScopedDispatch",
    "contribute",
    "default_feature_configuration",
    "discover_builtin_features",
]
