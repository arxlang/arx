"""
title: Runtime feature registry and per-module activation state.
"""

from __future__ import annotations

from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Iterable, Mapping

from llvmlite import ir

from irx.builder.runtime.array.feature import build_array_runtime_feature
from irx.builder.runtime.arrow_compute import (
    build_arrow_compute_runtime_feature,
)
from irx.builder.runtime.buffer.feature import build_buffer_runtime_feature
from irx.builder.runtime.classes import build_class_runtime_feature
from irx.builder.runtime.dataframe.feature import (
    build_dataframe_runtime_feature,
)
from irx.builder.runtime.errors.feature import build_runtime_failure_feature
from irx.builder.runtime.exceptions.feature import (
    build_exception_runtime_feature,
)
from irx.builder.runtime.feature_libc import build_libc_runtime_feature
from irx.builder.runtime.feature_libm import build_libm_runtime_feature
from irx.builder.runtime.features import NativeArtifact, RuntimeFeature
from irx.builder.runtime.file import build_file_runtime_feature
from irx.builder.runtime.list.feature import build_list_runtime_feature
from irx.builder.runtime.record_batch import (
    build_parquet_runtime_feature,
    build_record_batch_runtime_feature,
)
from irx.builder.runtime.tensor.feature import build_tensor_runtime_feature
from irx.builder.runtime.text.feature import build_text_runtime_feature
from irx.diagnostics import (
    Diagnostic,
    DiagnosticCodes,
    RuntimeFeatureError,
)
from irx.native import BUILTIN_RUNTIME_FEATURES, NativeFeature
from irx.typecheck import typechecked

if TYPE_CHECKING:
    from irx.builder.protocols import VisitorProtocol


@typechecked
class RuntimeFeatureRegistry:
    """
    title: Registry of named runtime features.
    attributes:
      _features: Features.
    """

    def __init__(self) -> None:
        """
        title: Initialize RuntimeFeatureRegistry.
        """
        self._features: Mapping[str, RuntimeFeature] = {}

    def register(self, feature: RuntimeFeature) -> None:
        """
        title: Register a runtime feature by name.
        parameters:
          feature: Feature.
        """
        if not isinstance(self._features, dict):
            raise ValueError("runtime capability snapshot is immutable")
        if feature.name in self._features:
            raise ValueError(
                f"Runtime feature '{feature.name}' already exists"
            )
        self._features[feature.name] = feature

    def freeze(self) -> RuntimeFeatureRegistry:
        """
        title: Close registration before sharing this capability snapshot.
        returns: 'Result of this operation: close registration before sharing
          this capability snapshot.'
        """
        self._features = MappingProxyType(dict(self._features))
        return self

    def with_native_features(
        self, features: tuple[NativeFeature, ...]
    ) -> RuntimeFeatureRegistry:
        """
        title: Copy builtin definitions into an isolated compilation registry.
        parameters:
          features: Features.
        returns: 'Result of this operation: copy builtin definitions into
          an isolated compilation registry.'
        """
        registry = RuntimeFeatureRegistry()
        for feature in self._features.values():
            registry.register(feature)
        for native in features:
            registry.register(
                RuntimeFeature(
                    name=native.name,
                    artifacts=native.artifacts,
                    linker_flags=native.linker_flags,
                )
            )
        return registry.freeze()

    def get(self, name: str) -> RuntimeFeature:
        """
        title: Return a runtime feature by name.
        parameters:
          name: Name identifying the declaration or operation.
        returns: A runtime feature by name.
        """
        try:
            return self._features[name]
        except KeyError as exc:
            available = self.names()
            raise RuntimeFeatureError(
                Diagnostic(
                    message=f"runtime feature '{name}' is not registered",
                    code=DiagnosticCodes.RUNTIME_FEATURE_UNKNOWN,
                    phase="runtime",
                    notes=(
                        f"available runtime features: {', '.join(available)}",
                    )
                    if available
                    else (),
                    cause=KeyError(name),
                )
            ) from exc

    def names(self) -> tuple[str, ...]:
        """
        title: Return the registered runtime feature names.
        returns: The registered runtime feature names.
        """
        return tuple(sorted(self._features))


@typechecked
class RuntimeFeatureState:
    """
    title: Track feature activation and symbol declarations for one module.
    attributes:
      _owner: Owner.
      _registry: Registry.
      _active_features: Active features.
      _declared_symbols: Declared symbols.
    """

    _owner: VisitorProtocol
    _registry: RuntimeFeatureRegistry
    _active_features: set[str]
    _declared_symbols: dict[tuple[str, str], ir.Function]

    def __init__(
        self,
        owner: "VisitorProtocol",
        registry: RuntimeFeatureRegistry,
        active_features: Iterable[str] | None = None,
    ) -> None:
        """
        title: Initialize RuntimeFeatureState.
        parameters:
          owner: Owner keeping the resource alive.
          registry: Registry.
          active_features: Active features.
        """
        self._owner = owner
        self._registry = registry
        self._active_features: set[str] = set()
        self._declared_symbols: dict[tuple[str, str], ir.Function] = {}

        if active_features is None:
            return

        for feature_name in active_features:
            self.activate(feature_name)

    def activate(self, feature_name: str) -> None:
        """
        title: Activate a runtime feature for the current module.
        parameters:
          feature_name: Name of feature.
        """
        features = self.dependency_order(feature_name, frozenset())
        self._active_features.update(feature.name for feature in features)

    def dependency_order(
        self, name: str, visiting: frozenset[str]
    ) -> tuple[RuntimeFeature, ...]:
        """
        title: Validate a feature dependency graph before activating any
          nodes.
        parameters:
          name: Name identifying the declaration or operation.
          visiting: Visiting.
        returns: 'Result of this operation: validate a feature dependency
          graph before activating any nodes.'
        """
        if name in visiting:
            raise RuntimeFeatureError(
                Diagnostic(
                    message=f"runtime feature dependency cycle at '{name}'",
                    code=DiagnosticCodes.RUNTIME_FEATURE_DEPENDENCY_CYCLE,
                    phase="runtime",
                )
            )
        feature = self._registry.get(name)
        if feature.unavailable_reason is not None:
            raise RuntimeFeatureError(
                Diagnostic(
                    message=f"runtime feature '{name}' is unavailable",
                    code=DiagnosticCodes.RUNTIME_FEATURE_UNAVAILABLE,
                    phase="runtime",
                    notes=(feature.unavailable_reason,),
                )
            )
        result: list[RuntimeFeature] = []
        for dependency in feature.dependencies:
            result.extend(self.dependency_order(dependency, visiting | {name}))
        result.append(feature)
        return tuple(result)

    def is_active(self, feature_name: str) -> bool:
        """
        title: Return whether a feature is active for the current module.
        parameters:
          feature_name: Name of feature.
        returns: Whether a feature is active for the current module.
        """
        return feature_name in self._active_features

    def active_feature_names(self) -> tuple[str, ...]:
        """
        title: Return the active feature names.
        returns: The active feature names.
        """
        return tuple(sorted(self._active_features))

    def feature(self, feature_name: str) -> RuntimeFeature:
        """
        title: Return a registered feature by name.
        parameters:
          feature_name: Name of feature.
        returns: A registered feature by name.
        """
        return self._registry.get(feature_name)

    def feature_declares_symbol(
        self,
        feature_name: str,
        symbol_name: str,
    ) -> bool:
        """
        title: Return whether one feature declares one symbol.
        parameters:
          feature_name: Name of feature.
          symbol_name: Name of symbol.
        returns: Whether one feature declares one symbol.
        """
        return symbol_name in self.feature(feature_name).symbols

    def require_symbol(
        self,
        feature_name: str,
        symbol_name: str,
    ) -> ir.Function:
        """
        title: Activate a feature and declare one of its external symbols.
        parameters:
          feature_name: Name of feature.
          symbol_name: Name of symbol.
        returns: 'Result of this operation: activate a feature and declare
          one of its external symbols.'
        """
        self.activate(feature_name)
        cache_key = (feature_name, symbol_name)
        cached = self._declared_symbols.get(cache_key)
        if cached is not None:
            return cached

        feature = self.feature(feature_name)
        try:
            symbol_spec = feature.symbols[symbol_name]
        except KeyError as exc:
            raise RuntimeFeatureError(
                Diagnostic(
                    message=(
                        f"runtime feature '{feature_name}' does not declare "
                        f"symbol '{symbol_name}'"
                    ),
                    code=DiagnosticCodes.RUNTIME_FEATURE_SYMBOL_MISSING,
                    phase="runtime",
                    notes=(
                        "declared symbols: "
                        f"{', '.join(sorted(feature.symbols))}",
                    )
                    if feature.symbols
                    else (),
                    cause=KeyError(symbol_name),
                )
            ) from exc

        declared = symbol_spec.declare(self._owner)
        self._declared_symbols[cache_key] = declared
        return declared

    def native_artifacts(self) -> tuple[NativeArtifact, ...]:
        """
        title: Return the native artifacts required by active features.
        returns: The native artifacts required by active features.
        """
        artifacts: list[NativeArtifact] = []
        seen: set[tuple[str, str]] = set()

        for feature_name in self.active_feature_names():
            feature = self.feature(feature_name)
            for artifact in feature.artifacts:
                dedupe_key = (artifact.kind, str(artifact.path))
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                artifacts.append(artifact)

        return tuple(artifacts)

    def linker_flags(self) -> tuple[str, ...]:
        """
        title: Return the linker flags required by active features.
        returns: The linker flags required by active features.
        """
        flags: list[str] = []
        seen: set[str] = set()

        for feature_name in self.active_feature_names():
            feature = self.feature(feature_name)
            for flag in feature.linker_flags:
                if flag in seen:
                    continue
                seen.add(flag)
                flags.append(flag)

        return tuple(flags)


@lru_cache(maxsize=1)
@typechecked
def get_default_runtime_feature_registry() -> RuntimeFeatureRegistry:
    """
    title: Build the default runtime feature registry.
    returns: Constructed the default runtime feature registry.
    """
    registry = RuntimeFeatureRegistry()
    registry.register(build_libc_runtime_feature())
    registry.register(build_runtime_failure_feature())
    registry.register(build_file_runtime_feature())
    registry.register(build_class_runtime_feature())
    registry.register(build_exception_runtime_feature())
    registry.register(build_libm_runtime_feature())
    registry.register(build_buffer_runtime_feature())
    registry.register(build_arrow_compute_runtime_feature())
    registry.register(build_array_runtime_feature())
    registry.register(build_dataframe_runtime_feature())
    registry.register(build_tensor_runtime_feature())
    registry.register(build_list_runtime_feature())
    registry.register(build_text_runtime_feature())
    registry.register(build_record_batch_runtime_feature())
    registry.register(build_parquet_runtime_feature())
    if frozenset(registry.names()) != BUILTIN_RUNTIME_FEATURES:
        raise ValueError("builtin runtime capabilities disagree with analysis")
    return registry.freeze()
